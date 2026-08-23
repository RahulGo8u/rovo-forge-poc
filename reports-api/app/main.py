from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import ApiResponse, DiagnoseDeliveryRequest, DiagnoseDeliveryResponse
from .repository import ReportsRepository
from .services.triage import diagnose_delivery_config
from .validation import (
    CatalogName,
    LimitQuery,
    LookupKind,
    PositiveId,
    SampleLimitQuery,
    TimelineLimitQuery,
    parse_identifier,
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Standalone Reports API for the Triage Agent. "
        "Looks up seeded report, delivery, and operations-task data by identifier. No auth in this POC."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_repo() -> ReportsRepository:
    return ReportsRepository()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "data_source": "seed",
        "auth": "none",
    }


@app.get(f"{settings.api_prefix}/reports/lookup-by-identifier", response_model=ApiResponse)
async def lookup_report_by_identifier(
    value: str = Query(..., min_length=1, max_length=32, description="Numeric identifier"),
    kind: LookupKind = Query(default="auto"),
    limit: LimitQuery = 20,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    number = parse_identifier(value)
    return repo.resolve_identifier(number, kind=kind, limit=limit)


@app.get(f"{settings.api_prefix}/reports/seed-examples", response_model=ApiResponse)
async def list_seed_example_reports(
    limit: SampleLimitQuery = 10,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_sample_reports(limit=limit)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ApiResponse)
async def get_report_by_id(report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)) -> dict[str, Any]:
    result = repo.get_report_by_id(report_id)
    if not result.get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/delivery-snapshot", response_model=ApiResponse)
async def get_delivery_snapshot(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    result = repo.get_overview(report_id)
    if not result.get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/delivery-rules", response_model=ApiResponse)
async def get_delivery_rules(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_delivery_rules(report_id)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/products", response_model=ApiResponse)
async def get_report_products(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_products(report_id)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/attributes", response_model=ApiResponse)
async def get_report_attributes(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_attributes(report_id)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/report-status-history", response_model=ApiResponse)
async def get_report_status_history(
    report_id: PositiveId,
    limit: TimelineLimitQuery = 25,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_report_status_history(report_id, limit=limit)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/task-status", response_model=ApiResponse)
async def get_report_task_status(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    if not repo.get_report_by_id(report_id).get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    result = repo.get_task_status(report_id)
    if not result.get("data"):
        raise HTTPException(status_code=404, detail=f"No operations task found for report {report_id}")
    return result


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/customer-email-settings", response_model=ApiResponse)
async def get_customer_email_settings(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    report = repo.get_report_by_id(report_id)
    if not report.get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    org_node_id = report["data"].get("OrgNodeID")
    profile_id = report["data"].get("ProfileID")
    return repo.get_email_availability(org_node_id=org_node_id, profile_id=profile_id)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/delivery-diagnosis", response_model=DiagnoseDeliveryResponse)
async def get_delivery_diagnosis(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> DiagnoseDeliveryResponse:
    return diagnose_delivery_config(repo, lookup=report_id, lookup_kind="ReportID")


@app.get(f"{settings.api_prefix}/org-nodes/{{org_node_id}}/inherited-delivery-rules", response_model=ApiResponse)
async def get_inherited_org_delivery_rules(
    org_node_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_org_delivery_rules(org_node_id)


@app.get(f"{settings.api_prefix}/reference/{{catalog_name}}", response_model=ApiResponse)
async def get_reference_catalog(
    catalog_name: CatalogName,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_catalog(catalog_name)


@app.post(f"{settings.api_prefix}/triage/diagnose-delivery-config", response_model=DiagnoseDeliveryResponse)
async def diagnose_delivery_config_endpoint(
    payload: DiagnoseDeliveryRequest,
    repo: ReportsRepository = Depends(get_repo),
) -> DiagnoseDeliveryResponse:
    number = parse_identifier(payload.lookup)
    return diagnose_delivery_config(repo, lookup=number, lookup_kind=payload.lookup_kind)


@app.get(f"{settings.api_prefix}/meta/endpoints")
async def list_endpoints() -> dict[str, Any]:
    prefix = settings.api_prefix
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "data_source": "seed",
        "auth": "none",
        "sample_identifiers": {
            "ReportID": [44840403, 72391747, 50110200, 61220311],
            "OrderID": [99100234, 100334455, 110445566, 120556677],
            "CustomerID": [120045, 220118, 330201, 440312],
            "OrgNodeID": [88012, 145002, 200101, 310202],
            "ProfileID": [55001, 66002, 77003, 88004],
        },
        "endpoints": [
            {"method": "GET", "path": "/health", "description": "Service health check"},
            {"method": "GET", "path": f"{prefix}/reports/lookup-by-identifier", "description": "Find reports from ReportID, OrderID, CustomerID, OrgNodeID, or ProfileID"},
            {"method": "GET", "path": f"{prefix}/reports/seed-examples", "description": "List seeded example reports"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}", "description": "Get report header by ReportID"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/delivery-snapshot", "description": "Full delivery + status + task snapshot"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/delivery-rules", "description": "File delivery rules for the report"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/products", "description": "Products on the report"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/attributes", "description": "Report attributes"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/report-status-history", "description": "Report lifecycle status history (not operations task)"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/task-status", "description": "Operations Task + TaskState for the report"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/customer-email-settings", "description": "Customer email availability settings"},
            {"method": "GET", "path": f"{prefix}/reports/{{report_id}}/delivery-diagnosis", "description": "Diagnose delivery configuration for a known ReportID"},
            {"method": "GET", "path": f"{prefix}/org-nodes/{{org_node_id}}/inherited-delivery-rules", "description": "Org-node inherited delivery rules"},
            {"method": "GET", "path": f"{prefix}/reference/{{catalog_name}}", "description": "delivery-methods, file-types, email-types"},
            {"method": "POST", "path": f"{prefix}/triage/diagnose-delivery-config", "description": "Diagnose delivery configuration from any identifier"},
        ],
    }
