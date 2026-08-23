"""Generate SQL from a compiled multi-database catalog pack."""
from __future__ import annotations

from typing import Any

from sqlglot import exp, parse

from ..config import settings
from . import gemini
from .catalog import CatalogDatabase, CatalogObject, load_catalog_database
from .nl2sql import (
    INLINE_ID_LITERAL,
    PARAMETER_COLUMNS,
    RESPONSE_SCHEMA,
    SYSTEM_INSTRUCTION,
    _identifier_map,
    _render_parameters,
    _validate_row_cap,
)


CATALOG_SYSTEM_INSTRUCTION = SYSTEM_INSTRUCTION.replace(
    "always schema-qualified as dbo.<Table>",
    "always schema-qualified as <schema>.<Table>; use no server or database qualifier",
) + """
13. PROCEDURE, FUNCTION, and TRIGGER entries are evidence only. Never EXEC or invoke them.
14. A dependency edge explains existing code but does not authorize a JOIN.
15. Query only entries explicitly marked QUERYABLE.
"""


def _object_block(obj: CatalogObject) -> str:
    kind = "VIEW" if obj.object_type == "V" else "TABLE"
    columns = ", ".join(
        f"{column.get('column_name')} {column.get('type_name')}"
        for column in obj.columns
        if column.get("column_name")
    )
    return f"{kind} {obj.schema}.{obj.name} [QUERYABLE]\n  COLUMNS: {columns}"


def _evidence_block(obj: CatalogObject) -> str:
    parameters = ", ".join(
        str(parameter.get("parameter_name"))
        for parameter in obj.parameters
        if parameter.get("parameter_name")
    )
    result_columns = ", ".join(
        str(column.get("column_name"))
        for column in obj.result_columns
        if column.get("column_name")
    )
    excerpt = (obj.definition_excerpt or "")[:2000]
    return (
        f"EVIDENCE {obj.schema}.{obj.name} {obj.object_type_desc} [NOT QUERYABLE]\n"
        f"  PARAMETERS: {parameters or 'none'}\n"
        f"  FIRST RESULT: {result_columns or 'unknown'}\n"
        f"  DEFINITION EXCERPT: {excerpt or 'unavailable'}"
    )


def _relationship_block(relationship: dict[str, Any], database: str) -> str | None:
    if not relationship.get("join_authorized"):
        return None
    source = str(relationship["source"]).split(".", 1)[-1]
    target = str(relationship["target"]).split(".", 1)[-1]
    return (
        f"{source}.{relationship['source_column']} -> "
        f"{target}.{relationship['target_column']} "
        f"[{relationship.get('confidence', 'catalog')}]"
    )


def _validate_catalog_sql(
    sql: str,
    *,
    catalog: CatalogDatabase,
    selected: list[CatalogObject],
    params: dict[str, int],
) -> dict[str, Any]:
    if INLINE_ID_LITERAL.search(sql):
        raise ValueError("Generated SQL inlines a literal identifier; bind a parameter")
    statements = parse(sql, read="tsql")
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("Exactly one SELECT or WITH...SELECT is allowed")
    statement = statements[0]
    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Merge,
        exp.Create,
        exp.Drop,
        exp.Alter,
        exp.Command,
        exp.Into,
    )
    if any(statement.find(node) is not None for node in forbidden):
        raise ValueError("SQL contains a forbidden write, DDL, command, or SELECT INTO")
    if statement.find(exp.Star) is not None:
        raise ValueError("SELECT * is not allowed")

    allowed_objects = {
        (obj.schema.casefold(), obj.name.casefold()): obj
        for obj in selected
        if obj.queryable
    }
    aliases: dict[str, tuple[str, str]] = {}
    used: set[tuple[str, str]] = set()
    for table in statement.find_all(exp.Table):
        if table.catalog:
            raise ValueError("Generated SQL may not use cross-database or linked-server names")
        identity = ((table.db or "dbo").casefold(), table.name.casefold())
        if identity not in allowed_objects:
            raise ValueError(f"SQL references a non-queryable catalog object: {table.sql()}")
        used.add(identity)
        aliases[table.name.casefold()] = identity
        if table.alias:
            aliases[table.alias.casefold()] = identity

    local_names = {
        alias.alias.casefold()
        for alias in statement.find_all(exp.Alias)
        if alias.alias
    }
    allowed_columns = {
        identity: {
            str(column.get("column_name", "")).casefold()
            for column in obj.columns
        }
        for identity, obj in allowed_objects.items()
    }
    unknown: set[str] = set()
    for column in statement.find_all(exp.Column):
        if column.name == "*":
            raise ValueError("SELECT * is not allowed")
        name = column.name.casefold()
        if name in local_names:
            continue
        if column.table:
            identity = aliases.get(column.table.casefold())
            if identity is None or name not in allowed_columns.get(identity, set()):
                unknown.add(column.sql())
        elif not any(name in columns for identity, columns in allowed_columns.items() if identity in used):
            unknown.add(column.name)
    if unknown:
        raise ValueError(f"SQL references columns that do not exist: {sorted(unknown)}")

    authorized = {
        frozenset(
            {
                (
                    ".".join(str(edge["source"]).split(".")[-2:]).casefold(),
                    str(edge["source_column"]).casefold(),
                ),
                (
                    ".".join(str(edge["target"]).split(".")[-2:]).casefold(),
                    str(edge["target_column"]).casefold(),
                ),
            }
        )
        for edge in catalog.relationships
        if edge.get("join_authorized")
    }
    for join in statement.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            raise ValueError("Every JOIN must use a reviewed relationship")
        matched = False
        for equality in on.find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            left_identity = aliases.get(left.table.casefold()) if left.table else None
            right_identity = aliases.get(right.table.casefold()) if right.table else None
            if not left_identity or not right_identity:
                continue
            edge = frozenset(
                {
                    (f"{left_identity[0]}.{left_identity[1]}", left.name.casefold()),
                    (f"{right_identity[0]}.{right_identity[1]}", right.name.casefold()),
                }
            )
            if edge not in authorized:
                raise ValueError(
                    f"SQL uses an unreviewed join: {left.sql()} = {right.sql()}"
                )
            matched = True
        if not matched:
            raise ValueError("JOIN is not connected by a reviewed relationship")

    actual_params = {node.name.casefold() for node in statement.find_all(exp.Parameter)}
    supplied_params = {name.casefold() for name in params}
    if not actual_params.issubset(supplied_params):
        raise ValueError(
            f"SQL references parameters that were not supplied: {sorted(actual_params - supplied_params)}"
        )
    cap = _validate_row_cap(sql, settings.nl2sql_row_limit)
    return {
        "read_only": True,
        "single_statement": True,
        "objects": sorted(f"{schema}.{name}" for schema, name in used),
        "parameters": sorted(actual_params),
        "row_limited": True,
        "row_cap": cap,
        "columns_verified": True,
        "joins_verified": True,
        "catalog_verified": True,
    }


