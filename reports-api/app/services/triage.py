from __future__ import annotations

from typing import Any

from ..models import QuickInvestigateResponse, TriageVerdict
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
            ["Check org-node inherited rules.", "Confirm report reached delivery-ready status."],
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
            ["Review why rules were disabled.", "Check org-node overrides."],
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
            ["Validate CustomerEmailAvailability.", "Check downstream mail pipeline if config looks correct."],
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
            ["Confirm customer expected DXF.", "Inspect partner WS / FTP delivery if applicable."],
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


def quick_investigate(repo: ReportsRepository, *, lookup: int, lookup_kind: str = "auto") -> QuickInvestigateResponse:
    resolved = repo.resolve_identifier(lookup, kind=lookup_kind)  # type: ignore[arg-type]
    candidates = resolved.get("data") or []
    if not candidates:
        return QuickInvestigateResponse(
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
            next_checks=["Verify ReportID/OrderID/CustomerID/OrgNodeID/ProfileID.", "Use /samples/reports for seeded IDs."],
        )

    top = candidates[0]
    report_id = int(top["ReportID"])
    overview = repo.get_overview(report_id)
    payload = overview.get("data") or {}
    rules = payload.get("delivery_rules") or []
    verdict, findings, next_checks = _analyze_delivery_rules(rules)

    return QuickInvestigateResponse(
        ok=True,
        source=repo.source,
        report_id=report_id,
        lookup=str(lookup),
        lookup_kind=str(top.get("MatchedAs") or lookup_kind),
        verdict=verdict,
        report=payload.get("report"),
        delivery_rules=rules,
        products=payload.get("products") or [],
        email_availability=payload.get("email_availability") or [],
        findings=findings,
        next_checks=next_checks,
    )
