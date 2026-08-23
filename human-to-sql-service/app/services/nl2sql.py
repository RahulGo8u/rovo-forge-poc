"""Generate read-only T-SQL from a natural-language triage question.

Flow: retrieve a schema slice (RAG) -> ask Gemini for SQL -> re-parse and reject
anything unsafe. The model is never trusted; the validator is the gate. Nothing
is executed here, the SQL is returned for a caller to run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlglot import exp, parse

from ..config import settings
from . import gemini
from .planner import load_schema_pack, validate_read_only_sql
from .schema_index import (
    Retrieval,
    SchemaIndex,
    load_index,
    render_schema_prompt,
    retrieve_schema,
)

PARAMETER_COLUMNS = {
    "report_id": ("ReportID", "@ReportID", "dbo.Report.ReportID"),
    "order_id": ("OrderID", "@OrderID", "dbo.Report.OrderID"),
    "customer_id": ("CustomerID", "@CustomerID", "dbo.Report.CustomerID"),
    "organization_node_id": ("OrganizationNodeID", "@OrganizationNodeID", "dbo.Report.OrgNodeID"),
    "profile_id": ("ProfileID", "@ProfileID", "dbo.Report.CustomerID (profile FK)"),
}

# Long bare numbers in generated SQL almost always mean an inlined identifier,
# which defeats parameterisation and plan reuse.
INLINE_ID_LITERAL = re.compile(r"(?<![\w.@])\d{5,}(?![\w.])")

SYSTEM_INSTRUCTION = """\
You are a SQL generator for a read-only support triage tool at a property measurement company.
You write Microsoft SQL Server (T-SQL) SELECT statements and nothing else.

Hard rules:
1. Emit exactly one statement. It must be a SELECT, or a WITH followed by a SELECT.
2. Never emit INSERT, UPDATE, DELETE, MERGE, TRUNCATE, DDL, SELECT INTO, EXEC, or dynamic SQL.
3. Use only the tables listed in the SCHEMA section, always schema-qualified as dbo.<Table>.
4. Use only the columns listed for those tables. Never invent a column.
5. Only join on edges listed under REVIEWED RELATIONSHIPS. Similar column names are
   not enough; if an edge is absent, do not make that join.
6. Every statement must include a row cap via SELECT TOP (n).
7. Filter using the bound parameters listed under PARAMETERS, for example @ReportID.
   Never inline a literal identifier value.
8. Select named columns. Never use SELECT *.
9. Prefer joining lookup tables so codes come back with human-readable names.
10. Add an ORDER BY that makes the result readable, newest first for time series.
11. Keep the query focused: return no more than 15 result columns and use the
    shortest schema-supported join path that directly answers the question.
12. A table whose name directly describes the requested business concept is
    preferable to a broader table that merely has similarly named columns.

If the question cannot be answered with the given tables and columns, set sql to an
empty string and explain why in the notes field. Do not guess.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string"},
        "notes": {"type": "string"},
        "tables_used": {"type": "array", "items": {"type": "string"}},
        "answerable": {"type": "boolean"},
    },
    "required": ["sql", "notes", "answerable"],
}


def _identifier_map(
    report_id: int | None,
    order_id: int | None,
    customer_id: int | None,
    organization_node_id: int | None,
    profile_id: int | None,
) -> dict[str, int]:
    supplied = {
        "report_id": report_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "organization_node_id": organization_node_id,
        "profile_id": profile_id,
    }
    params: dict[str, int] = {}
    for key, value in supplied.items():
        if value is not None:
            params[PARAMETER_COLUMNS[key][0]] = int(value)
    return params


def _render_parameters(params: dict[str, int]) -> str:
    if not params:
        return "PARAMETERS: none supplied. Do not filter on an identifier you were not given."
    lines = ["PARAMETERS (bind these, never inline the values):"]
    for key, (name, placeholder, column) in PARAMETER_COLUMNS.items():
        if name in params:
            lines.append(f"  {placeholder} (int) filters {column}")
    return "\n".join(lines)


