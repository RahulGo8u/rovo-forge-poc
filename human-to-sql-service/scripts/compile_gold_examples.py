"""Compile reviewed template prompts into gold question-to-SQL examples."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.planner import prepare_query  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="db01")
    parser.add_argument("--database", default="DB7222")
    parser.add_argument("--environment", default="test")
    args = parser.parse_args()

    source = ROOT / "catalog" / args.node / "gold_examples.yaml"
    spec = yaml.safe_load(source.read_text(encoding="utf-8"))
    if spec.get("node") != args.node or spec.get("database") != args.database:
        raise SystemExit("Gold example source identity does not match arguments")

    compiled = []
    failures = []
    for group in spec.get("examples") or []:
        for question in group.get("questions") or []:
            result = prepare_query(
                prompt=question,
                environment=args.environment,
                server=args.node,
                database=args.database,
                **(group.get("request") or {}),
            )
            if not result.get("ok") or result.get("intent") != group.get("intent"):
                failures.append(
                    {
                        "question": question,
                        "expected_intent": group.get("intent"),
                        "result": result,
                    }
                )
                continue
            compiled.append(
                {
                    "question": question,
                    "intent": result["intent"],
                    "sql": result["sql"],
                    "params": result["params"],
                    "objects": result["tables_used"],
                    "safety": result["safety"],
                }
            )

    target = ROOT / "schema" / args.environment / args.node / args.database / "gold_examples.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "node": args.node,
                "database": args.database,
                "example_count": len(compiled),
                "examples": compiled,
                "failures": failures,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(compiled)} gold examples to {target}")
    if failures:
        print(json.dumps(failures, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
