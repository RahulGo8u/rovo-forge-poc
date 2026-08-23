"""In-process validation of reports-api. Run: python validate.py"""
from __future__ import annotations

import os

TEST_KEY = "validate-local-secret-not-for-production"
os.environ["API_SECRET_KEY"] = TEST_KEY

from app.config import get_settings
import app.config as config

get_settings.cache_clear()
config.settings = get_settings()

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FAILED: list[str] = []
AUTH = {"X-API-Key": TEST_KEY}


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
    auth: bool = True,
    extra_headers: dict[str, str] | None = None,
    **kwargs,
) -> dict | list | None:
    headers = dict(kwargs.pop("headers", {}) or {})
    if auth:
        headers.update(AUTH)
    if extra_headers:
        headers.update(extra_headers)
    response = client.request(method, path, headers=headers, **kwargs)
    check(name, response.status_code == status, f"{response.status_code} != {status} body={response.text[:180]}")
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return None


def main() -> int:
    health = expect_status("health public", "GET", "/health", 200, auth=False)
    check("health reports api_key", bool(health and health.get("auth") == "api_key"))

    expect_status("api without key", "GET", "/api/v1/reports/44840403", 401, auth=False)
    expect_status("api wrong key", "GET", "/api/v1/reports/44840403", 401, extra_headers={"X-API-Key": "wrong-key"})
    bearer = expect_status(
        "api bearer token",
        "GET",
        "/api/v1/reports/44840403",
        200,
        auth=False,
        extra_headers={"Authorization": f"Bearer {TEST_KEY}"},
    )
    check("bearer returns report", bool(bearer and bearer["data"]["ReportID"] == 44840403))

    report = expect_status("getReportById", "GET", "/api/v1/reports/44840403", 200)
    check("getReportById data", bool(report and report["data"]["ReportID"] == 44840403))

    expect_status("getReportById missing", "GET", "/api/v1/reports/999", 404)
    expect_status("getReportById zero", "GET", "/api/v1/reports/0", 422)

    snapshot = expect_status("delivery-snapshot", "GET", "/api/v1/reports/44840403/delivery-snapshot", 200)
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
        "delivery-rules",
        "products",
        "attributes",
        "report-status-history",
        "task-status",
        "customer-email-settings",
        "delivery-diagnosis",
    ):
        expect_status(f"report {suffix}", "GET", f"/api/v1/reports/44840403/{suffix}", 200)

    task = expect_status("task-status stuck", "GET", "/api/v1/reports/50110200/task-status", 200)
    check("task waiting", bool(task and task["data"]["current_state"]["StateName"] == "Waiting"))

    resolved = expect_status("lookup OrderID", "GET", "/api/v1/reports/lookup-by-identifier?value=99100234", 200)
    check(
        "lookup OrderID match",
        bool(resolved and resolved["row_count"] == 1 and resolved["data"][0]["MatchedAs"] == "OrderID"),
    )
    expect_status("lookup empty", "GET", "/api/v1/reports/lookup-by-identifier?value=99999999", 200)
    expect_status("lookup jira key", "GET", "/api/v1/reports/lookup-by-identifier?value=PE-658", 422)

    expect_status("org rules", "GET", "/api/v1/org-nodes/88012/inherited-delivery-rules", 200)
    expect_status("reference file-types", "GET", "/api/v1/reference/file-types", 200)
    expect_status("seed-examples", "GET", "/api/v1/reports/seed-examples", 200)

    diagnose = "/api/v1/triage/diagnose-delivery-config"
    attention = expect_status("diagnose 44840403", "POST", diagnose, 200, json={"lookup": "44840403", "lookup_kind": "auto"})
    check("diagnose attention", bool(attention and attention["verdict"]["level"] == "attention"))
    expect_status("diagnose jira body", "POST", diagnose, 422, json={"lookup": "HCAT-123"})

    meta = expect_status("meta endpoints", "GET", "/api/v1/meta/endpoints", 200)
    check("meta lists endpoints", bool(meta and len(meta.get("endpoints", [])) >= 15))
    check("meta describes api_key", bool(meta and (meta.get("auth") or {}).get("type") == "api_key"))

    if FAILED:
        print(f"\n{len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
