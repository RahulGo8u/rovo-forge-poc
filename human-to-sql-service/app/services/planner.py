from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from sqlglot import exp, parse

SCHEMA_ROOT = Path(__file__).resolve().parent.parent.parent / "schema"
ALLOWED_SCHEMA_PACKS = {("test", "db01", "DB7222")}

PLANNER_TABLES = (
    "Report",
    "ReportStatus",
    "Status",
    "SubStatus",
    "ReportFileDeliveryRule",
    "ReportAddress",
    "ReportProduct",
    "ReportAttribute",
    "CustomerEmailAvailability",
    "DeliveryMethod",
    "EmailType",
    "Product",
    "Profile",
    "Order",
    "ReportDetail",
    "ReportImage",
    "DeliverableVerificationRule",
)

IdentifierMap = dict[str, int | None]
SqlBuilder = Callable[[dict[str, list[dict[str, Any]]], IdentifierMap], tuple[str, dict[str, int], list[str]]]


@dataclass(frozen=True)
class Intent:
    name: str
    phrases: tuple[str, ...]
    tokens: tuple[str, ...]
    builder: SqlBuilder


@lru_cache
def load_schema_pack(environment: str = "test", server: str = "db01", database: str = "DB7222") -> dict[str, Any]:
    key = (environment, server, database)
    if key not in ALLOWED_SCHEMA_PACKS:
        raise ValueError(f"Schema pack is not allowlisted: {environment}/{server}/{database}")
    folder = (SCHEMA_ROOT / environment / server / database).resolve()
    if SCHEMA_ROOT.resolve() not in folder.parents:
        raise ValueError("Schema pack path escapes the schema root")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    tables = json.loads((folder / "tables.json").read_text(encoding="utf-8"))
    return {"manifest": manifest, "tables": tables, "path": str(folder)}


