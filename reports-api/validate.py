"""In-process validation of reports-api. Run: python validate.py"""
from __future__ import annotations

import os

from app.config import get_settings
import app.config as config

get_settings.cache_clear()
config.settings = get_settings()

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if (not ok and detail) else ""
    print(f"[{status}] {name}{extra}")
    if not ok:
        FAILED.append(name)


def expect_status(
    name: str,
    method: str,
    path: str,
    status: int,
    *,
    auth: bool = False,
    extra_headers: dict[str, str] | None = None,
    **kwargs,
) -> dict | list | None:
    headers = dict(kwargs.pop("headers", {}) or {})
    if auth:
        headers.update({"X-API-Key": "unused-key"})
    if extra_headers:
        headers.update(extra_headers)
    response = client.request(method, path, headers=headers, **kwargs)
    check(name, response.status_code == status, f"{response.status_code} != {status} body={response.text[:180]}")
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return None


def main() -> int:
    health = expect_status("health public", "GET", "/health", 200, auth=False)
    check("health reports public auth", bool(health and health.get("auth") == "none"))

    report = expect_status("getReportById", "GET", "/api/v1/reports/44840403", 200)
    check("getReportById data", bool(report and report["data"]["ReportID"] == 44840403))

    expect_status("getReportById missing", "GET", "/api/v1/reports/999", 404)
    expect_status("getReportById zero", "GET", "/api/v1/reports/0", 422)

    snapshot = expect_status(
        "delivery-configuration-snapshot",
        "GET",
        "/api/v1/reports/44840403/delivery-configuration-snapshot",
        200,
    )
    check(
        "snapshot sections",
        bool(
            snapshot
            and snapshot["data"]["report"]["ReportID"] == 44840403
            and "task_status" in snapshot["data"]
            and "report_status_history" in snapshot["data"]
        ),
    )

    for suffix in (
        "current-status-with-history",
        "status-change-history",
        "operations-workflow-status",
        "operations-workflow-task",
        "operations-workflow-task-states",
        "details-with-address-and-measurements",
        "details-with-ordered-products",
        "details-with-ordered-products-and-attributes",
        "file-delivery-rules",
        "delivery-configuration-diagnosis",
        "customer-email-notification-settings",
        "deliverable-verification-rules",
        "product-file-generation-capabilities",
        "ordered-products",
        "report-attributes",
        "property-address",
        "measurement-values",
        "source-imagery",
        "profile-and-organization-associations",
        "related-reports",
        "ordering-application-source",
        "invoice-status",
    ):
        expect_status(f"report {suffix}", "GET", f"/api/v1/reports/44840403/{suffix}", 200)

    task = expect_status(
        "operations-workflow-status stuck",
        "GET",
        "/api/v1/reports/50110200/operations-workflow-status",
        200,
    )
    check("task waiting", bool(task and task["data"]["current_state"]["StateName"] == "Waiting"))

    by_task = expect_status(
        "workflow task by TaskID", "GET", "/api/v1/operations-workflow-tasks/90044840403", 200
    )
    check("task by id", bool(by_task and by_task["data"]["task"]["TaskID"] == 90044840403))
    expect_status(
        "workflow task states by TaskID",
        "GET",
        "/api/v1/operations-workflow-tasks/90044840403/task-states",
        200,
    )

    for retired in (
        "/api/v1/reports/44840403/report-detail-withproducts",
        "/api/v1/reports/44840403/composition",
        "/api/v1/reports/44840403/full-profile",
        "/api/v1/reports/44840403/task-status",
        "/api/v1/tasks/90044840403",
        "/api/v1/org-nodes/88012",
    ):
        expect_status(f"retired path {retired}", "GET", retired, 404)

    expect_status("customer", "GET", "/api/v1/customers/120045", 200)
    expect_status("reports for customer", "GET", "/api/v1/customers/120045/reports", 200)
    expect_status(
        "customer email notification settings",
        "GET",
        "/api/v1/customers/120045/email-notification-settings",
        200,
    )
    expect_status("organization node", "GET", "/api/v1/organization-nodes/88012", 200)
    expect_status("reports for organization node", "GET", "/api/v1/organization-nodes/88012/reports", 200)
    expect_status(
        "inherited file delivery rules",
        "GET",
        "/api/v1/organization-nodes/88012/inherited-file-delivery-rules",
        200,
    )
    expect_status("recipient profile", "GET", "/api/v1/recipient-profiles/55001", 200)
    expect_status("reports for order", "GET", "/api/v1/orders/99100234/reports", 200)
    expect_status("reference workflow-states", "GET", "/api/v1/reference-data/workflow-states", 200)
    expect_status("reference file-types", "GET", "/api/v1/reference-data/file-types", 200)

    find = "/api/v1/reports/find-by-identifier"
    resolved = expect_status("find by OrderID", "GET", f"{find}?value=99100234", 200)
    check(
        "find by OrderID match",
        bool(resolved and resolved["row_count"] == 1 and resolved["data"][0]["MatchedAs"] == "OrderID"),
    )
    expect_status("find no match", "GET", f"{find}?value=99999999", 200)
    expect_status("find jira key", "GET", f"{find}?value=PE-658", 422)
    expect_status("example reports in seed data", "GET", "/api/v1/reports/example-reports-in-seed-data", 200)

    diagnose = "/api/v1/triage/diagnose-delivery-configuration"
    attention = expect_status("diagnose 44840403", "POST", diagnose, 200, json={"lookup": "44840403", "lookup_kind": "auto"})
    check("diagnose attention", bool(attention and attention["verdict"]["level"] == "attention"))
    expect_status("diagnose jira body", "POST", diagnose, 422, json={"lookup": "HCAT-123"})

    generate_sql = expect_status(
        "generate sql query",
        "POST",
        "/api/v1/generatesqlquery",
        200,
        json={"prompt": "Show the report status timeline for report 45036187"},
    )
    check(
        "generate sql query returns SQL",
        bool(generate_sql and isinstance(generate_sql.get("query"), str) and len(generate_sql["query"]) > 20),
    )
    expect_status(
        "generate sql query rejects extra fields",
        "POST",
        "/api/v1/generatesqlquery",
        422,
        json={"prompt": "Show the report status timeline for report 45036187", "database": "DB7222"},
    )

    catalog = expect_status("endpoint catalog", "GET", "/api/v1/metadata/endpoint-catalog", 200)
    check("catalog lists endpoints", bool(catalog and len(catalog.get("endpoints", [])) >= 25))
    check("catalog endpoint_count", bool(catalog and catalog.get("endpoint_count", 0) >= 25))
    check(
        "catalog describes no auth",
        bool(catalog and (catalog.get("authentication") or {}).get("type") == "none"),
    )
    entry_points = (catalog or {}).get("triage_entry_points") or {}
    check("triage entry points advertised", len(entry_points) >= 10)

    from fastapi.routing import APIRoute

    api_paths = sorted(
        {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute) and route.path.startswith("/api/v1")
        }
    )
    check("at least 25 api endpoints", len(api_paths) >= 25, str(len(api_paths)))

    abbreviations = ("withproducts", "taskstates", "/org-", "/meta/", "/reference/")
    offenders = [
        path
        for path in api_paths
        if any(token in path for token in abbreviations) or path.endswith("-config")
    ]
    check("no abbreviated path segments", not offenders, ", ".join(offenders))

    if FAILED:
        print(f"\n{len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
