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
    expect_status("getReportById negative", "GET", "/api/v1/reports/-1", 422)
    expect_status("getReportById not numeric", "GET", "/api/v1/reports/abc", 422)

    overview = expect_status("overview", "GET", "/api/v1/reports/44840403/overview", 200)
    check(
        "overview sections",
        bool(
            overview
            and overview["data"]["report"]["ReportID"] == 44840403
            and isinstance(overview["data"]["delivery_rules"], list)
            and isinstance(overview["data"]["products"], list)
        ),
    )

    for suffix in (
        "delivery-rules",
        "products",
        "attributes",
        "status-timeline",
        "email-availability",
        "delivery-analysis",
    ):
        expect_status(f"report {suffix}", "GET", f"/api/v1/reports/44840403/{suffix}", 200)

    resolved = expect_status("resolve OrderID", "GET", "/api/v1/resolve?value=99100234", 200)
    check(
        "resolve OrderID match",
        bool(resolved and resolved["row_count"] == 1 and resolved["data"][0]["MatchedAs"] == "OrderID"),
    )
    expect_status("resolve empty", "GET", "/api/v1/resolve?value=99999999", 200)
    expect_status("resolve jira key", "GET", "/api/v1/resolve?value=PE-658", 422)
    expect_status("resolve text", "GET", "/api/v1/resolve?value=not-a-number", 422)
    expect_status("resolve bad kind", "GET", "/api/v1/resolve?value=44840403&kind=Nope", 422)

    expect_status("org rules", "GET", "/api/v1/org-nodes/88012/delivery-rules", 200)
    expect_status("catalog delivery-methods", "GET", "/api/v1/catalog/delivery-methods", 200)
    expect_status("catalog file-types", "GET", "/api/v1/catalog/file-types", 200)
    expect_status("catalog email-types", "GET", "/api/v1/catalog/email-types", 200)
    expect_status("catalog invalid", "GET", "/api/v1/catalog/unknown", 422)
    expect_status("samples", "GET", "/api/v1/samples/reports", 200)
    expect_status("samples bad limit", "GET", "/api/v1/samples/reports?limit=0", 422)

    attention = expect_status(
        "triage 44840403",
        "POST",
        "/api/v1/triage/quick-investigate",
        200,
        json={"lookup": "44840403", "lookup_kind": "auto"},
    )
    check("triage attention", bool(attention and attention["verdict"]["level"] == "attention"))

    healthy = expect_status(
        "triage 72391747",
        "POST",
        "/api/v1/triage/quick-investigate",
        200,
        json={"lookup": "72391747"},
    )
    check("triage healthy", bool(healthy and healthy["verdict"]["level"] == "healthy"))

    missing_rules = expect_status(
        "triage 50110200",
        "POST",
        "/api/v1/triage/quick-investigate",
        200,
        json={"lookup": "50110200"},
    )
    check("triage issue no rules", bool(missing_rules and missing_rules["verdict"]["level"] == "issue"))

    disabled = expect_status(
        "triage 61220311",
        "POST",
        "/api/v1/triage/quick-investigate",
        200,
        json={"lookup": "61220311"},
    )
    check("triage issue disabled", bool(disabled and disabled["verdict"]["level"] == "issue"))

    unknown = expect_status(
        "triage unknown id",
        "POST",
        "/api/v1/triage/quick-investigate",
        200,
        json={"lookup": "1"},
    )
    check("triage unknown ok false", bool(unknown and unknown["ok"] is False))

    expect_status(
        "triage jira body",
        "POST",
        "/api/v1/triage/quick-investigate",
        422,
        json={"lookup": "HCAT-123"},
    )
    expect_status(
        "triage empty body",
        "POST",
        "/api/v1/triage/quick-investigate",
        422,
        json={},
    )

    meta = expect_status("meta endpoints", "GET", "/api/v1/meta/endpoints", 200)
    check("meta lists endpoints", bool(meta and len(meta.get("endpoints", [])) >= 14))

    if FAILED:
        print(f"\n{len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
