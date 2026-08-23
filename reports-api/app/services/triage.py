from __future__ import annotations

from typing import Any

from ..models import DiagnoseDeliveryResponse, TriageVerdict
from ..repository import ReportsRepository


def _analyze_delivery_rules(rules: list[dict[str, Any]]) -> tuple[TriageVerdict, list[str], list[str]]:
    findings: list[str] = []
    next_checks: list[str] = []

    if not rules:
        return (
            TriageVerdict(
                level="issue",
                summary="No delivery rules are configured for this report.",
                confidence=92,
            ),
            ["No rows in ReportFileDeliveryRule for this ReportID."],
            [
                "Check /organization-nodes/{org_node_id}/inherited-file-delivery-rules.",
                "Check /reports/{report_id}/operations-workflow-status to confirm the report reached a delivery-ready state.",
            ],
        )

    enabled = [r for r in rules if not r.get("Disabled")]
    disabled = [r for r in rules if r.get("Disabled")]

    if disabled:
        findings.append(f"{len(disabled)} delivery rule(s) are disabled.")
    if not enabled:
        return (
            TriageVerdict(
                level="issue",
                summary="Delivery rules exist but all are disabled.",
                confidence=95,
            ),
            findings,
            [
                "Review why every rule was disabled.",
                "Check /organization-nodes/{org_node_id}/inherited-file-delivery-rules for an OverrideChildren rule.",
            ],
        )

    file_types = sorted({r.get("FileTypeID") for r in enabled if r.get("FileTypeID") is not None})
    findings.append(f"Enabled rules cover FileTypeIDs: {file_types or 'none'}.")

    email_rules = [r for r in enabled if r.get("DeliveryMethodID") == 1]
    dxf_rules = [r for r in enabled if r.get("FileTypeID") == 4]

    if not email_rules:
        findings.append("No enabled email delivery rules (DeliveryMethodID=1).")
        return (
            TriageVerdict(
                level="issue",
                summary="No active email delivery channel is configured.",
                confidence=88,
            ),
            findings,
            [
                "Check /reports/{report_id}/customer-email-notification-settings.",
                "If configuration looks correct, inspect the downstream mail pipeline.",
            ],
        )

    if not dxf_rules:
        findings.append("No enabled neighborhood/DXF rule (FileTypeID=4).")
        return (
            TriageVerdict(
                level="attention",
                summary="Email delivery looks configured; DXF/neighborhood delivery may be missing or disabled.",
                confidence=80,
            ),
            findings,
            [
                "Confirm the customer expected a DXF file.",
                "Check /reports/{report_id}/product-file-generation-capabilities for CanGenerateDXF.",
                "Inspect Partner Web Service or FTP delivery if either applies.",
            ],
        )

    return (
        TriageVerdict(
            level="healthy",
            summary="Delivery configuration appears complete for common channels.",
            confidence=78,
        ),
        findings,
        ["If customer still reports failure, inspect downstream delivery attempts and mail logs."],
    )


def diagnose_delivery_config(repo: ReportsRepository, *, lookup: int, lookup_kind: str = "auto") -> DiagnoseDeliveryResponse:
    resolved = repo.resolve_identifier(lookup, kind=lookup_kind)  # type: ignore[arg-type]
    candidates = resolved.get("data") or []
    if not candidates:
        return DiagnoseDeliveryResponse(
            ok=False,
            source=repo.source,
            lookup=str(lookup),
            lookup_kind=lookup_kind,
            verdict=TriageVerdict(
                level="info",
                summary="No report matched the supplied identifier.",
                confidence=90,
            ),
            findings=["Identifier did not resolve to any report."],
            next_checks=[
                "Verify the ReportID, OrderID, CustomerID, OrgNodeID, or ProfileID.",
                "Call /reports/example-reports-in-seed-data for identifiers that exist in this service.",
            ],
        )

    top = candidates[0]
    report_id = int(top["ReportID"])
    overview = repo.get_overview(report_id)
    payload = overview.get("data") or {}
    rules = payload.get("delivery_rules") or []
    verdict, findings, next_checks = _analyze_delivery_rules(rules)

    return DiagnoseDeliveryResponse(
        ok=True,
        source=repo.source,
        report_id=report_id,
        lookup=str(lookup),
        lookup_kind=str(top.get("MatchedAs") or lookup_kind),
        verdict=verdict,
        report=payload.get("report"),
        delivery_rules=rules,
        products=payload.get("products") or [],
        email_availability=payload.get("customer_email_settings") or [],
        findings=findings,
        next_checks=next_checks,
    )