def build_prompt(
    question: str,
    *,
    index: SchemaIndex,
    retrieval: Retrieval,
    params: dict[str, int],
    row_limit: int,
    gold_examples: list[dict[str, Any]] | None = None,
) -> str:
    schema_block = render_schema_prompt(index, retrieval.tables, retrieval.join_paths)
    sections = [
        f"QUESTION:\n{question}",
        f"SCHEMA:\n{schema_block}",
        _render_parameters(params),
    ]
    if gold_examples:
        sections.append(
            "REVIEWED GOLD EXAMPLES (prefer these joins and business meanings):\n"
            + "\n\n".join(
                f"Example question: {example['question']}\n"
                f"Reviewed SQL:\n{example['sql']}"
                for example in gold_examples
            )
        )
    sections.append(f"ROW CAP: use SELECT TOP (n) with n no greater than {row_limit}.")
    return "\n\n".join(sections)


def _retrieve_gold_examples(pack_path: str, question: str, limit: int = 3) -> list[dict[str, Any]]:
    path = Path(pack_path) / "gold_examples.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    query_tokens = set(re.findall(r"[a-z0-9]+", question.casefold()))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for example in payload.get("examples") or []:
        example_tokens = set(re.findall(r"[a-z0-9]+", str(example.get("question", "")).casefold()))
        overlap = query_tokens & example_tokens
        if not overlap:
            continue
        score = len(overlap) / max(1, len(query_tokens | example_tokens))
        ranked.append((score, example))
    ranked.sort(key=lambda item: (-item[0], item[1].get("question", "")))
    return [example for _, example in ranked[:limit]]


def _columns_by_table(pack_tables: dict[str, list[dict[str, Any]]], tables: list[str]) -> dict[str, set[str]]:
    return {
        name.casefold(): {str(column["name"]).casefold() for column in pack_tables.get(name, [])}
        for name in tables
    }


def _validate_columns(sql: str, allowed: dict[str, set[str]]) -> None:
    """Reject hallucinated columns by resolving each reference against the pack."""
    statement = parse(sql, read="tsql")[0]

    alias_to_table: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        key = table.name.casefold()
        alias_to_table[key] = key
        if table.alias:
            alias_to_table[table.alias.casefold()] = key

    every_column: set[str] = set()
    for columns in allowed.values():
        every_column |= columns

    # Names introduced by the query itself (aliases, CTEs) are not base columns.
    local_names = {
        alias.alias.casefold()
        for alias in statement.find_all(exp.Alias)
        if alias.alias
    }
    local_names |= {
        cte.alias.casefold() for cte in statement.find_all(exp.CTE) if cte.alias
    }

    unknown: set[str] = set()
    for column in statement.find_all(exp.Column):
        name = column.name.casefold()
        if not name or name == "*":
            continue
        qualifier = column.table.casefold() if column.table else ""
        if qualifier:
            table_key = alias_to_table.get(qualifier)
            if table_key is None:
                unknown.add(f"{column.table}.{column.name}")
                continue
            if name not in allowed.get(table_key, set()) and name not in local_names:
                unknown.add(f"{column.table}.{column.name}")
        elif name not in every_column and name not in local_names:
            unknown.add(column.name)

    if unknown:
        raise ValueError(f"SQL references columns that do not exist: {sorted(unknown)}")


def _validate_row_cap(sql: str, row_limit: int) -> int:
    statement = parse(sql, read="tsql")[0]
    limit = statement.find(exp.Limit)
    if limit is None:
        raise ValueError("Generated SQL must include a SELECT TOP (n) row cap")
    expression = limit.expression
    try:
        value = int(expression.name)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Row cap must be a literal integer") from None
    if value < 1 or value > row_limit:
        raise ValueError(f"Row cap {value} is outside the allowed range 1..{row_limit}")
    return value


def _relationship_key(
    left_table: str,
    left_column: str,
    right_table: str,
    right_column: str,
) -> frozenset[tuple[str, str]]:
    return frozenset(
        {
            (left_table.casefold(), left_column.casefold()),
            (right_table.casefold(), right_column.casefold()),
        }
    )


