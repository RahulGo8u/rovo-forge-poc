"""Choose between reviewed SQL templates and schema-driven SQL generation."""
from __future__ import annotations

import re
from typing import Any, Literal

from ..config import settings
from .nl2sql import generate_sql, materialize_bound_params
from .planner import INTENTS, prepare_query
from .target_router import resolve_target

QueryMode = Literal["auto", "templates_only", "generated_only"]

GENERATED_DIRECTIVES = (
    re.compile(r"\b(?:do\s+not|don't|dont)\s+use\s+(?:the\s+)?templates?\b", re.I),
    re.compile(r"\bwithout\s+(?:using\s+)?templates?\b", re.I),
    re.compile(r"\bno\s+templates?\b", re.I),
)
TEMPLATE_DIRECTIVES = (
    re.compile(r"\buse\s+(?:the\s+)?templates?\s+only\b", re.I),
    re.compile(r"\btemplates?\s+only\b", re.I),
    re.compile(r"\bonly\s+use\s+(?:the\s+)?templates?\b", re.I),
)


def detect_prompt_mode(prompt: str) -> tuple[QueryMode | None, str]:
    """Read an optional routing instruction and remove it from the question."""
    generated = any(pattern.search(prompt) for pattern in GENERATED_DIRECTIVES)
    templates = any(pattern.search(prompt) for pattern in TEMPLATE_DIRECTIVES)
    if generated and templates:
        raise ValueError("Prompt asks both to avoid templates and to use templates only.")

    selected: QueryMode | None = None
    patterns: tuple[re.Pattern[str], ...] = ()
    if generated:
        selected = "generated_only"
        patterns = GENERATED_DIRECTIVES
    elif templates:
        selected = "templates_only"
        patterns = TEMPLATE_DIRECTIVES

    cleaned = prompt
    for pattern in patterns:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    return selected, cleaned or prompt.strip()


def _arguments(
    *,
    prompt: str,
    report_id: int | None,
    order_id: int | None,
    customer_id: int | None,
    organization_node_id: int | None,
    profile_id: int | None,
    environment: str,
    server: str,
    database: str,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "report_id": report_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "organization_node_id": organization_node_id,
        "profile_id": profile_id,
        "environment": environment,
        "server": server,
        "database": database,
    }


def _with_route(
    result: dict[str, Any],
    *,
    target_routing: dict[str, Any],
    requested_mode: QueryMode,
    selected_engine: str,
    mode_source: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    result["routing"] = {
        "target": target_routing,
        "engine": {
            "requested_mode": requested_mode,
            "selected_engine": selected_engine,
            "mode_source": mode_source,
            "fallback_reason": fallback_reason,
            "template_catalog_count": len(INTENTS),
        },
    }
    return result


def prepare_or_generate_query(
    *,
    prompt: str,
    query_mode: QueryMode | None = None,
    report_id: int | None = None,
    order_id: int | None = None,
    customer_id: int | None = None,
    organization_node_id: int | None = None,
    profile_id: int | None = None,
    environment: str = "test",
    server: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """Route one question according to field, prompt directive, or feature flag.

    Precedence:
      1. Explicit ``query_mode`` request field
      2. Natural-language directive in the prompt
      3. ``QUERY_PLANNER_MODE`` environment setting

    In auto mode templates win when they match; generation is the fallback.
    """
    try:
        prompt_mode, cleaned_prompt = detect_prompt_mode(prompt)
    except ValueError as error:
        return {"ok": False, "mode": "routing_error", "error": str(error)}

    if query_mode and prompt_mode and query_mode != prompt_mode:
        return {
            "ok": False,
            "mode": "routing_error",
            "error": (
                f"query_mode={query_mode} conflicts with the prompt directive "
                f"requesting {prompt_mode}."
            ),
        }

    target_result = resolve_target(
        cleaned_prompt,
        environment=environment,
        node=server,
        database=database,
    )
    if not target_result["ok"]:
        return target_result
    target = target_result["target"]
    server = target.node
    database = target.database
    target_routing = target_result["routing"]

    if query_mode:
        selected_mode: QueryMode = query_mode
        source = "request_field"
    elif prompt_mode:
        selected_mode = prompt_mode
        source = "prompt_directive"
    else:
        selected_mode = settings.query_planner_mode
        source = "feature_flag"

    arguments = _arguments(
        prompt=cleaned_prompt,
        report_id=report_id,
        order_id=order_id,
        customer_id=customer_id,
        organization_node_id=organization_node_id,
        profile_id=profile_id,
        environment=environment,
        server=server,
        database=database,
    )
    templates_available = server == "db01" and database == "DB7222"

    if selected_mode == "templates_only":
        if not templates_available:
            return _with_route(
                {
                    "ok": False,
                    "mode": "no_match",
                    "error": f"No reviewed template catalog is enabled for {server}/{database}.",
                },
                target_routing=target_routing,
                requested_mode=selected_mode,
                selected_engine="template",
                mode_source=source,
            )
        template = prepare_query(**arguments)
        if template.get("ok") and template.get("params"):
            template["sql"] = materialize_bound_params(template["sql"], template["params"])
        return _with_route(
            template,
            target_routing=target_routing,
            requested_mode=selected_mode,
            selected_engine="template",
            mode_source=source,
        )

    if selected_mode == "generated_only":
        generated = generate_sql(**arguments)
        if generated.get("ok") and generated.get("params"):
            generated["sql"] = materialize_bound_params(generated["sql"], generated["params"])
        return _with_route(
            generated,
            target_routing=target_routing,
            requested_mode=selected_mode,
            selected_engine="generated",
            mode_source=source,
        )

    template = (
        prepare_query(**arguments)
        if templates_available
        else {
            "ok": False,
            "mode": "no_match",
            "error": f"No reviewed template catalog is enabled for {server}/{database}.",
        }
    )
    if template.get("ok"):
        template["sql"] = materialize_bound_params(template["sql"], template["params"])
        return _with_route(
            template,
            target_routing=target_routing,
            requested_mode="auto",
            selected_engine="template",
            mode_source=source,
        )

    generated = generate_sql(**arguments)
    if generated.get("ok") and generated.get("params"):
        generated["sql"] = materialize_bound_params(generated["sql"], generated["params"])
    return _with_route(
        generated,
        target_routing=target_routing,
        requested_mode="auto",
        selected_engine="generated",
        mode_source=source,
        fallback_reason=template.get("error") or "No template matched.",
    )
