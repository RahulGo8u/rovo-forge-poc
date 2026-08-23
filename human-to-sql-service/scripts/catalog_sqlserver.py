"""Capture a complete, read-only SQL Server metadata catalog.

The extractor is deliberately outside the API runtime. It connects to one node,
inventories every accessible user database, and writes immutable run artifacts
under .catalog-captures/. No user table data is selected and no routine executes.

Examples:
  python scripts/catalog_sqlserver.py --node db01
  python scripts/catalog_sqlserver.py --node db02 --database Operations
  python scripts/catalog_sqlserver.py --node db02 --server DB02NODE1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

import pyodbc
from dotenv import load_dotenv

from sqlserver_catalog_queries import (
    DATABASES_SQL,
    QUERIES,
    RESULT_SET_SQL,
    SERVER_SQL,
)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DEFAULT_CAPTURE_ROOT = ROOT / ".catalog-captures"
DEFAULT_SERVERS = {"db01": "DB01NODE1", "db02": "DB02NODE1"}
MODULE_TYPES = {"V", "P", "PC", "FN", "IF", "TF", "FS", "FT"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9_. -]+$")
EXTRACTOR_VERSION = "1.0.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_database_name(name: str) -> str:
    if not name or not SAFE_NAME.fullmatch(name) or "\x00" in name:
        raise ValueError(f"Unsafe database name: {name!r}")
    return name


def rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    names = [str(column[0]) for column in cursor.description or ()]
    return [
        {name: json_value(value) for name, value in zip(names, record)}
        for record in cursor.fetchall()
    ]


def execute_rows(connection: pyodbc.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        return rows(cursor)
    finally:
        cursor.close()


def connection_string(*, server: str, database: str, driver: str) -> str:
    # Database and server are operator/config values, never prompt input.
    validate_database_name(database)
    if not server or any(char in server for char in ";\r\n\x00"):
        raise ValueError("Unsafe SQL Server host")
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
        "ApplicationIntent=ReadOnly;APP=human-to-sql-service-catalog;"
    )


def connect(*, server: str, database: str, driver: str, timeout: int) -> pyodbc.Connection:
    return pyodbc.connect(
        connection_string(server=server, database=database, driver=driver),
        timeout=timeout,
        autocommit=True,
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_ndjson(path: Path, payload: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in payload:
            line = canonical_json(item)
            handle.write(line + "\n")
            digest.update((line + "\n").encode("utf-8"))
            count += 1
    return {"row_count": count, "sha256": digest.hexdigest(), "file": path.name}


def read_latest(capture_root: Path, environment: str, node: str) -> dict[str, Any] | None:
    pointer = capture_root / environment / node / "latest.json"
    if not pointer.is_file():
        return None
    try:
        return json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def describe_result_sets(
    connection: pyodbc.Connection,
    module_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for module in module_rows:
        if module.get("type") not in MODULE_TYPES:
            continue
        object_id = int(module["object_id"])
        identity = {
            "object_id": object_id,
            "schema_name": module.get("schema_name"),
            "object_name": module.get("object_name"),
            "object_type": module.get("type"),
        }
        try:
            described = execute_rows(connection, RESULT_SET_SQL, (object_id,))
            if described:
                for column in described:
                    output.append({**identity, **column, "discoverable": column.get("error_number") is None})
            else:
                output.append({**identity, "discoverable": True, "column_ordinal": None})
        except pyodbc.Error as error:
            errors.append({**identity, "stage": "result_sets", "error": str(error)})
            output.append({**identity, "discoverable": False, "error_message": str(error)})
    return output, errors


def capture_database(
    *,
    server: str,
    database: str,
    driver: str,
    timeout: int,
    target: Path,
) -> dict[str, Any]:
    started = utc_now()
    files: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    with connect(server=server, database=database, driver=driver, timeout=timeout) as connection:
        for name, sql in QUERIES.items():
            try:
                captured = execute_rows(connection, sql)
                if name in {"modules", "triggers"}:
                    for item in captured:
                        definition = item.get("definition")
                        item["definition_sha256"] = (
                            sha256_text(definition) if isinstance(definition, str) else None
                        )
                files[name] = write_ndjson(target / f"{name}.ndjson", captured)
            except pyodbc.Error as error:
                errors.append({"stage": name, "error": str(error)})
                files[name] = write_ndjson(target / f"{name}.ndjson", [])

        module_path = target / "modules.ndjson"
        module_rows = [
            json.loads(line)
            for line in module_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result_rows, result_errors = describe_result_sets(connection, module_rows)
        errors.extend(result_errors)
        files["result_sets"] = write_ndjson(target / "result_sets.ndjson", result_rows)

        database_info = execute_rows(
            connection,
            """
SELECT
  DB_NAME() AS database_name,
  DATABASEPROPERTYEX(DB_NAME(), 'Status') AS status,
  DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS collation,
  DATABASEPROPERTYEX(DB_NAME(), 'Updateability') AS updateability,
  compatibility_level,
  HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'VIEW DEFINITION') AS has_view_definition
