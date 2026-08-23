from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import ApiResponse, QuickInvestigateRequest, QuickInvestigateResponse
from .repository import ReportsRepository
from .services.triage import quick_investigate
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
        "Looks up seeded report data by identifier. No auth in this POC."
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


@app.get(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ApiResponse)
async def get_report_by_id(report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)) -> dict[str, Any]:
    result = repo.get_report_by_id(report_id)
    if not result.get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return result


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/overview", response_model=ApiResponse)
async def get_report_overview(
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


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/status-timeline", response_model=ApiResponse)
async def get_status_timeline(
    report_id: PositiveId,
    limit: TimelineLimitQuery = 25,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_status_timeline(report_id, limit=limit)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/email-availability", response_model=ApiResponse)
async def get_email_availability(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    report = repo.get_report_by_id(report_id)
    if not report.get("data"):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    org_node_id = report["data"].get("OrgNodeID")
    profile_id = report["data"].get("ProfileID")
    return repo.get_email_availability(org_node_id=org_node_id, profile_id=profile_id)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/delivery-analysis", response_model=QuickInvestigateResponse)
async def get_delivery_analysis(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> QuickInvestigateResponse:
    return quick_investigate(repo, lookup=report_id, lookup_kind="ReportID")


@app.get(f"{settings.api_prefix}/resolve", response_model=ApiResponse)
async def resolve_identifier(
    value: str = Query(..., min_length=1, max_length=32, description="Numeric identifier"),
    kind: LookupKind = Query(default="auto"),
    limit: LimitQuery = 20,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    number = parse_identifier(value)
    return repo.resolve_identifier(number, kind=kind, limit=limit)


@app.get(f"{settings.api_prefix}/org-nodes/{{org_node_id}}/delivery-rules", response_model=ApiResponse)
async def get_org_delivery_rules(
    org_node_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_org_delivery_rules(org_node_id)


@app.get(f"{settings.api_prefix}/catalog/{{catalog_name}}", response_model=ApiResponse)
async def get_catalog(
    catalog_name: CatalogName,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_catalog(catalog_name)


@app.get(f"{settings.api_prefix}/samples/reports", response_model=ApiResponse)
async def get_sample_reports(
    limit: SampleLimitQuery = 10,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_sample_reports(limit=limit)


@app.post(f"{settings.api_prefix}/triage/quick-investigate", response_model=QuickInvestigateResponse)
async def triage_quick_investigate(
    payload: QuickInvestigateRequest,
    repo: ReportsRepository = Depends(get_repo),
) -> QuickInvestigateResponse:
    number = parse_identifier(payload.lookup)
    return quick_investigate(repo, lookup=number, lookup_kind=payload.lookup_kind)


@app.get(f"{settings.api_prefix}/meta/endpoints")
async def list_endpoints() -> dict[str, Any]:
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
            {"method": "GET", "path": "/health", "description": "Render health check"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}", "description": "Get report by ID"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/overview", "description": "Full report overview"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/delivery-rules", "description": "Delivery rules for report"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/products", "description": "Products on report"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/attributes", "description": "Report attributes"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/status-timeline", "description": "Report status history"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/email-availability", "description": "Customer email availability"},
            {"method": "GET", "path": f"{settings.api_prefix}/reports/{{report_id}}/delivery-analysis", "description": "Delivery triage verdict for report"},
            {"method": "GET", "path": f"{settings.api_prefix}/resolve", "description": "Resolve identifier to candidate reports"},
            {"method": "GET", "path": f"{settings.api_prefix}/org-nodes/{{org_node_id}}/delivery-rules", "description": "Org-node inherited delivery rules"},
            {"method": "GET", "path": f"{settings.api_prefix}/catalog/{{catalog_name}}", "description": "Reference catalogs"},
            {"method": "GET", "path": f"{settings.api_prefix}/samples/reports", "description": "Sample reports for testing"},
            {"method": "POST", "path": f"{settings.api_prefix}/triage/quick-investigate", "description": "Quick investigate by identifier (JSON body)"},
        ],
    }
