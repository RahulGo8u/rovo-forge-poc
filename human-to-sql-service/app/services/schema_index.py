"""Schema retrieval for NL2SQL.

The database has 410 base tables and 2904 columns, far more than fits in a model
prompt. This module narrows a natural-language question down to a handful of
relevant tables and the real foreign keys between them, so generation sees a
small, accurate slice instead of the whole catalogue.

Retrieval is hybrid:
  * BM25 over per-table documents built from table and column names
  * optional Gemini embedding vectors, fused with BM25 by reciprocal rank fusion
  * foreign-key expansion so join partners and lookup tables come along

Embeddings are optional. Without an index file the lexical path runs alone.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60

# Weight for tables joined directly to the anchor table.
ANCHOR_BOOST = 1.6

# Table slots held back for foreign-key lookup targets.
LOOKUP_RESERVE = 4
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
NON_WORD = re.compile(r"[^A-Za-z0-9]+")

# Table-name tokens carry more signal than column tokens, so they are repeated.
TABLE_NAME_WEIGHT = 3

# Triage vocabulary that does not appear in any identifier. Support ticket wording
# ("customer never got the DXF") has to reach tables named after internal concepts.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "dxf": ("file", "filetype", "delivery", "deliverable"),
    "pdf": ("file", "filetype", "delivery"),
    "xml": ("file", "filetype", "delivery"),
    "sku": ("product", "order"),
    "skus": ("product", "order"),
    "billed": ("product", "order", "price"),
    "billing": ("product", "order", "price"),
    "charged": ("product", "order", "price"),
    "invoice": ("order", "price", "product"),
    "mail": ("email", "notification"),
    "email": ("email", "availability", "notification", "template"),
    "emailed": ("email", "availability", "delivery"),
    "notification": ("email", "availability", "template"),
    "recipient": ("email", "contact", "profile"),
    "stuck": ("status", "substatus", "workflow"),
    "pending": ("status", "substatus"),
    "processing": ("status", "substatus"),
    "completed": ("status", "substatus"),
    "timeline": ("status", "substatus", "history"),
    "history": ("status", "substatus"),
    "location": ("address", "city", "zip"),
    "property": ("address", "report"),
    "job": ("report", "order"),
    "client": ("customer", "profile"),
    "account": ("customer", "profile", "orgnode"),
    "org": ("orgnode", "organization"),
    "organisation": ("orgnode", "organization"),
    "organization": ("orgnode", "organization"),
    "measurement": ("measurement", "detail", "roof"),
    "delivered": ("delivery", "deliverable", "file"),
    "delivery": ("delivery", "deliverable", "filetype", "method"),
    "rule": ("rule", "availability", "override"),
    "disabled": ("disabled", "rule", "availability"),
    "image": ("image", "imagery"),
}

# The hub table for every triage question. Identifiers resolve through it.
ANCHOR_TABLE = "Report"

# Objects that only add noise to retrieval: search-accelerator trigram counts,
# EF migration bookkeeping, and leftover copies of real tables.
EXCLUDED_OBJECTS = (
    re.compile(r"^__"),
    re.compile(r"Trigram", re.IGNORECASE),
    re.compile(r"_Test$", re.IGNORECASE),
    re.compile(r"^ReportsTest$", re.IGNORECASE),
    re.compile(r"_(Backup|Bak|Old|Copy|Temp)$", re.IGNORECASE),
    re.compile(r"^MSchange", re.IGNORECASE),
    re.compile(r"^sysdiagrams$", re.IGNORECASE),
)

STOP_WORDS = frozenset(
    {
        "a", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by", "can",
        "check", "customer", "did", "do", "does", "for", "from", "get", "got", "has", "have",
        "he", "her", "his", "i", "if", "in", "into", "is", "it", "its", "just", "me", "need",
        "needs", "no", "not", "of", "on", "or", "our", "please", "say", "says", "see", "she",
        "should", "show", "so", "some", "still", "that", "the", "their", "them", "then",
        "there", "these", "they", "this", "to", "us", "want", "was", "we", "were", "what",
        "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
    }
)


def tokenize(text: str) -> list[str]:
    """Split prose or an identifier into lowercase word tokens.

    ``ReportFileDeliveryRule`` becomes ``[report, file, delivery, rule]`` so that
    a question about "delivery rules" can reach it lexically.
    """
    parts: list[str] = []
    for chunk in NON_WORD.split(text or ""):
        if not chunk:
            continue
        for piece in CAMEL_BOUNDARY.split(chunk):
            piece = piece.strip().casefold()
            if piece:
                parts.append(piece)
    return parts


def _singular(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _normalize(tokens: Iterable[str]) -> list[str]:
    return [_singular(token) for token in tokens]


def _segment(token: str, vocabulary: frozenset[str], min_piece: int = 3) -> list[str]:
    """Split a run-together word into known schema words, longest match first.

    A question says "substatus" but the table is ``SubStatus``, which camel-splits
    to ``sub`` + ``status``. Without segmentation the two never meet.
    """
    pieces: list[str] = []
    remainder = token
    while remainder:
        for size in range(len(remainder), min_piece - 1, -1):
            candidate = remainder[:size]
            if candidate in vocabulary:
                pieces.append(candidate)
                remainder = remainder[size:]
                break
        else:
            return []
    return pieces


def expand_query(prompt: str, vocabulary: frozenset[str] = frozenset()) -> list[str]:
    """Tokenize a question, add domain synonyms, and split run-together words."""
    expanded: list[str] = []

    def emit(token: str) -> None:
        normalized = _singular(token)
        expanded.append(normalized)
        if vocabulary and normalized not in vocabulary and len(normalized) >= 6:
            expanded.extend(_segment(normalized, vocabulary))

    for raw in tokenize(prompt):
        if raw.isdigit():
            continue
        if raw not in STOP_WORDS:
            emit(raw)
        for synonym in SYNONYMS.get(raw, ()) or SYNONYMS.get(_singular(raw), ()):
            for piece in tokenize(synonym):
                emit(piece)
    return expanded


@dataclass
class TableDocument:
    name: str
    columns: tuple[str, ...]
    tokens: tuple[str, ...]
    is_view: bool = False
    term_frequency: Counter[str] = field(default_factory=Counter)

    @property
    def length(self) -> int:
        return len(self.tokens)

    @property
    def kind(self) -> str:
        return "VIEW" if self.is_view else "TABLE"


@dataclass
class SchemaIndex:
    documents: dict[str, TableDocument]
    document_frequency: Counter[str]
    average_length: float
    foreign_keys: tuple[dict[str, str], ...]
    adjacency: dict[str, set[str]]
    embeddings: dict[str, tuple[float, ...]]
    vocabulary: frozenset[str] = frozenset()
    excluded: tuple[str, ...] = ()

    @property
    def table_count(self) -> int:
        return len(self.documents)

    @property
    def has_embeddings(self) -> bool:
        return bool(self.embeddings)

    def bm25(self, query_tokens: Sequence[str], limit: int) -> list[tuple[str, float]]:
        total_docs = len(self.documents) or 1
        scores: dict[str, float] = {}
        for token in set(query_tokens):
            matching = self.document_frequency.get(token, 0)
            if not matching:
                continue
            idf = math.log(1 + (total_docs - matching + 0.5) / (matching + 0.5))
            for name, document in self.documents.items():
                frequency = document.term_frequency.get(token, 0)
                if not frequency:
                    continue
                norm = frequency * (BM25_K1 + 1)
                denom = frequency + BM25_K1 * (
                    1 - BM25_B + BM25_B * (document.length / (self.average_length or 1))
                )
                scores[name] = scores.get(name, 0.0) + idf * (norm / denom)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]

    def vector_search(self, query_vector: Sequence[float], limit: int) -> list[tuple[str, float]]:
        if not self.embeddings or not query_vector:
            return []
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        scored: list[tuple[str, float]] = []
        for name, vector in self.embeddings.items():
            if len(vector) != len(query_vector):
                continue
            dot = sum(a * b for a, b in zip(query_vector, vector))
            magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
            scored.append((name, dot / (query_norm * magnitude)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def edges_between(self, tables: Iterable[str]) -> list[dict[str, str]]:
        selected = {name.casefold() for name in tables}
        return [
            edge
            for edge in self.foreign_keys
            if edge["parent_table"].casefold() in selected
            and edge["referenced_table"].casefold() in selected
        ]

    def neighbours(self, table: str) -> set[str]:
        return self.adjacency.get(table.casefold(), set())


def _identifier_tokens(name: str) -> list[str]:
    """Camel-split pieces plus the whole run-together form.

    Indexing both means "report status", "reportstatus", and "status" all hit
    ``ReportStatus``.
    """
    pieces = _normalize(tokenize(name))
    whole = _singular(NON_WORD.sub("", name).casefold())
    if whole and whole not in pieces:
        pieces.append(whole)
    return pieces


def _build_documents(
    tables: dict[str, list[dict[str, Any]]], views: set[str], excluded: set[str]
) -> dict[str, TableDocument]:
    documents: dict[str, TableDocument] = {}
    for name, columns in tables.items():
        if name in excluded:
            continue
        column_names = tuple(str(column["name"]) for column in columns)
        tokens = _identifier_tokens(name) * TABLE_NAME_WEIGHT
        for column_name in column_names:
            tokens.extend(_identifier_tokens(column_name))
        document = TableDocument(
            name=name,
            columns=column_names,
            tokens=tuple(tokens),
            is_view=name in views,
        )
        document.term_frequency = Counter(document.tokens)
        documents[name] = document
    return documents


@lru_cache
def load_index(environment: str = "test", server: str = "db01", database: str = "DB7222") -> SchemaIndex:
    from .planner import load_schema_pack

    pack = load_schema_pack(environment, server, database)
    folder = Path(pack["path"])

    views: set[str] = set()
    views_path = folder / "views.json"
    if views_path.is_file():
        views = set(json.loads(views_path.read_text(encoding="utf-8")).get("views", []))

    excluded = {
        name
        for name in pack["tables"]
        if any(pattern.search(name) for pattern in EXCLUDED_OBJECTS)
    }
    documents = _build_documents(pack["tables"], views, excluded)

    document_frequency: Counter[str] = Counter()
    for document in documents.values():
        document_frequency.update(set(document.tokens))
    average_length = (
        sum(document.length for document in documents.values()) / len(documents) if documents else 0.0
    )

    foreign_keys: tuple[dict[str, str], ...] = ()
    fk_path = folder / "foreign_keys.json"
    if fk_path.is_file():
        declared = json.loads(fk_path.read_text(encoding="utf-8"))
        foreign_keys = tuple({**edge, "source": "foreign-key"} for edge in declared)

    relationships_path = folder / "semantic_relationships.json"
    if relationships_path.is_file():
        reviewed = json.loads(relationships_path.read_text(encoding="utf-8")).get(
            "relationships", []
        )
        foreign_keys += tuple(reviewed)

    adjacency: dict[str, set[str]] = {}
    for edge in foreign_keys:
        parent = edge["parent_table"].casefold()
        referenced = edge["referenced_table"].casefold()
        adjacency.setdefault(parent, set()).add(edge["referenced_table"])
        adjacency.setdefault(referenced, set()).add(edge["parent_table"])

    embeddings: dict[str, tuple[float, ...]] = {}
    embedding_path = folder / "embeddings.json"
    if embedding_path.is_file():
        raw = json.loads(embedding_path.read_text(encoding="utf-8"))
        for name, vector in raw.get("vectors", {}).items():
            if name in documents:
                embeddings[name] = tuple(float(value) for value in vector)

    vocabulary = frozenset(document_frequency)

    return SchemaIndex(
        documents=documents,
        document_frequency=document_frequency,
        average_length=average_length,
        foreign_keys=foreign_keys,
        adjacency=adjacency,
        embeddings=embeddings,
        vocabulary=vocabulary,
        excluded=tuple(sorted(excluded)),
    )


def document_text(index: SchemaIndex, table: str) -> str:
    """Embedding input for one table: its name plus its column names."""
    document = index.documents[table]
    return f"Table {document.name}. Columns: {', '.join(document.columns)}."


@dataclass
class Retrieval:
    tables: list[str]
    join_paths: list[dict[str, str]]
    lexical_ranking: list[tuple[str, float]]
    vector_ranking: list[tuple[str, float]]
    strategy: str
    expanded_query: list[str]


def _fuse(rankings: Sequence[Sequence[tuple[str, float]]]) -> dict[str, float]:
    """Reciprocal rank fusion: combine rankings without comparing raw scores."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, (name, _score) in enumerate(ranking):
            fused[name] = fused.get(name, 0.0) + 1.0 / (RRF_K + position + 1)
    return fused