def generate_catalog_sql(
    *,
    prompt: str,
    report_id: int | None = None,
    order_id: int | None = None,
    customer_id: int | None = None,
    organization_node_id: int | None = None,
    profile_id: int | None = None,
    environment: str = "test",
    server: str,
    database: str,
    max_tables: int | None = None,
) -> dict[str, Any]:
    question = (prompt or "").strip()
    if not question:
        return {"ok": False, "mode": "error", "error": "Prompt is required."}
    try:
        catalog = load_catalog_database(
            server,
            database,
            environment,
            require_query_enabled=True,
        )
    except (FileNotFoundError, ValueError) as error:
        return {
            "ok": False,
            "mode": "catalog_unavailable",
            "error": str(error),
            "catalog": {"environment": environment, "node": server, "database": database},
        }

    matches = catalog.search(
        question,
        limit=max_tables or settings.nl2sql_max_tables,
        include_evidence=True,
    )
    by_key = {obj.key: obj for obj in catalog.objects}
    selected = [by_key[match["key"]] for match in matches if match["key"] in by_key]
    if not any(obj.queryable for obj in selected):
        return {
            "ok": False,
            "mode": "not_answerable",
            "error": "No queryable table or view matched the prompt in this database.",
            "retrieval": {"matches": matches},
        }

    selected_keys = [obj.key for obj in selected]
    relationships = catalog.relationships_between(selected_keys)
    schema_lines = [
        _object_block(obj) if obj.queryable else _evidence_block(obj)
        for obj in selected
    ]
    relationship_lines = [
        line
        for line in (
            _relationship_block(relationship, database)
            for relationship in relationships
        )
        if line
    ]
    schema_lines.append("REVIEWED RELATIONSHIPS (the only allowed JOIN edges):")
    schema_lines.extend(relationship_lines or ["  none"])
    params = _identifier_map(
        report_id,
        order_id,
        customer_id,
        organization_node_id,
        profile_id,
    )
    model_prompt = "\n\n".join(
        [
            f"TARGET: node={server}, database={database}. Do not qualify the database in SQL.",
            f"QUESTION:\n{question}",
            "CATALOG:\n" + "\n".join(schema_lines),
            _render_parameters(params),
            f"ROW CAP: TOP (n), n <= {settings.nl2sql_row_limit}.",
        ]
    )
    retrieval = {
        "strategy": "catalog-lexical",
        "node": server,
        "database": database,
        "matches": matches,
        "relationships": relationships,
        "candidate_pool": len(catalog.objects),
        "source": catalog.source,
    }
    try:
        answer, meta = gemini.generate_json(
            system_instruction=CATALOG_SYSTEM_INSTRUCTION,
            prompt=model_prompt,
            response_schema=RESPONSE_SCHEMA,
        )
    except gemini.GeminiNotConfigured as error:
        return {"ok": False, "mode": "not_configured", "error": str(error), "retrieval": retrieval}
    except gemini.GeminiError as error:
        return {"ok": False, "mode": "model_error", "error": str(error), "retrieval": retrieval}

    sql = (answer.get("sql") or "").strip().rstrip(";")
    if not answer.get("answerable", True) or not sql:
        return {
            "ok": False,
            "mode": "not_answerable",
            "error": answer.get("notes") or "The model could not answer from the catalog.",
            "retrieval": retrieval,
            "model": meta,
        }
    sql += ";"
    try:
        safety = _validate_catalog_sql(
            sql,
            catalog=catalog,
            selected=selected,
            params=params,
        )
    except ValueError as error:
        return {
            "ok": False,
            "mode": "rejected",
            "error": str(error),
            "rejected_sql": sql,
            "retrieval": retrieval,
            "model": meta,
        }
    return {
        "ok": True,
        "mode": "generated",
        "sql": sql,
        "params": params,
        "notes": answer.get("notes"),
        "objects_used": safety["objects"],
        "safety": safety,
        "retrieval": retrieval,
        "model": meta,
        "catalog": {
            "environment": environment,
            "node": server,
            "database": database,
            "fingerprint": catalog.manifest.get("fingerprint"),
        },
        "execution": "not_run",
        "note": "SQL was generated and catalog-validated but not executed.",
    }
