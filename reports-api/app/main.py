from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from .auth import require_api_key
from .config import settings
from .models import (
    ApiResponse,
    DiagnoseDeliveryRequest,
    DiagnoseDeliveryResponse,
)
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
        "All /api/v1 routes require header X-API-Key (or Authorization: Bearer). "
        "/health is public for Render health checks."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix=settings.api_prefix, dependencies=[Depends(require_api_key)])


def get_repo() -> ReportsRepository:
    return ReportsRepository()


def require_report(repo: ReportsRepository, report_id: int) -> dict[str, Any]:
    report = repo.get_report_by_id(report_id).get("data")
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


def require_data(result: dict[str, Any], message: str) -> dict[str, Any]:
    if not result.get("data"):
        raise HTTPException(status_code=404, detail=message)
    return result


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "data_source": "seed",
        "auth": "api_key",
        "public_paths": ["/health"],
    }


@api.get("/reports/find-by-identifier", response_model=ApiResponse)
async def find_reports_by_identifier(
    value: str = Query(..., min_length=1, max_length=32, description="Numeric identifier"),
    kind: LookupKind = Query(default="auto"),
    limit: LimitQuery = 20,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    number = parse_identifier(value)
    return repo.resolve_identifier(number, kind=kind, limit=limit)


@api.get("/reports/example-reports-in-seed-data", response_model=ApiResponse)
async def list_example_reports_in_seed_data(
    limit: SampleLimitQuery = 10,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_sample_reports(limit=limit)


@api.get("/reports/{report_id}", response_model=ApiResponse)
async def get_report_header(report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_report_by_id(report_id)


@api.get("/reports/{report_id}/current-status-with-history", response_model=ApiResponse)
async def get_report_current_status_with_history(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_report_status(report_id)


@api.get("/reports/{report_id}/status-change-history", response_model=ApiResponse)
async def get_report_status_change_history(
    report_id: PositiveId,
    limit: TimelineLimitQuery = 25,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_report_status_history(report_id, limit=limit)


@api.get("/reports/{report_id}/operations-workflow-status", response_model=ApiResponse)
async def get_report_operations_workflow_status(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(
        repo.get_task_status(report_id),
        f"No operations workflow task found for report {report_id}",
    )


@api.get("/reports/{report_id}/operations-workflow-task", response_model=ApiResponse)
async def get_report_operations_workflow_task(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(
        repo.get_task(report_id),
        f"No operations workflow task found for report {report_id}",
    )


@api.get("/reports/{report_id}/operations-workflow-task-states", response_model=ApiResponse)
async def get_report_operations_workflow_task_states(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(
        repo.get_task_states(report_id),
        f"No operations workflow task found for report {report_id}",
    )


@api.get("/reports/{report_id}/details-with-address-and-measurements", response_model=ApiResponse)
async def get_report_details_with_address_and_measurements(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_report_detail(report_id), f"Report {report_id} not found")


@api.get("/reports/{report_id}/details-with-ordered-products", response_model=ApiResponse)
async def get_report_details_with_ordered_products(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(
        repo.get_report_detail_with_products(report_id), f"Report {report_id} not found"
    )


@api.get(
    "/reports/{report_id}/details-with-ordered-products-and-attributes",
    response_model=ApiResponse,
)
async def get_report_details_with_ordered_products_and_attributes(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(
        repo.get_report_detail_with_products_and_attributes(report_id),
        f"Report {report_id} not found",
    )


@api.get("/reports/{report_id}/delivery-configuration-snapshot", response_model=ApiResponse)
async def get_report_delivery_configuration_snapshot(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_overview(report_id), f"Report {report_id} not found")


@api.get("/reports/{report_id}/file-delivery-rules", response_model=ApiResponse)
async def get_report_file_delivery_rules(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_delivery_rules(report_id)


@api.get("/reports/{report_id}/delivery-configuration-diagnosis", response_model=DiagnoseDeliveryResponse)
async def get_report_delivery_configuration_diagnosis(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> DiagnoseDeliveryResponse:
    return diagnose_delivery_config(repo, lookup=report_id, lookup_kind="ReportID")


@api.get("/reports/{report_id}/customer-email-notification-settings", response_model=ApiResponse)
async def get_report_customer_email_notification_settings(
    report_id: PositiveId,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    report = require_report(repo, report_id)
    return repo.get_email_availability(
        org_node_id=report.get("OrgNodeID"), profile_id=report.get("ProfileID")
    )


@api.get("/reports/{report_id}/deliverable-verification-rules", response_model=ApiResponse)
async def get_report_deliverable_verification_rules(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_deliverable_verification(report_id)


@api.get("/reports/{report_id}/product-file-generation-capabilities", response_model=ApiResponse)
async def get_report_product_file_generation_capabilities(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_product_capabilities(report_id)


@api.get("/reports/{report_id}/ordered-products", response_model=ApiResponse)
async def get_report_ordered_products(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_products(report_id)


@api.get("/reports/{report_id}/report-attributes", response_model=ApiResponse)
async def get_report_attributes(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_attributes(report_id)


@api.get("/reports/{report_id}/property-address", response_model=ApiResponse)
async def get_report_property_address(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(repo.get_address(report_id), f"No property address for report {report_id}")


@api.get("/reports/{report_id}/measurement-values", response_model=ApiResponse)
async def get_report_measurement_values(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_measurements(report_id)


@api.get("/reports/{report_id}/source-imagery", response_model=ApiResponse)
async def get_report_source_imagery(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_images(report_id)


@api.get("/reports/{report_id}/profile-and-organization-associations", response_model=ApiResponse)
async def get_report_profile_and_organization_associations(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_associations(report_id)


@api.get("/reports/{report_id}/related-reports", response_model=ApiResponse)
async def get_related_reports(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return repo.get_related_reports(report_id)


@api.get("/reports/{report_id}/ordering-application-source", response_model=ApiResponse)
async def get_report_ordering_application_source(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(
        repo.get_application_source(report_id),
        f"No ordering application source for report {report_id}",
    )


@api.get("/reports/{report_id}/invoice-status", response_model=ApiResponse)
async def get_report_invoice_status(
    report_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_report(repo, report_id)
    return require_data(repo.get_invoice_status(report_id), f"No invoice status for report {report_id}")


@api.get("/operations-workflow-tasks/{task_id}", response_model=ApiResponse)
async def get_operations_workflow_task_by_task_id(
    task_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_task_by_id(task_id), f"Operations workflow task {task_id} not found")


@api.get("/operations-workflow-tasks/{task_id}/task-states", response_model=ApiResponse)
async def get_operations_workflow_task_states_by_task_id(
    task_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(
        repo.get_task_states_by_task_id(task_id),
        f"Operations workflow task {task_id} not found",
    )


@api.get("/customers/{customer_id}", response_model=ApiResponse)
async def get_customer(customer_id: PositiveId, repo: ReportsRepository = Depends(get_repo)) -> dict[str, Any]:
    return require_data(repo.get_customer(customer_id), f"Customer {customer_id} not found")


@api.get("/customers/{customer_id}/reports", response_model=ApiResponse)
async def get_reports_for_customer(
    customer_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_data(repo.get_customer(customer_id), f"Customer {customer_id} not found")
    return repo.get_customer_reports(customer_id)


@api.get("/customers/{customer_id}/email-notification-settings", response_model=ApiResponse)
async def get_customer_email_notification_settings(
    customer_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    customer = require_data(repo.get_customer(customer_id), f"Customer {customer_id} not found")["data"]
    return repo.get_email_availability(
        org_node_id=customer.get("DefaultOrgNodeID"),
        profile_id=customer.get("DefaultProfileID"),
    )


@api.get("/organization-nodes/{org_node_id}", response_model=ApiResponse)
async def get_organization_node(
    org_node_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_org_node(org_node_id), f"Organization node {org_node_id} not found")


@api.get("/organization-nodes/{org_node_id}/reports", response_model=ApiResponse)
async def get_reports_for_organization_node(
    org_node_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    require_data(repo.get_org_node(org_node_id), f"Organization node {org_node_id} not found")
    return repo.get_org_reports(org_node_id)


@api.get("/organization-nodes/{org_node_id}/inherited-file-delivery-rules", response_model=ApiResponse)
async def get_inherited_file_delivery_rules_for_organization_node(
    org_node_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return repo.get_org_delivery_rules(org_node_id)


@api.get("/recipient-profiles/{profile_id}", response_model=ApiResponse)
async def get_recipient_profile(
    profile_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_profile(profile_id), f"Recipient profile {profile_id} not found")


@api.get("/orders/{order_id}/reports", response_model=ApiResponse)
async def get_reports_for_order(
    order_id: PositiveId, repo: ReportsRepository = Depends(get_repo)
) -> dict[str, Any]:
    return require_data(repo.get_order_reports(order_id), f"No reports found for order {order_id}")


@api.get("/reference-data/{catalog_name}", response_model=ApiResponse)
async def get_reference_data_catalog(
    catalog_name: CatalogName,
    repo: ReportsRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_catalog(catalog_name)


@api.post("/triage/diagnose-delivery-configuration", response_model=DiagnoseDeliveryResponse)
async def diagnose_delivery_configuration(
    payload: DiagnoseDeliveryRequest,
    repo: ReportsRepository = Depends(get_repo),
) -> DiagnoseDeliveryResponse:
    number = parse_identifier(payload.lookup)
    return diagnose_delivery_config(repo, lookup=number, lookup_kind=payload.lookup_kind)


@api.get("/metadata/endpoint-catalog")
async def get_endpoint_catalog() -> dict[str, Any]:
    prefix = settings.api_prefix
    endpoints: list[dict[str, Any]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            endpoints.append(
                {
                    "method": method,
                    "path": route.path,
                    "requires_api_key": route.path.startswith(prefix),
                    "operation": route.name,
                }
            )
    endpoints.sort(key=lambda item: (item["path"], item["method"]))
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "data_source": "seed",
        "endpoint_count": len(endpoints),
        "authentication": {
            "type": "api_key",
            "header": "X-API-Key",
            "alternate_header": "Authorization: Bearer <key>",
        },
        "sample_identifiers": {
            "ReportID": [44840403, 72391747, 50110200, 61220311],
            "OrderID": [99100234, 100334455, 110445566, 120556677],
            "CustomerID": [120045, 220118, 330201, 440312],
            "OrgNodeID": [88012, 145002, 200101, 310202],
            "ProfileID": [55001, 66002, 77003, 88004],
            "TaskID": [90044840403, 90072391747, 90050110200, 90061220311],
        },
        "triage_entry_points": {
            "report_status_now_and_history": f"{prefix}/reports/{{report_id}}/current-status-with-history",
            "report_status_change_history": f"{prefix}/reports/{{report_id}}/status-change-history",
            "operations_workflow_status": f"{prefix}/reports/{{report_id}}/operations-workflow-status",
            "operations_workflow_task": f"{prefix}/reports/{{report_id}}/operations-workflow-task",
            "operations_workflow_task_states": f"{prefix}/reports/{{report_id}}/operations-workflow-task-states",
            "report_details": f"{prefix}/reports/{{report_id}}/details-with-address-and-measurements",
            "report_details_with_products": f"{prefix}/reports/{{report_id}}/details-with-ordered-products",
            "report_details_with_products_and_attributes": f"{prefix}/reports/{{report_id}}/details-with-ordered-products-and-attributes",
            "operations_workflow_task_by_task_id": f"{prefix}/operations-workflow-tasks/{{task_id}}",
            "operations_workflow_task_states_by_task_id": f"{prefix}/operations-workflow-tasks/{{task_id}}/task-states",
            "delivery_configuration_diagnosis": f"{prefix}/reports/{{report_id}}/delivery-configuration-diagnosis",
        },
        "endpoints": endpoints,
    }


app.include_router(api)
