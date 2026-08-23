"""Load and search sanitized SQL Server metadata catalogs.

Catalog capture is offline and privileged. This runtime loader sees only the
sanitized planner projection under schema/<environment>/<node>/<database>/catalog.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_ROOT = ROOT / "schema"
REGISTRY_ROOT = ROOT / "catalog"
ALLOWED_ENVIRONMENTS = {"test"}
ALLOWED_NODES = {"db01", "db02"}
TOKEN = re.compile(r"[A-Za-z0-9]+")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(value: str) -> set[str]:
    def normalize(token: str) -> str:
        token = token.casefold()
        if len(token) > 3 and token.endswith("ies"):
            return token[:-3] + "y"
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            return token[:-1]
        return token

    output: set[str] = set()
    for raw in TOKEN.findall(value or ""):
        pieces = CAMEL.split(raw)
        output.add(normalize(raw))
        output.update(normalize(piece) for piece in pieces if piece)
    return output


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _safe_segment(value: str, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


@dataclass(frozen=True)
class DatabasePolicy:
    node: str
    database: str
    domain: str | None
    catalog_enabled: bool
    searchable: bool
    query_enabled: bool
    templates_enabled: bool
    definitions: str
    anchor_objects: tuple[str, ...] = ()
    note: str | None = None
    query_disabled_reason: str | None = None


@dataclass
class CatalogObject:
    key: str
    node: str
    database: str
    schema: str
    name: str
    object_type: str
    object_type_desc: str
    queryable: bool
    routine_evidence_only: bool
    columns: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    result_columns: list[dict[str, Any]] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    definition_excerpt: str | None = None
    definition_sha256: str | None = None
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CatalogObject":
        fields = cls.__dataclass_fields__
        return cls(**{key: value.get(key) for key in fields})

    @property
    def search_text(self) -> str:
        parts = [
            self.database,
            self.schema,
            self.name,
            self.object_type_desc,
            *self.descriptions,
            *(str(column.get("column_name", "")) for column in self.columns),
            *(str(parameter.get("parameter_name", "")) for parameter in self.parameters),
            *(str(column.get("column_name", "")) for column in self.result_columns),
            self.definition_excerpt or "",
        ]
        return " ".join(parts)


@dataclass
class CatalogDatabase:
    policy: DatabasePolicy
    manifest: dict[str, Any]
    objects: list[CatalogObject]
    relationships: list[dict[str, Any]]
    source: str = "compiled"
    semantic_model: dict[str, Any] = field(default_factory=dict)

    def search(
        self,
        prompt: str,
        *,
        limit: int = 12,
        include_evidence: bool = True,
    ) -> list[dict[str, Any]]:
        query = _tokens(prompt)
        boosts: dict[str, float] = defaultdict(float)
        for term, model in (self.semantic_model.get("business_terms") or {}).items():
            vocabulary = _tokens(term)
            for synonym in model.get("synonyms") or []:
                vocabulary |= _tokens(str(synonym))
            if not (query & vocabulary):
                continue
            for name in model.get("preferred_objects") or []:
                boosts[str(name).casefold()] += 5.0
            for name in model.get("discouraged_objects") or []:
                boosts[str(name).casefold()] -= 4.0
        ranked: list[tuple[float, CatalogObject]] = []
        for obj in self.objects:
            if not include_evidence and not obj.queryable:
                continue
            object_tokens = _tokens(obj.search_text)
            name_tokens = _tokens(f"{obj.schema} {obj.name}")
            overlap = query & object_tokens
            if not overlap:
                continue
            score = float(len(overlap)) + 2.0 * len(query & name_tokens)
            score += boosts.get(f"{obj.schema}.{obj.name}".casefold(), 0.0)
            if obj.queryable:
                score += 0.25
            ranked.append((score, obj))
        ranked.sort(key=lambda item: (-item[0], item[1].key))
        return [
            {
                "score": score,
                "key": obj.key,
                "kind": obj.object_type_desc,
                "queryable": obj.queryable,
                "evidence_only": obj.routine_evidence_only,
                "columns": [column.get("column_name") for column in obj.columns],
                "parameters": [parameter.get("parameter_name") for parameter in obj.parameters],
                "result_columns": [column.get("column_name") for column in obj.result_columns],
                "description": obj.descriptions,
            }
            for score, obj in ranked[:limit]
        ]

    def relationships_between(self, keys: Iterable[str]) -> list[dict[str, Any]]:
        selected = {key.casefold() for key in keys}
        return [
            relationship
            for relationship in self.relationships
            if str(relationship.get("source", "")).casefold() in selected
            and str(relationship.get("target", "")).casefold() in selected
        ]


@lru_cache
def load_registry(node: str, environment: str = "test") -> dict[str, Any]:
    _safe_segment(node, "node")
    if node not in ALLOWED_NODES or environment not in ALLOWED_ENVIRONMENTS:
        raise ValueError(f"Catalog node is not allowlisted: {environment}/{node}")
    path = REGISTRY_ROOT / node / "databases.yaml"
    registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    if registry.get("node") != node or registry.get("environment") != environment:
        raise ValueError(f"Registry identity mismatch: {path}")
    return registry


def database_policy(node: str, database: str, environment: str = "test") -> DatabasePolicy:
    registry = load_registry(node, environment)
    values = dict(registry.get("defaults") or {})
    values.update((registry.get("databases") or {}).get(database) or {})
    reason = None
    for pattern in registry.get("exclude_from_query_patterns") or []:
        if re.search(pattern, database):
            values["query_enabled"] = False
            reason = f"name matches {pattern}"
    return DatabasePolicy(
        node=node,
        database=database,
        domain=values.get("domain"),
        catalog_enabled=bool(values.get("catalog_enabled", True)),
        searchable=bool(values.get("searchable", True)),
        query_enabled=bool(values.get("query_enabled", False)),
        templates_enabled=bool(values.get("templates_enabled", False)),
        definitions=str(values.get("definitions", "evidence_only")),
        anchor_objects=tuple(values.get("anchor_objects") or ()),
        note=values.get("note"),
        query_disabled_reason=reason or values.get("query_disabled_reason"),
    )


def list_catalog_databases(environment: str = "test") -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for node in sorted(ALLOWED_NODES):
        registry = load_registry(node, environment)
        compiled_path = SCHEMA_ROOT / environment / node / "catalog.manifest.json"
        compiled = _read_json(compiled_path).get("databases", {}) if compiled_path.is_file() else {}
        names = set((registry.get("databases") or {})) | set(compiled)
        for database in sorted(names):
            policy = database_policy(node, database, environment)
            legacy_compiled = (
                node == "db01"
                and database == "DB7222"
                and (SCHEMA_ROOT / environment / node / database / "manifest.json").is_file()
            )
            output.append(
                {
                    "environment": environment,
                    "node": node,
                    "database": database,
                    "domain": policy.domain,
                    "catalog_enabled": policy.catalog_enabled,
                    "searchable": policy.searchable,
                    "query_enabled": policy.query_enabled,
                    "templates_enabled": policy.templates_enabled,
                    "compiled": database in compiled or legacy_compiled,
                    "catalog": compiled.get(database),
                    "note": policy.note,
                    "query_disabled_reason": policy.query_disabled_reason,
                }
            )
    return output


def _legacy_db7222(environment: str, node: str, database: str) -> CatalogDatabase:
    """Adapter for the existing pack while the full capture is being established."""
    folder = SCHEMA_ROOT / environment / node / database
    tables = _read_json(folder / "tables.json")
    view_names = set(_read_json(folder / "views.json").get("views", [])) if (folder / "views.json").is_file() else set()
    policy = database_policy(node, database, environment)
    objects = [
        CatalogObject(
            key=f"{database}.dbo.{name}",
            node=node,
            database=database,
            schema="dbo",
            name=name,
            object_type="V" if name in view_names else "U",
            object_type_desc="VIEW" if name in view_names else "USER_TABLE",
            queryable=policy.query_enabled,
            routine_evidence_only=False,
            columns=[{"column_name": column["name"], **column} for column in columns],
        )
        for name, columns in tables.items()
    ]
    relationships = []
    fk_path = folder / "foreign_keys.json"
    if fk_path.is_file():
        for edge in _read_json(fk_path):
            relationships.append(
                {
                    "source": f"{database}.dbo.{edge['parent_table']}",
                    "source_column": edge["parent_column"],
                    "target": f"{database}.dbo.{edge['referenced_table']}",
                    "target_column": edge["referenced_column"],
                    "relationship": "foreign_key",
                    "confidence": "catalog",
                    "join_authorized": True,
                }
            )
    semantic_path = folder / "semantic_relationships.json"
    if semantic_path.is_file():
        for edge in _read_json(semantic_path).get("relationships", []):
            relationships.append(
                {
                    "source": f"{database}.dbo.{edge['parent_table']}",
                    "source_column": edge["parent_column"],
                    "target": f"{database}.dbo.{edge['referenced_table']}",
                    "target_column": edge["referenced_column"],
                    "relationship": "semantic",
                    "confidence": edge.get("source", "domain-reviewed"),
                    "join_authorized": True,
                }
            )
    return CatalogDatabase(
        policy=policy,
        manifest=_read_json(folder / "manifest.json"),
        objects=objects,
        relationships=relationships,
        source="legacy-adapter",
        semantic_model=load_semantic_model(node, database),
    )


@lru_cache
def load_semantic_model(node: str, database: str) -> dict[str, Any]:
    path = REGISTRY_ROOT / node / "semantic_model.yaml"
    if not path.is_file():
        return {}
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    if model.get("node") != node or model.get("database") != database:
        return {}
    return model


@lru_cache
def load_catalog_database(
    node: str,
    database: str,
    environment: str = "test",
    *,
    require_query_enabled: bool = False,
) -> CatalogDatabase:
    _safe_segment(database, "database")
    policy = database_policy(node, database, environment)
    if not policy.catalog_enabled:
        raise ValueError(f"Catalog is disabled for {node}/{database}")
    if require_query_enabled and not policy.query_enabled:
        raise ValueError(f"Query generation is disabled for {node}/{database}")

    folder = SCHEMA_ROOT / environment / node / database / "catalog"
    if (folder / "catalog.manifest.json").is_file():
        return CatalogDatabase(
            policy=policy,
            manifest=_read_json(folder / "catalog.manifest.json"),
            objects=[CatalogObject.from_dict(value) for value in _read_ndjson(folder / "objects.ndjson")],
            relationships=_read_ndjson(folder / "relationships.ndjson"),
            semantic_model=load_semantic_model(node, database),
        )
    if node == "db01" and database == "DB7222":
        return _legacy_db7222(environment, node, database)
    raise FileNotFoundError(f"No compiled catalog pack for {environment}/{node}/{database}")


def search_catalog(
    prompt: str,
    *,
    environment: str = "test",
    node: str | None = None,
    database: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    candidates = list_catalog_databases(environment)
    if node:
        candidates = [item for item in candidates if item["node"] == node]
    if database:
        candidates = [item for item in candidates if item["database"].casefold() == database.casefold()]

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for candidate in candidates:
        if not candidate["searchable"]:
            continue
        try:
            catalog = load_catalog_database(
                candidate["node"], candidate["database"], environment
            )
        except (FileNotFoundError, ValueError) as error:
            errors.append(
                {
                    "node": candidate["node"],
                    "database": candidate["database"],
                    "error": str(error),
                }
            )
            continue
        for match in catalog.search(prompt, limit=limit):
            results.append(
                {
                    "node": candidate["node"],
                    "database": candidate["database"],
                    "query_enabled": candidate["query_enabled"],
                    **match,
                }
            )
    results.sort(key=lambda item: (-item["score"], item["node"], item["database"], item["key"]))
    return {
        "prompt": prompt,
        "results": results[:limit],
        "candidate_databases": len(candidates),
        "errors": errors,
    }
