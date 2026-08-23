"""In-process validation of reports-api. No auth. Run: python validate.py"""
from __future__ import annotations

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


def expect_status(name: str, method: str, path: str, status: int, **kwargs) -> dict | list | None:
    response = client.request(method, path, **kwargs)
    check(name, response.status_code == status, f"{response.status_code} != {status} body={response.text[:180]}")
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return None


def main() -> int:
    health = expect_status("health", "GET", "/health", 200)
    check("health auth none", bool(health and health.get("auth") == "none" and health.get("data_source") == "seed"))

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
    check(
        "task waiting",
        bool(task and task["data"]["current_state"]["StateName"] == "Waiting"),
    )

    resolved = expect_status(
        "lookup OrderID",
        "GET",
        "/api/v1/reports/lookup-by-identifier?value=99100234",
        200,
    )
    check(
        "lookup OrderID match",
        bool(resolved and resolved["row_count"] == 1 and resolved["data"][0]["MatchedAs"] == "OrderID"),
    )
    expect_status("lookup empty", "GET", "/api/v1/reports/lookup-by-identifier?value=99999999", 200)
    expect_status("lookup jira key", "GET", "/api/v1/reports/lookup-by-identifier?value=PE-658", 422)
    expect_status("lookup text", "GET", "/api/v1/reports/lookup-by-identifier?value=not-a-number", 422)
    expect_status("lookup bad kind", "GET", "/api/v1/reports/lookup-by-identifier?value=44840403&kind=Nope", 422)

    expect_status("org rules", "GET", "/api/v1/org-nodes/88012/inherited-delivery-rules", 200)
    expect_status("reference delivery-methods", "GET", "/api/v1/reference/delivery-methods", 200)
    expect_status("reference file-types", "GET", "/api/v1/reference/file-types", 200)
    expect_status("reference email-types", "GET", "/api/v1/reference/email-types", 200)
    expect_status("reference invalid", "GET", "/api/v1/reference/unknown", 422)
    expect_status("seed-examples", "GET", "/api/v1/reports/seed-examples", 200)
    expect_status("seed-examples bad limit", "GET", "/api/v1/reports/seed-examples?limit=0", 422)

    diagnose = "/api/v1/triage/diagnose-delivery-config"
    attention = expect_status("diagnose 44840403", "POST", diagnose, 200, json={"lookup": "44840403", "lookup_kind": "auto"})
    check("diagnose attention", bool(attention and attention["verdict"]["level"] == "attention"))
    healthy = expect_status("diagnose 72391747", "POST", diagnose, 200, json={"lookup": "72391747"})
    check("diagnose healthy", bool(healthy and healthy["verdict"]["level"] == "healthy"))
    missing_rules = expect_status("diagnose 50110200", "POST", diagnose, 200, json={"lookup": "50110200"})
    check("diagnose issue no rules", bool(missing_rules and missing_rules["verdict"]["level"] == "issue"))
    disabled = expect_status("diagnose 61220311", "POST", diagnose, 200, json={"lookup": "61220311"})
    check("diagnose issue disabled", bool(disabled and disabled["verdict"]["level"] == "issue"))
    unknown = expect_status("diagnose unknown id", "POST", diagnose, 200, json={"lookup": "1"})
    check("diagnose unknown ok false", bool(unknown and unknown["ok"] is False))
    expect_status("diagnose jira body", "POST", diagnose, 422, json={"lookup": "HCAT-123"})
    expect_status("diagnose empty body", "POST", diagnose, 422, json={})

    meta = expect_status("meta endpoints", "GET", "/api/v1/meta/endpoints", 200)
    check("meta lists endpoints", bool(meta and len(meta.get("endpoints", [])) >= 15))

    if FAILED:
        print(f"\n{len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
