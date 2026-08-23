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

    def _record(self, collection: str, key: int) -> dict[str, Any] | None:
        value = self._seed.get(collection, {}).get(str(key))
        return value if isinstance(value, dict) else None

    def _require_report(self, report_id: int) -> dict[str, Any] | None:
        return self._by_report_id.get(report_id)

    def _task_payload(self, report_id: int) -> dict[str, Any] | None:
        return self._seed.get("task_status", {}).get(str(report_id))

    def list_reports(
        self,
        *,
        customer_id: int | None = None,
        org_node_id: int | None = None,
        order_id: int | None = None,
        profile_id: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._reports
        if customer_id is not None:
            rows = [r for r in rows if r.get("CustomerID") == customer_id]
        if org_node_id is not None:
            rows = [r for r in rows if r.get("OrgNodeID") == org_node_id]
        if order_id is not None:
            rows = [r for r in rows if r.get("OrderID") == order_id]
        if profile_id is not None:
            rows = [r for r in rows if r.get("ProfileID") == profile_id]
        return rows

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

    def get_report_status(self, report_id: int) -> dict[str, Any]:
        history = self._keyed("status_timeline", report_id)
        current = history[0] if history else None
        return _ok(
            {"current": current, "history": history},
            meta={"report_id": report_id, "current_status": (current or {}).get("Status")},
        )

    def get_report_detail(self, report_id: int) -> dict[str, Any]:
        report = self._require_report(report_id)
        if not report:
            return _ok(None, meta={"report_id": report_id, "error": "Report not found"}, row_count=0)
        return _ok(
            {
                "report": report,
                "address": self._record("addresses", report_id),
                "report_detail": self._record("report_details", report_id),
            },
            meta={"report_id": report_id},
        )

    def get_report_detail_with_products(self, report_id: int) -> dict[str, Any]:
        detail = self.get_report_detail(report_id)
        if not detail.get("data"):
            return detail
        payload = dict(detail["data"])
        payload["products"] = self.get_products(report_id)["data"]
        return _ok(payload, meta={"report_id": report_id})

    def get_report_detail_with_products_and_attributes(self, report_id: int) -> dict[str, Any]:
        detail = self.get_report_detail_with_products(report_id)
        if not detail.get("data"):
            return detail
        payload = dict(detail["data"])
        payload["attributes"] = self.get_attributes(report_id)["data"]
        return _ok(payload, meta={"report_id": report_id})

    def get_task(self, report_id: int) -> dict[str, Any]:
        payload = self._task_payload(report_id)
        task = (payload or {}).get("task")
        if not task:
            return {
                "ok": False,
                "source": "seed",
                "row_count": 0,
                "data": None,
                "meta": {"report_id": report_id, "error": "No operations task found for this report"},
            }
        return _ok(task, meta={"report_id": report_id, "task_id": task.get("TaskID")})

    def get_task_states(self, report_id: int) -> dict[str, Any]:
        payload = self._task_payload(report_id)
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
        return _ok(
            {
                "current_state": active[0] if active else None,
                "active_states": active,
                "state_history": history,
            },
            meta={"report_id": report_id, "task_id": (payload.get("task") or {}).get("TaskID")},
        )

    def get_task_by_id(self, task_id: int) -> dict[str, Any]:
        for report_id, payload in (self._seed.get("task_status") or {}).items():
            task = (payload or {}).get("task") or {}
            if int(task.get("TaskID") or 0) == task_id:
                wrapped = self.get_task_status(int(report_id))
                wrapped["meta"]["lookup_task_id"] = task_id
                return wrapped
        return {
            "ok": False,
            "source": "seed",
            "row_count": 0,
            "data": None,
            "meta": {"task_id": task_id, "error": "Task not found"},
        }

    def get_task_states_by_task_id(self, task_id: int) -> dict[str, Any]:
        found = self.get_task_by_id(task_id)
        if not found.get("data"):
            return found
        report_id = int(found["data"]["task"]["ReportID"])
        return self.get_task_states(report_id)

    def get_customer(self, customer_id: int) -> dict[str, Any]:
        row = self._record("customers", customer_id)
        return _ok(row, meta={"customer_id": customer_id}, row_count=1 if row else 0)

    def get_customer_reports(self, customer_id: int) -> dict[str, Any]:
        rows = self.list_reports(customer_id=customer_id)
        return _ok(rows, meta={"customer_id": customer_id})

    def get_org_node(self, org_node_id: int) -> dict[str, Any]:
        row = self._record("org_nodes", org_node_id)
        return _ok(row, meta={"org_node_id": org_node_id}, row_count=1 if row else 0)

    def get_org_reports(self, org_node_id: int) -> dict[str, Any]:
        return _ok(self.list_reports(org_node_id=org_node_id), meta={"org_node_id": org_node_id})

    def get_profile(self, profile_id: int) -> dict[str, Any]:
        row = self._record("profiles", profile_id)
        return _ok(row, meta={"profile_id": profile_id}, row_count=1 if row else 0)

    def get_order_reports(self, order_id: int) -> dict[str, Any]:
        return _ok(self.list_reports(order_id=order_id), meta={"order_id": order_id})

    def get_related_reports(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("related_reports", report_id), meta={"report_id": report_id})

    def get_images(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("images", report_id), meta={"report_id": report_id})

    def get_application_source(self, report_id: int) -> dict[str, Any]:
        row = self._record("application_sources", report_id)
        return _ok(row, meta={"report_id": report_id}, row_count=1 if row else 0)

    def get_product_capabilities(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("product_capabilities", report_id), meta={"report_id": report_id})

    def get_deliverable_verification(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("deliverable_verification", report_id), meta={"report_id": report_id})

    def get_address(self, report_id: int) -> dict[str, Any]:
        row = self._record("addresses", report_id)
        return _ok(row, meta={"report_id": report_id}, row_count=1 if row else 0)

    def get_associations(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("associations", report_id), meta={"report_id": report_id})

    def get_measurements(self, report_id: int) -> dict[str, Any]:
        return _ok(self._keyed("measurements", report_id), meta={"report_id": report_id})

    def get_invoice_status(self, report_id: int) -> dict[str, Any]:
        row = self._record("invoice_status", report_id)
        return _ok(row, meta={"report_id": report_id}, row_count=1 if row else 0)
