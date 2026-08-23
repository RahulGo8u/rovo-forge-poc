"""Compile protected SQL Server captures into sanitized planner packs.

Raw definitions stay under .catalog-captures. The compiler publishes only
redacted excerpts, hashes, object metadata, and relationship evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
CAPTURE_ROOT = ROOT / ".catalog-captures"
SCHEMA_ROOT = ROOT / "schema"
CATALOG_ROOT = ROOT / "catalog"
COMPILER_VERSION = "1.0.0"
QUERYABLE_TYPES = {"U", "V"}
ROUTINE_TYPES = {"P", "PC", "FN", "IF", "TF", "FS", "FT"}
DEFINITION_EXCERPT_LIMIT = 8000

SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(password|pwd|secret|api[_ -]?key|access[_ -]?key|token)\s*=\s*"
        r"(?:'[^']*'|\"[^\"]*\"|[^;\s,\)]+)"
    ),
    re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_ndjson(path: Path, values: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    sha = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            line = canonical(value)
            handle.write(line + "\n")
            sha.update((line + "\n").encode("utf-8"))
            count += 1
    return {"file": path.name, "row_count": count, "sha256": sha.hexdigest()}


def redact_definition(definition: str | None) -> tuple[str | None, int]:
    if not definition:
        return None, 0
    redacted = definition
    matches = 0
    for pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(lambda match: f"{match.group(1) if match.lastindex else 'secret'}=[REDACTED]", redacted)
        matches += count
    return redacted[:DEFINITION_EXCERPT_LIMIT], matches


def registry_for(node: str) -> dict[str, Any]:
    path = CATALOG_ROOT / node / "databases.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing database registry: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def database_policy(registry: dict[str, Any], database: str) -> dict[str, Any]:
    policy = dict(registry.get("defaults") or {})
    policy.update((registry.get("databases") or {}).get(database) or {})
    for raw_pattern in registry.get("exclude_from_query_patterns") or []:
        if re.search(raw_pattern, database):
            policy["query_enabled"] = False
            policy["query_disabled_reason"] = f"name matches {raw_pattern}"
    return policy


def object_key(database: str, schema: str, name: str) -> str:
    return f"{database}.{schema}.{name}"


def group_by(rows: Iterable[dict[str, Any]], key: str) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value is not None:
            grouped[int(value)].append(row)
    return grouped


def compile_database(
    *,
    source: Path,
    target: Path,
    node: str,
    database: str,
    policy: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    raw_manifest = read_json(source / "catalog.manifest.json")
    objects = read_ndjson(source / "objects.ndjson")
    columns = group_by(read_ndjson(source / "columns.ndjson"), "object_id")
    modules = {int(row["object_id"]): row for row in read_ndjson(source / "modules.ndjson")}
    parameters = group_by(read_ndjson(source / "parameters.ndjson"), "object_id")
    result_sets = group_by(read_ndjson(source / "result_sets.ndjson"), "object_id")
    indexes = group_by(read_ndjson(source / "indexes.ndjson"), "object_id")
    dependencies = group_by(read_ndjson(source / "dependencies.ndjson"), "referencing_id")
    extended = group_by(read_ndjson(source / "extended_properties.ndjson"), "major_id")

    documents: list[dict[str, Any]] = []
    redaction_count = 0
    for obj in objects:
        object_id = int(obj["object_id"])
        schema = str(obj["schema_name"])
        name = str(obj["object_name"])
        module = modules.get(object_id) or {}
        excerpt, redactions = redact_definition(module.get("definition"))
        redaction_count += redactions

        object_columns = [
            {
                key: row.get(key)
                for key in (
                    "column_id",
                    "column_name",
                    "type_schema",
                    "type_name",
                    "max_length",
                    "precision",
                    "scale",
                    "is_nullable",
                    "is_identity",
                    "is_computed",
                    "computed_definition",
                    "default_definition",
                    "is_encrypted",
                )
            }
            for row in columns.get(object_id, [])
        ]
        object_parameters = [
            {
                key: row.get(key)
                for key in (
                    "parameter_id",
                    "parameter_name",
                    "type_schema",
                    "type_name",
                    "max_length",
                    "precision",
                    "scale",
                    "is_output",
                    "has_default_value",
                    "is_readonly",
                )
            }
            for row in parameters.get(object_id, [])
        ]
        result_columns = [
            {
                key: row.get(key)
                for key in (
                    "column_ordinal",
                    "column_name",
                    "system_type_name",
                    "is_nullable",
                    "source_database",
                    "source_schema",
                    "source_table",
                    "source_column",
                    "discoverable",
                    "error_number",
                    "error_message",
                )
            }
            for row in result_sets.get(object_id, [])
        ]
        descriptions = [
            row.get("property_value")
            for row in extended.get(object_id, [])
            if str(row.get("property_name", "")).casefold() in {"ms_description", "description"}
        ]

        documents.append(
            {
                "key": object_key(database, schema, name),
                "node": node,
                "database": database,
                "schema": schema,
                "name": name,
                "object_id": object_id,
                "object_type": obj.get("type"),
                "object_type_desc": obj.get("type_desc"),
                "queryable": bool(policy.get("query_enabled")) and obj.get("type") in QUERYABLE_TYPES,
                "routine_evidence_only": obj.get("type") in ROUTINE_TYPES,
                "create_date": obj.get("create_date"),
                "modify_date": obj.get("modify_date"),
                "columns": object_columns,
                "parameters": object_parameters,
                "result_columns": result_columns,
                "descriptions": descriptions,
                "definition_sha256": module.get("definition_sha256"),
                "definition_excerpt": excerpt,
                "definition_visible": module.get("definition_visible"),
                "dependencies": [
                    {
                        key: row.get(key)
                        for key in (
                            "referenced_server_name",
                            "referenced_database_name",
                            "referenced_schema_name",
                            "referenced_entity_name",
                            "referenced_id",
                            "referenced_type",
                            "is_schema_bound_reference",
                            "is_caller_dependent",
                            "is_ambiguous",
                        )
                    }
                    for row in dependencies.get(object_id, [])
                ],
                "indexes": [
                    {
                        key: row.get(key)
                        for key in (
                            "index_id",
                            "index_name",
                            "type_desc",
                            "is_unique",
                            "is_primary_key",
                            "is_unique_constraint",
                            "has_filter",
                            "filter_definition",
                            "is_disabled",
                            "key_ordinal",
                            "is_descending_key",
                            "is_included_column",
                            "column_name",
                        )
                    }
                    for row in indexes.get(object_id, [])
                ],
            }
        )

    relationships: list[dict[str, Any]] = []
    for row in read_ndjson(source / "foreign_keys.ndjson"):
        relationships.append(
            {
                "source": object_key(database, row["parent_schema"], row["parent_table"]),
                "source_column": row["parent_column"],
                "target": object_key(database, row["referenced_schema"], row["referenced_table"]),
                "target_column": row["referenced_column"],
                "relationship": "foreign_key",
                "name": row["foreign_key_name"],
                "ordinal": row["ordinal"],
                "confidence": "catalog",
                "join_authorized": not row.get("is_disabled") and not row.get("is_not_trusted"),
                "is_disabled": row.get("is_disabled"),
                "is_not_trusted": row.get("is_not_trusted"),
            }
        )
    for row in read_ndjson(source / "dependencies.ndjson"):
        target_database = row.get("referenced_database_name") or database
        target_schema = row.get("referenced_schema_name") or "dbo"
        target_name = row.get("referenced_entity_name")
        if not target_name:
            continue
        relationships.append(
            {
                "source": object_key(database, row["referencing_schema"], row["referencing_object"]),
                "target": object_key(target_database, target_schema, target_name),
                "relationship": "sql_dependency",
                "confidence": (
                    "ambiguous"
                    if row.get("is_ambiguous")
                    else "bound"
                    if row.get("referenced_id") is not None
                    else "unresolved"
                ),
                "join_authorized": False,
                "cross_database": target_database.casefold() != database.casefold(),
                "referenced_server": row.get("referenced_server_name"),
            }
        )

    target.mkdir(parents=True, exist_ok=True)
    files = {
        "objects": write_ndjson(target / "objects.ndjson", documents),
        "relationships": write_ndjson(target / "relationships.ndjson", relationships),
    }
    manifest = {
        "catalog_version": 1,
        "compiler_version": COMPILER_VERSION,
        "source_run_id": run_id,
        "source_fingerprint": raw_manifest.get("fingerprint"),
        "node": node,
        "database": database,
        "policy": policy,
        "object_count": len(documents),
        "queryable_object_count": sum(1 for document in documents if document["queryable"]),
        "relationship_count": len(relationships),
        "redaction_count": redaction_count,
        "source_errors": raw_manifest.get("errors", []),
        "files": files,
        "fingerprint": digest({"documents": files["objects"]["sha256"], "relationships": files["relationships"]["sha256"]}),
    }
    write_json(target / "catalog.manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", choices=("db01", "db02"), required=True)
    parser.add_argument("--environment", default="test")
    parser.add_argument("--run-id", help="Capture run; defaults to latest")
    parser.add_argument("--database", action="append", help="Compile only this database; repeatable")
    parser.add_argument("--capture-root", type=Path, default=CAPTURE_ROOT)
    parser.add_argument("--schema-root", type=Path, default=SCHEMA_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = registry_for(args.node)
    run_id = args.run_id
    if not run_id:
        latest = read_json(args.capture_root / args.environment / args.node / "latest.json")
        run_id = latest["run_id"]
    source_root = args.capture_root / args.environment / args.node / "runs" / run_id
    server_manifest = read_json(source_root / "server.manifest.json")
    selected = {name.casefold() for name in args.database or []}
    compiled: dict[str, Any] = {}
    failures: list[dict[str, str]] = []

    for database in sorted(server_manifest.get("databases", {})):
        if selected and database.casefold() not in selected:
            continue
        try:
            manifest = compile_database(
                source=source_root / database,
                target=args.schema_root / args.environment / args.node / database / "catalog",
                node=args.node,
                database=database,
                policy=database_policy(registry, database),
                run_id=run_id,
            )
            compiled[database] = {
                "fingerprint": manifest["fingerprint"],
                "objects": manifest["object_count"],
                "relationships": manifest["relationship_count"],
                "query_enabled": manifest["policy"].get("query_enabled", False),
            }
            print(f"Compiled {args.node}/{database}: {manifest['object_count']} objects")
        except Exception as error:
            failures.append({"database": database, "error": str(error)})

    node_manifest = {
        "catalog_version": 1,
        "node": args.node,
        "environment": args.environment,
        "source_run_id": run_id,
        "databases": compiled,
        "failures": failures,
        "complete": not failures,
    }
    write_json(args.schema_root / args.environment / args.node / "catalog.manifest.json", node_manifest)
    print(json.dumps(node_manifest, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