def _validate_joins(sql: str, relationships: list[dict[str, str]]) -> None:
    """Require every cross-table equality in JOIN...ON to be reviewed.

    Existing-column checks cannot catch a plausible but false edge such as
    Report.CatID = Product.ProductID. This graph check can.
    """
    statement = parse(sql, read="tsql")[0]
    alias_to_table: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        name = table.name.casefold()
        alias_to_table[name] = name
        if table.alias:
            alias_to_table[table.alias.casefold()] = name

    allowed = {
        _relationship_key(
            edge["parent_table"],
            edge["parent_column"],
            edge["referenced_table"],
            edge["referenced_column"],
        )
        for edge in relationships
    }

    for join in statement.find_all(exp.Join):
        target = join.this
        if not isinstance(target, exp.Table):
            raise ValueError("Generated SQL may only join directly to reviewed tables")
        target_alias = (target.alias or target.name).casefold()
        target_table = target.name.casefold()
        on = join.args.get("on")
        if on is None:
            raise ValueError(f"JOIN to {target.name} has no ON relationship")

        connected = False
        for equality in on.find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            left_table = alias_to_table.get(left.table.casefold()) if left.table else None
            right_table = alias_to_table.get(right.table.casefold()) if right.table else None
            if not left_table or not right_table or left_table == right_table:
                continue

            relationship = _relationship_key(
                left_table, left.name, right_table, right.name
            )
            if relationship not in allowed:
                raise ValueError(
                    "SQL uses an unreviewed join: "
                    f"{left_table}.{left.name} = {right_table}.{right.name}"
                )
            if (
                left.table.casefold() == target_alias
                or right.table.casefold() == target_alias
                or left_table == target_table
                or right_table == target_table
            ):
                connected = True

        if not connected:
            raise ValueError(
                f"JOIN to {target.name} is not connected by a reviewed relationship"
            )


def validate_generated_sql(
    sql: str,
    *,
    allowed_tables: list[str],
    allowed_relationships: list[dict[str, str]],
    pack_tables: dict[str, list[dict[str, Any]]],
    params: dict[str, int],
    row_limit: int,
) -> dict[str, Any]:
    if INLINE_ID_LITERAL.search(sql):
        raise ValueError("Generated SQL inlines a literal identifier; it must bind a parameter instead")
    safety = validate_read_only_sql(
        sql,
        allowed_tables=allowed_tables,
        params=params,
        require_exact_params=False,
    )
    _validate_columns(sql, _columns_by_table(pack_tables, allowed_tables))
    _validate_joins(sql, allowed_relationships)
    safety["row_cap"] = _validate_row_cap(sql, row_limit)
    safety["columns_verified"] = True
    safety["joins_verified"] = True
    return safety


