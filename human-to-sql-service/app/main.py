from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from .config import settings
from .models import SqlGenerateRequest
from .services.catalog import list_catalog_databases
from .services.query_router import prepare_or_generate_query

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Generates catalog-validated T-SQL. This service never executes SQL.",
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "execution": "disabled",
    }


@app.get(f"{settings.api_prefix}/catalog/databases")
async def catalog_databases() -> dict[str, Any]:
    databases = list_catalog_databases()
    return {
        "ok": True,
        "row_count": len(databases),
        "data": databases,
        "note": "Registered, query-enabled, and compiled are independent readiness signals.",
    }


@app.post(f"{settings.api_prefix}/sql/generate")
async def generate_sql(payload: SqlGenerateRequest) -> dict[str, Any]:
    result = prepare_or_generate_query(
        prompt=payload.prompt,
        query_mode=payload.query_mode,
        report_id=payload.report_id,
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        organization_node_id=payload.organization_node_id,
        profile_id=payload.profile_id,
        environment=payload.environment,
        server=payload.node_hint,
        database=payload.database,
    )
    if not result.get("ok"):
        status = (
            503
            if result.get("mode")
            in {"catalog_unavailable", "not_configured", "model_error"}
            else 422
        )
        raise HTTPException(status_code=status, detail=result)
    result["execution"] = "not_run"
    return result