FROM sys.databases
WHERE name = DB_NAME();
""",
        )[0]

    fingerprint = sha256_text(
        canonical_json({name: {"row_count": meta["row_count"], "sha256": meta["sha256"]} for name, meta in files.items()})
    )
    manifest = {
        "catalog_version": 1,
        "extractor_version": EXTRACTOR_VERSION,
        "database": database_info,
        "started_at": started.isoformat(),
        "completed_at": utc_now().isoformat(),
        "fingerprint": fingerprint,
        "files": files,
        "errors": errors,
        "complete": not errors,
    }
    write_json(target / "catalog.manifest.json", manifest)
    return manifest


def build_drift(
    *,
    current: dict[str, Any],
    previous_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    if not previous_manifest:
        return {"baseline": True, "changed": True, "files": {}}
    previous_files = previous_manifest.get("files", {})
    changes: dict[str, Any] = {}
    for name in sorted(set(previous_files) | set(current.get("files", {}))):
        before = previous_files.get(name)
        after = current.get("files", {}).get(name)
        if before != after:
            changes[name] = {"before": before, "after": after}
    return {
        "baseline": False,
        "changed": bool(changes),
        "previous_fingerprint": previous_manifest.get("fingerprint"),
        "current_fingerprint": current.get("fingerprint"),
        "files": changes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", choices=("db01", "db02"), required=True)
    parser.add_argument("--server", help="SQL Server host; otherwise node env/default is used")
    parser.add_argument("--environment", default="test")
    parser.add_argument("--database", action="append", help="Capture only this database; repeatable")
    parser.add_argument("--driver", default=os.getenv("SQLSERVER_ODBC_DRIVER", "ODBC Driver 17 for SQL Server"))
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--output", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = args.server or os.getenv(f"SQLSERVER_{args.node.upper()}_HOST") or DEFAULT_SERVERS[args.node]
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    run_root = args.output.resolve() / args.environment / args.node / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=False)

    with connect(server=server, database="master", driver=args.driver, timeout=args.timeout) as master:
        server_info = execute_rows(master, SERVER_SQL)[0]
        database_rows = execute_rows(master, DATABASES_SQL)

    requested = {validate_database_name(name).casefold() for name in (args.database or [])}
    inventory = []
    eligible: list[str] = []
    for item in database_rows:
        item["selected"] = (
            item.get("has_access") == 1
            and item.get("state_desc") == "ONLINE"
            and (not requested or str(item["name"]).casefold() in requested)
        )
        inventory.append(item)
        if item["selected"]:
            eligible.append(str(item["name"]))

    missing = sorted(requested - {str(item["name"]).casefold() for item in database_rows})
    if missing:
        write_json(run_root / "catalog.errors.json", [{"stage": "inventory", "missing": missing}])

    write_ndjson(run_root / "databases.ndjson", inventory)
    previous = read_latest(args.output.resolve(), args.environment, args.node)
    previous_root = (
        args.output.resolve() / args.environment / args.node / "runs" / previous["run_id"]
        if previous and previous.get("run_id")
        else None
    )

    captured: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    for database in eligible:
        print(f"Capturing {args.node}/{database}...", flush=True)
        try:
            manifest = capture_database(
                server=server,
                database=database,
                driver=args.driver,
                timeout=args.timeout,
                target=run_root / database,
            )
            previous_manifest = None
            if previous_root:
                old_path = previous_root / database / "catalog.manifest.json"
                if old_path.is_file():
                    previous_manifest = json.loads(old_path.read_text(encoding="utf-8"))
            drift = build_drift(current=manifest, previous_manifest=previous_manifest)
            write_json(run_root / database / "drift.json", drift)
            captured[database] = {
                "complete": manifest["complete"],
                "fingerprint": manifest["fingerprint"],
                "errors": len(manifest["errors"]),
                "changed": drift["changed"],
            }
        except Exception as error:  # keep other databases extractable
            failure = {"database": database, "error": str(error)}
            failures.append(failure)
            print(f"FAILED {args.node}/{database}: {error}", file=sys.stderr)
            if not args.continue_on_error:
                break

    run_manifest = {
        "catalog_version": 1,
        "extractor_version": EXTRACTOR_VERSION,
        "run_id": run_id,
        "environment": args.environment,
        "node": args.node,
        "server": server_info,
        "started_at": started.isoformat(),
        "completed_at": utc_now().isoformat(),
        "database_count_visible": len(database_rows),
        "database_count_selected": len(eligible),
        "database_count_captured": len(captured),
        "databases": captured,
        "failures": failures,
        "complete": (
            not failures
            and len(captured) == len(eligible)
            and all(item["complete"] for item in captured.values())
        ),
    }
    write_json(run_root / "server.manifest.json", run_manifest)
    pointer_name = "latest.json" if run_manifest["complete"] else "latest_failed.json"
    write_json(
        args.output.resolve() / args.environment / args.node / pointer_name,
        {"run_id": run_id, "manifest": str(run_root / "server.manifest.json")},
    )
    print(json.dumps(run_manifest, indent=2))
    return 0 if run_manifest["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