def generate_sql(
    *,
    prompt: str,
    report_id: int | None = None,
    order_id: int | None = None,
    customer_id: int | None = None,
    organization_node_id: int | None = None,
    profile_id: int | None = None,
    environment: str = "test",
    server: str = "db01",
    database: str = "DB7222",
    max_tables: int | None = None,
) -> dict[str, Any]:
    if server != "db01" or database != "DB7222":
        from .catalog_nl2sql import generate_catalog_sql

        return generate_catalog_sql(
            prompt=prompt,
            report_id=report_id,
            order_id=order_id,
            customer_id=customer_id,
            organization_node_id=organization_node_id,
            profile_id=profile_id,
            environment=environment,
            server=server,
            database=database,
            max_tables=max_tables,
        )
    pack = load_schema_pack(environment, server, database)
    index = load_index(environment, server, database)
    question = (prompt or "").strip()
    if not question:
        return {"ok": False, "mode": "error", "error": "Prompt is required."}

    params = _identifier_map(report_id, order_id, customer_id, organization_node_id, profile_id)

    query_vector: list[float] | None = None
    embedding_error: str | None = None
    if index.has_embeddings and gemini.is_configured():
        try:
            query_vector = gemini.embed(question, task_type="RETRIEVAL_QUERY")
        except gemini.GeminiError as error:
            embedding_error = str(error)

    retrieval = retrieve_schema(
        question,
        index=index,
        query_vector=query_vector,
        max_tables=max_tables or settings.nl2sql_max_tables,
    )

    retrieval_report = {
        "strategy": retrieval.strategy,
        "tables": retrieval.tables,
        "join_paths": retrieval.join_paths,
        "expanded_query": retrieval.expanded_query,
        "top_lexical": [{"table": name, "score": round(score, 4)} for name, score in retrieval.lexical_ranking[:8]],
        "embeddings_available": index.has_embeddings,
        "embedding_error": embedding_error,
        "candidate_pool": index.table_count,
    }
    gold_examples = _retrieve_gold_examples(pack["path"], question)
    retrieval_report["gold_examples"] = [
        {"question": example["question"], "intent": example["intent"]}
        for example in gold_examples
    ]

    model_prompt = build_prompt(
        question,
        index=index,
        retrieval=retrieval,
        params=params,
        row_limit=settings.nl2sql_row_limit,
        gold_examples=gold_examples,
    )

    try:
        answer, meta = gemini.generate_json(
            system_instruction=SYSTEM_INSTRUCTION,
            prompt=model_prompt,
            response_schema=RESPONSE_SCHEMA,
        )
    except gemini.GeminiNotConfigured as error:
        return {
            "ok": False,
            "mode": "not_configured",
            "error": str(error),
            "retrieval": retrieval_report,
        }
    except gemini.GeminiError as error:
        return {"ok": False, "mode": "model_error", "error": str(error), "retrieval": retrieval_report}

    sql = (answer.get("sql") or "").strip().rstrip(";")
    if not answer.get("answerable", True) or not sql:
        return {
            "ok": False,
            "mode": "not_answerable",
            "error": answer.get("notes") or "The model could not answer this from the retrieved schema.",
            "retrieval": retrieval_report,
            "model": meta,
        }
    sql = f"{sql};"

    attempts = [{"kind": "generate", **meta}]
    repaired = False
    try:
        safety = validate_generated_sql(
            sql,
            allowed_tables=retrieval.tables,
            allowed_relationships=retrieval.join_paths,
            pack_tables=pack["tables"],
            params=params,
            row_limit=settings.nl2sql_row_limit,
        )
    except ValueError as first_error:
        repair_prompt = (
            f"{model_prompt}\n\n"
            "REPAIR THE REJECTED SQL ONCE.\n"
            f"Rejected SQL:\n{sql}\n"
            f"Deterministic validator error:\n{first_error}\n"
            "Return a corrected answer using only the original catalog. If it cannot "
            "be corrected, set answerable=false. Do not defend the rejected SQL."
        )
        try:
            repaired_answer, repair_meta = gemini.generate_json(
                system_instruction=SYSTEM_INSTRUCTION,
                prompt=repair_prompt,
                response_schema=RESPONSE_SCHEMA,
            )
            attempts.append({"kind": "repair", "validator_error": str(first_error), **repair_meta})
            repaired_sql = (repaired_answer.get("sql") or "").strip().rstrip(";")
            if not repaired_answer.get("answerable", True) or not repaired_sql:
                raise ValueError(repaired_answer.get("notes") or "Model declined repair")
            repaired_sql += ";"
            safety = validate_generated_sql(
                repaired_sql,
                allowed_tables=retrieval.tables,
                allowed_relationships=retrieval.join_paths,
                pack_tables=pack["tables"],
                params=params,
                row_limit=settings.nl2sql_row_limit,
            )
            sql = repaired_sql
            answer = repaired_answer
            repaired = True
        except (gemini.GeminiError, ValueError) as repair_error:
            return {
                "ok": False,
                "mode": "rejected",
                "error": str(first_error),
                "repair_error": str(repair_error),
                "rejected_sql": sql,
                "retrieval": retrieval_report,
                "model_attempts": attempts,
            }

    return {
        "ok": True,
        "mode": "generated",
        "sql": sql,
        "params": params,
        "notes": answer.get("notes"),
        "tables_used": sorted(safety["tables"]),
        "safety": safety,
        "retrieval": retrieval_report,
        "model": meta,
        "model_attempts": attempts,
        "repaired": repaired,
        "schema": pack["manifest"],
        "execution": "not_run",
        "note": "SQL was generated and validated but not executed.",
    }