def compact_schema(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    compact: dict[str, list[str]] = {}
    for name in PLANNER_TABLES:
        cols = tables.get(name)
        if cols:
            compact[name] = [c["name"] for c in cols]
    return compact


def _has_column(tables: dict[str, list[dict[str, Any]]], table: str, column: str) -> bool:
    wanted = column.casefold()
    return any(str(c["name"]).casefold() == wanted for c in tables.get(table, []))


def _require_columns(
    tables: dict[str, list[dict[str, Any]]],
    requirements: dict[str, tuple[str, ...]],
) -> None:
    missing = [
        f"{table}.{column}"
        for table, columns in requirements.items()
        for column in columns
        if not _has_column(tables, table, column)
    ]
    if missing:
        raise ValueError(f"Schema pack is missing required columns: {', '.join(missing)}")


def _extract_identifiers(prompt: str, supplied: IdentifierMap) -> IdentifierMap:
    identifiers = dict(supplied)
    patterns = {
        "report_id": r"\breport(?:\s*id)?\s*(?:is|=|:|#)?\s*(\d{5,})\b",
        "order_id": r"\border(?:\s*id)?\s*(?:is|=|:|#)?\s*(\d{5,})\b",
        "customer_id": r"\bcustomer(?:\s*id)?\s*(?:is|=|:|#)?\s*(\d{5,})\b",
        "organization_node_id": r"\b(?:organization|org)(?:\s*node)?(?:\s*id)?\s*(?:is|=|:|#)?\s*(\d{3,})\b",
        "profile_id": r"\bprofile(?:\s*id)?\s*(?:is|=|:|#)?\s*(\d{3,})\b",
    }
    for name, pattern in patterns.items():
        if identifiers.get(name) is None:
            match = re.search(pattern, prompt, flags=re.IGNORECASE)
            if match:
                identifiers[name] = int(match.group(1))
    return identifiers


def _report_scope(alias: str, identifiers: IdentifierMap) -> tuple[str, dict[str, int]]:
    choices = (
        ("report_id", "ReportID", "ReportID"),
        ("order_id", "OrderID", "OrderID"),
        ("customer_id", "CustomerID", "CustomerID"),
        ("organization_node_id", "OrgNodeID", "OrganizationNodeID"),
        ("profile_id", "CustomerID", "ProfileID"),
    )
    for key, column, parameter in choices:
        value = identifiers.get(key)
        if value is not None:
            return f"{alias}.{column} = @{parameter}", {parameter: value}
    raise ValueError("A ReportID, OrderID, CustomerID, OrganizationNodeID, or ProfileID is required")


def _build_status(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    _require_columns(
        tables,
        {
            "Report": ("ReportID", "OrderID", "CustomerID", "OrgNodeID"),
            "ReportStatus": (
                "ReportStatusID", "ReportID", "StatusID", "SubStatusID",
                "StatusTimeStamp", "ExpiredDate", "UserEmail",
            ),
            "Status": ("StatusID", "Name", "ExternalName"),
            "SubStatus": ("SubStatusID", "Name", "ExternalName"),
        },
    )
    where, params = _report_scope("r", identifiers)
    sql = f"""\
SELECT TOP (100)
  rs.ReportStatusID,
  rs.ReportID,
  rs.StatusID,
  st.Name AS StatusName,
  st.ExternalName AS StatusExternalName,
  rs.SubStatusID,
  ss.Name AS SubStatusName,
  ss.ExternalName AS SubStatusExternalName,
  rs.StatusTimeStamp,
  rs.ExpiredDate,
  rs.UserEmail,
  CASE WHEN rs.ExpiredDate IS NULL THEN 1 ELSE 0 END AS IsCurrent
FROM dbo.Report AS r
INNER JOIN dbo.ReportStatus AS rs ON rs.ReportID = r.ReportID
INNER JOIN dbo.Status AS st ON st.StatusID = rs.StatusID
INNER JOIN dbo.SubStatus AS ss ON ss.SubStatusID = rs.SubStatusID
WHERE {where}
ORDER BY rs.StatusTimeStamp DESC;"""
    return sql, params, ["Report", "ReportStatus", "Status", "SubStatus"]


def _build_delivery_rules(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    _require_columns(
        tables,
        {
            "Report": ("ReportID", "OrderID", "CustomerID", "OrgNodeID"),
            "ReportFileDeliveryRule": (
                "Id", "ReportID", "OrgNodeID", "ProfileID", "ProductID",
                "FileTypeID", "FileTypeGroupID", "DeliveryMethodID",
                "EmailTypeID", "Disabled", "OverrideChildren",
            ),
        },
    )
    where, params = _report_scope("r", identifiers)
    sql = f"""\
SELECT TOP (200)
  r.ReportID,
  rules.Id AS DeliveryRuleID,
  CASE
    WHEN rules.ReportID = r.ReportID THEN 'report'
    WHEN rules.ProfileID = r.CustomerID THEN 'profile'
    WHEN rules.OrgNodeID = r.OrgNodeID THEN 'organization'
    ELSE 'unknown'
  END AS RuleScope,
  rules.OrgNodeID,
  rules.ProfileID,
  rules.ProductID,
  rules.FileTypeID,
  rules.FileTypeGroupID,
  rules.DeliveryMethodID,
  rules.EmailTypeID,
  rules.Disabled,
  rules.OverrideChildren
FROM dbo.Report AS r
INNER JOIN dbo.ReportFileDeliveryRule AS rules
  ON rules.ReportID = r.ReportID
  OR (
    rules.ReportID IS NULL
    AND (
      rules.ProfileID = r.CustomerID
      OR rules.OrgNodeID = r.OrgNodeID
    )
  )
WHERE {where}
ORDER BY RuleScope, rules.Id;"""
    return sql, params, ["Report", "ReportFileDeliveryRule"]


def _build_email_settings(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    _require_columns(
        tables,
        {
            "Report": ("ReportID", "OrderID", "CustomerID", "OrgNodeID"),
            "CustomerEmailAvailability": (
                "CustomerEmailAvailabilityId", "ProfileId", "ProductId",
                "ApplicationSourceId", "EmailTypeId", "EmailTemplateId",
                "IsEnabled", "OverrideChildren", "OrgNodeId",
            ),
        },
    )
    where, params = _report_scope("r", identifiers)
    sql = f"""\
SELECT TOP (100)
  r.ReportID,
  settings.CustomerEmailAvailabilityId,
  CASE
    WHEN settings.ProfileId = r.CustomerID THEN 'profile'
    WHEN settings.OrgNodeId = r.OrgNodeID THEN 'organization'
    ELSE 'unknown'
  END AS SettingScope,
  settings.ProfileId,
  settings.OrgNodeId,
  settings.ProductId,
  settings.ApplicationSourceId,
  settings.EmailTypeId,
  settings.EmailTemplateId,
  settings.IsEnabled,
  settings.OverrideChildren
FROM dbo.Report AS r
INNER JOIN dbo.CustomerEmailAvailability AS settings
  ON settings.ProfileId = r.CustomerID
  OR settings.OrgNodeId = r.OrgNodeID
WHERE {where}
ORDER BY SettingScope, settings.CustomerEmailAvailabilityId;"""
    return sql, params, ["Report", "CustomerEmailAvailability"]


def _build_address(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    _require_columns(
        tables,
        {
            "Report": ("ReportID", "OrderID", "CustomerID", "OrgNodeID"),
            "ReportAddress": (
                "ReportAddressID", "ReportID", "Address", "Address2", "City",
                "State", "Zip", "Country", "Latitude", "Longitude",
                "AddressTypeID", "County",
            ),
        },
    )
    where, params = _report_scope("r", identifiers)
    sql = f"""\
SELECT TOP (50)
  address.ReportAddressID,
  address.ReportID,
  address.Address,
  address.Address2,
  address.City,
  address.State,
  address.Zip,
  address.Country,
  address.Latitude,
  address.Longitude,
  address.AddressTypeID,
  address.County
FROM dbo.Report AS r
INNER JOIN dbo.ReportAddress AS address ON address.ReportID = r.ReportID
WHERE {where}
ORDER BY address.ReportAddressID;"""
    return sql, params, ["Report", "ReportAddress"]


def _build_products(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    _require_columns(
        tables,
        {
            "Report": ("ReportID", "OrderID", "CustomerID", "OrgNodeID"),
            "ReportProduct": ("ReportProductID", "ReportID", "ProductID"),
            "Product": ("ProductID", "Name", "Abbreviation", "Active"),
        },
    )
    where, params = _report_scope("r", identifiers)
    sql = f"""\
SELECT TOP (100)
  report_product.ReportProductID,
  report_product.ReportID,
  report_product.ProductID,
  product.Name AS ProductName,
  product.Abbreviation AS ProductAbbreviation,
  product.Active AS ProductActive
FROM dbo.Report AS r
INNER JOIN dbo.ReportProduct AS report_product ON report_product.ReportID = r.ReportID
INNER JOIN dbo.Product AS product ON product.ProductID = report_product.ProductID
WHERE {where}
ORDER BY report_product.ReportProductID;"""
    return sql, params, ["Report", "ReportProduct", "Product"]


def _build_header(
    tables: dict[str, list[dict[str, Any]]], identifiers: IdentifierMap
) -> tuple[str, dict[str, int], list[str]]:
    columns = ("ReportID", "CustomerID", "OrgNodeID", "OrderID", "City", "State", "Zip", "OrderPlacedDate")
    _require_columns(tables, {"Report": columns})
    where, params = _report_scope("report", identifiers)
    sql = f"""\
SELECT TOP (50)
  report.ReportID,
  report.CustomerID,
  report.OrgNodeID,
  report.OrderID,
  report.City,
  report.State,
  report.Zip,
  report.OrderPlacedDate
FROM dbo.Report AS report
WHERE {where}
ORDER BY report.ReportID;"""
    return sql, params, ["Report"]


INTENTS = (
    Intent(
        "report-status-timeline",
        ("current status", "status history", "status timeline", "substatus history"),
        ("status", "substatus", "timeline", "completed", "processing"),
        _build_status,
    ),
    Intent(
        "report-file-delivery-rules",
        ("file delivery rules", "delivery rules", "dxf setup", "delivery configuration"),
        ("delivery", "rule", "rules", "dxf"),
        _build_delivery_rules,
    ),
    Intent(
        "customer-email-notification-settings",
        ("email notification settings", "customer email settings", "email availability"),
        ("email", "notification", "notifications"),
        _build_email_settings,
    ),
    Intent(
        "report-property-address",
        ("property address", "report address", "city and zip"),
        ("address", "city", "zip", "location"),
        _build_address,
    ),
    Intent(
        "report-ordered-products",
        ("ordered products", "products ordered", "report products"),
        ("product", "products"),
        _build_products,
    ),
    Intent(
        "report-header",
        ("report header", "report details", "find report", "report summary"),
        ("header", "summary", "find"),
        _build_header,
    ),
)


def _classify(prompt: str) -> tuple[Intent | None, float, list[str]]:
    text = prompt.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    scored: list[tuple[int, Intent]] = []
    strong_matches: list[str] = []
    for intent in INTENTS:
        matched_phrases = [phrase for phrase in intent.phrases if phrase in text]
        score = len(matched_phrases) * 4
        score += sum(1 for token in intent.tokens if token in tokens)
        if score:
            scored.append((score, intent))
        if matched_phrases:
            strong_matches.append(intent.name)
    if not scored:
        return None, 0.0, []
    if len(strong_matches) > 1:
        return None, 0.0, strong_matches
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    tied = [intent.name for score, intent in scored if score == best_score]
    if len(tied) > 1:
        return None, 0.0, tied
    confidence = min(0.99, 0.55 + (best_score * 0.06))
    return best, confidence, []


def validate_read_only_sql(
    sql: str,
    *,
    allowed_tables: list[str],
    params: dict[str, int],
    require_exact_params: bool = True,
) -> dict[str, Any]:
    """Reject anything that is not a single, capped, read-only SELECT on allowed tables.

    Templates must bind every parameter they were given, so they use exact matching.
    Generated SQL may legitimately ignore an identifier the caller supplied, so it
    only requires that referenced parameters were actually provided.
    """
    statements = parse(sql, read="tsql")
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is allowed")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise ValueError("Only SELECT or WITH...SELECT statements are allowed")
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
        exp.Alter, exp.Command, exp.Into,
    )
    if any(statement.find(node_type) is not None for node_type in forbidden):
        raise ValueError("SQL contains a forbidden write, DDL, command, or SELECT INTO operation")

    expected_tables = {name.casefold() for name in allowed_tables}
    actual_tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        if table.catalog:
            raise ValueError("Cross-database or linked-server names are not allowed")
        if table.db and table.db.casefold() != "dbo":
            raise ValueError(f"Only dbo tables are allowed, found {table.db}.{table.name}")
        actual_tables.add(table.name.casefold())
    if not actual_tables or not actual_tables.issubset(expected_tables):
        unexpected = sorted(actual_tables - expected_tables)
        raise ValueError(f"SQL references non-allowlisted tables: {unexpected}")
    if statement.find(exp.Star) is not None:
        raise ValueError("SELECT * is not allowed")

    actual_params = {node.name.casefold() for node in statement.find_all(exp.Parameter)}
    expected_params = {name.casefold() for name in params}
    if require_exact_params:
        if actual_params != expected_params:
            raise ValueError(
                f"SQL parameters do not match values: SQL={sorted(actual_params)}, values={sorted(expected_params)}"
            )
    elif not actual_params.issubset(expected_params):
        unbound = sorted(actual_params - expected_params)
        raise ValueError(f"SQL references parameters that were not supplied: {unbound}")
    if statement.find(exp.Limit) is None:
        raise ValueError("Every generated query must include TOP or another row limit")
    return {
        "read_only": True,
        "single_statement": True,
        "tables": sorted(actual_tables),
        "parameters": sorted(actual_params),
        "row_limited": True,
    }


def prepare_query(
    *,
    prompt: str,
    report_id: int | None = None,
    order_id: int | None = None,
    customer_id: int | None = None,
    organization_node_id: int | None = None,
    profile_id: int | None = None,
    environment: str = "test",
    server: str = "db01",
    database: str = "DB7222",
) -> dict[str, Any]:
    pack = load_schema_pack(environment, server, database)
    tables: dict[str, list[dict[str, Any]]] = pack["tables"]
    text = (prompt or "").strip()
    if not text:
        return {
            "ok": False,
            "mode": "no_match",
            "error": "Prompt is required.",
            "schema": pack["manifest"],
        }

    # Identifier parameters must come from typed request fields, never prose.
    identifiers = {
        "report_id": report_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "organization_node_id": organization_node_id,
        "profile_id": profile_id,
    }
    if not any(identifiers.values()):
        return {
            "ok": False,
            "mode": "no_match",
            "error": "Need a ReportID or OrderID in the prompt or request body.",
            "schema": pack["manifest"],
            "compact_schema": compact_schema(tables),
        }

    intent, confidence, ambiguity = _classify(text)
    if intent is None:
        return {
            "ok": False,
            "mode": "no_match",
            "error": "Prompt is ambiguous." if ambiguity else "No supported query intent matched the prompt.",
            "candidate_intents": ambiguity,
            "schema": pack["manifest"],
            "compact_schema": compact_schema(tables),
        }

    try:
        sql, params, used = intent.builder(tables, identifiers)
        safety = validate_read_only_sql(sql, allowed_tables=used, params=params)
    except ValueError as error:
        return {
            "ok": False,
            "mode": "no_match",
            "error": str(error),
            "intent": intent.name,
            "schema": pack["manifest"],
        }

    return {
        "ok": True,
        "mode": "template",
        "intent": intent.name,
        "confidence": confidence,
        "sql": sql,
        "params": params,
        "tables_used": used,
        "safety": safety,
        "schema": pack["manifest"],
        "execution": "not_run",
        "note": "Planner only: SQL was prepared and validated but not executed.",
    }