def retrieve_schema(
    prompt: str,
    *,
    index: SchemaIndex,
    query_vector: Sequence[float] | None = None,
    max_tables: int = 12,
    seed_pool: int = 15,
) -> Retrieval:
    """Pick a small set of tables plus the foreign keys that connect them."""
    query_tokens = expand_query(prompt, index.vocabulary)
    lexical = index.bm25(query_tokens, seed_pool)
    vector = index.vector_search(query_vector or (), seed_pool) if query_vector else []

    if lexical and vector:
        strategy = "hybrid-rrf"
    elif vector:
        strategy = "vector-only"
    elif lexical:
        strategy = "lexical-bm25"
    else:
        strategy = "anchor-fallback"

    fused = _fuse([ranking for ranking in (lexical, vector) if ranking])

    # Graph prior: every triage question routes through Report, so a table with a
    # foreign key to Report beats an unrelated table with a similar name score.
    anchor_adjacent = {name.casefold() for name in index.neighbours(ANCHOR_TABLE)}
    for name in list(fused):
        if name.casefold() in anchor_adjacent:
            fused[name] *= ANCHOR_BOOST
    ordered = [name for name, _ in sorted(fused.items(), key=lambda item: (-item[1], item[0]))]

    selected: list[str] = []
    if ANCHOR_TABLE in index.documents:
        selected.append(ANCHOR_TABLE)

    # Hold back budget so code-to-name lookup tables still fit.
    seed_budget = max(1, max_tables - LOOKUP_RESERVE)
    for name in ordered:
        if len(selected) >= seed_budget:
            break
        if name not in selected:
            selected.append(name)

    # Follow foreign keys outward so codes such as StatusID resolve to names.
    # The anchor has many unrelated lookups of its own, so a target reached only
    # from the anchor has to earn its slot with a lexical score.
    lookup_candidates: dict[str, bool] = {}
    for edge in index.foreign_keys:
        parent = edge["parent_table"]
        target = edge["referenced_table"]
        if parent not in selected or target in selected or target not in index.documents:
            continue
        from_seed = parent != ANCHOR_TABLE
        lookup_candidates[target] = lookup_candidates.get(target, False) or from_seed

    qualified = [
        name
        for name, from_seed in lookup_candidates.items()
        if from_seed or fused.get(name, 0.0) > 0
    ]
    for name in sorted(qualified, key=lambda item: (-fused.get(item, 0.0), item)):
        if len(selected) >= max_tables:
            break
        selected.append(name)

    # Any slots the lookups did not need go back to the ranked list.
    for name in ordered:
        if len(selected) >= max_tables:
            break
        if name not in selected:
            selected.append(name)

    return Retrieval(
        tables=selected,
        join_paths=index.edges_between(selected),
        lexical_ranking=lexical,
        vector_ranking=vector,
        strategy=strategy,
        expanded_query=query_tokens,
    )


def render_schema_prompt(index: SchemaIndex, tables: Sequence[str], joins: Sequence[dict[str, str]]) -> str:
    """Format the retrieved slice as the schema section of the model prompt."""
    lines: list[str] = []
    for name in tables:
        document = index.documents.get(name)
        if document is None:
            continue
        lines.append(f"{document.kind} dbo.{name}")
        lines.append(f"  COLUMNS: {', '.join(document.columns)}")
    if joins:
        lines.append("REVIEWED RELATIONSHIPS (the only join paths you may use):")
        for edge in joins:
            lines.append(
                f"  dbo.{edge['parent_table']}.{edge['parent_column']}"
                f" -> dbo.{edge['referenced_table']}.{edge['referenced_column']}"
                f" [{edge.get('source', 'unknown')}]"
            )
    else:
        lines.append("REVIEWED RELATIONSHIPS: none between these tables.")
    return "\n".join(lines)
