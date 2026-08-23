from __future__ import annotations

import argparse
import json

from .services.query_router import prepare_or_generate_query


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate validated T-SQL without executing it."
    )
    parser.add_argument("prompt")
    parser.add_argument("--environment", default="test", choices=("test",))
    parser.add_argument("--node", choices=("db01", "db02"))
    parser.add_argument("--database")
    parser.add_argument(
        "--query-mode",
        choices=("auto", "templates_only", "generated_only"),
    )
    parser.add_argument("--report-id", type=int)
    parser.add_argument("--order-id", type=int)
    parser.add_argument("--customer-id", type=int)
    parser.add_argument("--organization-node-id", type=int)
    parser.add_argument("--profile-id", type=int)
    args = parser.parse_args()
    result = prepare_or_generate_query(
        prompt=args.prompt,
        environment=args.environment,
        server=args.node,
        database=args.database,
        query_mode=args.query_mode,
        report_id=args.report_id,
        order_id=args.order_id,
        customer_id=args.customer_id,
        organization_node_id=args.organization_node_id,
        profile_id=args.profile_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
