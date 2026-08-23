from __future__ import annotations

from typing import Any, Literal

from .seed import load_seed
from .validation import LookupKind

LOOKUP_FIELDS: dict[str, str] = {
    "ReportID": "ReportID",
    "OrderID": "OrderID",
    "CustomerID": "CustomerID",
    "OrgNodeID": "OrgNodeID",
    "ProfileID": "ProfileID",
}


def _ok(data: Any, *, meta: dict[str, Any] | None = None, row_count: int | None = None) -> dict[str, Any]:
    if row_count is None:
        if isinstance(data, list):
            row_count = len(data)
        elif data is None:
            row_count = 0
        else:
            row_count = 1
    return {"ok": True, "source": "seed", "row_count": row_count, "data": data, "meta": meta or {}}


class ReportsRepository:
    source: Literal["seed"] = "seed"

    def __init__(self) -> None:
        self._seed = load_seed()
        self._reports: list[dict[str, Any]] = list(self._seed["reports"])
        self._by_report_id = {int(r["ReportID"]): r for r in self._reports}

    def _keyed(self, collection: str, key: int) -> list[dict[str, Any]]:
        return list(self._seed.get(collection, {}).get(str(key), []))

    def get_report_by_id(self, report_id: int) -> dict[str, Any]:
        report = self._by_report_id.get(report_id)
        return _ok(report, meta={"report_id": report_id}, row_count=1 if report else 0)

    def get_delivery_rules(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("delivery_rules", report_id), meta={"report_id": report_id})

    def get_org_delivery_rules(self, org_node_id: int) -> dict[str, Any]:
        return _ok(self._keyed("org_rules", org_node_id), meta={"org_node_id": org_node_id})

    def get_products(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("products", report_id), meta={"report_id": report_id})

    def get_attributes(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("attributes", report_id), meta={"report_id": report_id})

    def get_report_status_history(self, report_id: int, *, limit: int = 25) -> dict[str, Any]:
        rows = self._keyed("status_timeline", report_id)[: max(1, min(limit, 100))]
        return _ok(rows, meta={"report_id": report_id})

    def get_task_status(self, report_id: int) -> dict[str, Any]:
        payload = self._seed.get("task_status", {}).get(str(report_id))
        if not payload:
            return {
                "ok": False,
                "source": "seed",
                "row_count": 0,
                "data": None,
                "meta": {"report_id": report_id, "error": "No operations task found for this report"},
            }
        active = payload.get("active_states") or []
        history = payload.get("state_history") or []
        current = active[0] if active else None
        return _ok(
            {
                "task": payload.get("task"),
                "current_state": current,
                "active_states": active,
                "state_history": history,
            },
            meta={
                "report_id": report_id,
                "task_id": (payload.get("task") or {}).get("TaskID"),
                "current_state_name": (current or {}).get("StateName"),
            },
        )

    def get_email_availability(self, *, org_node_id: int | None, profile_id: int | None) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        if org_node_id is not None:
            rows.extend(self._keyed("email_availability", org_node_id))
        if profile_id is not None:
            for report in self._reports:
                if report.get("ProfileID") == profile_id:
                    rows.extend(self._keyed("email_availability", int(report["OrgNodeID"])))
            seen: set[int] = set()
            unique: list[dict[str, Any]] = []
            for row in rows:
                row_id = int(row.get("Id", 0))
                if row_id in seen:
                    continue
                seen.add(row_id)
                unique.append(row)
            rows = unique
        return _ok(rows, meta={"org_node_id": org_node_id, "profile_id": profile_id})

    def resolve_identifier(self, number: int, *, kind: LookupKind = "auto", limit: int = 20) -> dict[str, Any]:
        top = max(1, min(limit, 50))
        fields = LOOKUP_FIELDS if kind == "auto" else {kind: LOOKUP_FIELDS[kind]}
        rows: list[dict[str, Any]] = []
        for report in self._reports:
            matched_as = next(
                (label for label, field in fields.items() if report.get(field) == number),
                None,
            )
            if matched_as:
                rows.append({**report, "MatchedAs": matched_as})
        return _ok(rows[:top], meta={"lookup": number, "kind": kind})

    def get_catalog(self, catalog_name: str) -> dict[str, Any]:
        key = catalog_name.replace("-", "_")
        catalogs = self._seed.get("catalogs", {})
        if key not in catalogs:
            return {
                "ok": False,
                "source": "seed",
                "row_count": 0,
                "data": [],
                "meta": {"error": "Unknown catalog"},
            }
        return _ok(catalogs[key], meta={"catalog": catalog_name})

    def get_sample_reports(self, *, limit: int = 10) -> dict[str, Any]:
        top = max(1, min(limit, 50))
        rows = []
        for report in self._reports[:top]:
            report_id = int(report["ReportID"])
            rows.append(
                {
                    "ReportID": report_id,
                    "CustomerID": report["CustomerID"],
                    "OrgNodeID": report["OrgNodeID"],
                    "OrderID": report["OrderID"],
                    "ProfileID": report.get("ProfileID"),
                    "DeliveryRuleCount": len(self._keyed("delivery_rules", report_id)),
                }
            )
        return _ok(rows)

    def get_overview(self, report_id: int) -> dict[str, Any]:
        report = self.get_report_by_id(report_id).get("data")
        if not report:
            return {
                "ok": False,
                "source": "seed",
                "row_count": 0,
                "data": None,
                "meta": {"report_id": report_id, "error": "Report not found"},
            }
        org_node_id = report.get("OrgNodeID")
        return _ok(
            {
                "report": report,
                "products": self.get_products(report_id)["data"],
                "attributes": self.get_attributes(report_id)["data"],
                "delivery_rules": self.get_delivery_rules(report_id)["data"],
                "report_status_history": self.get_report_status_history(report_id)["data"],
                "task_status": self.get_task_status(report_id).get("data"),
                "customer_email_settings": self.get_email_availability(
                    org_node_id=org_node_id, profile_id=report.get("ProfileID")
                )["data"],
            },
            meta={"report_id": report_id},
        )
