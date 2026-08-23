"""Convert a read-only sys.foreign_key_columns dump into a schema-pack file.

The API has no database driver, so foreign keys are captured out-of-band with the
SQL MCP tool and committed alongside the column dump. Refresh with:

    SELECT pt.name AS ParentTable, pc.name AS ParentColumn,
           rt.name AS ReferencedTable, rc.name AS ReferencedColumn
    FROM sys.foreign_key_columns AS fkc
    INNER JOIN sys.tables AS pt ON pt.object_id = fkc.parent_object_id
    INNER JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
    INNER JOIN sys.columns AS pc ON pc.object_id = fkc.parent_object_id
                               AND pc.column_id = fkc.parent_column_id
    INNER JOIN sys.tables AS rt ON rt.object_id = fkc.referenced_object_id
    INNER JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
    INNER JOIN sys.columns AS rc ON rc.object_id = fkc.referenced_object_id
                               AND rc.column_id = fkc.referenced_column_id
    WHERE ps.name = 'dbo' AND rs.name = 'dbo'
    ORDER BY pt.name, pc.name;

Usage:
    python scripts/import_foreign_keys.py <dump.json> [--environment test] [--server db01] [--database DB7222]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schema"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="JSON file holding the MCP query result")
    parser.add_argument("--environment", default="test")
    parser.add_argument("--server", default="db01")
    parser.add_argument("--database", default="DB7222")
    args = parser.parse_args()

    payload = json.loads(args.dump.read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload

    edges = sorted(
        {
            (
                str(row["ParentTable"]),
                str(row["ParentColumn"]),
                str(row["ReferencedTable"]),
                str(row["ReferencedColumn"]),
            )
            for row in rows
        }
    )

    target = SCHEMA_ROOT / args.environment / args.server / args.database / "foreign_keys.json"
    if not target.parent.is_dir():
        raise SystemExit(f"Schema pack folder does not exist: {target.parent}")

    target.write_text(
        json.dumps(
            [
                {
                    "parent_table": parent_table,
                    "parent_column": parent_column,
                    "referenced_table": referenced_table,
                    "referenced_column": referenced_column,
                }
                for parent_table, parent_column, referenced_table, referenced_column in edges
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(edges)} foreign key edges to {target}")


if __name__ == "__main__":
    main()
