"""Resolve a natural-language question to a registered SQL catalog target."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .catalog import list_catalog_databases, load_semantic_model


@dataclass(frozen=True)
class Target:
    node: str
    database: str
    domain: str
    terms: tuple[str, ...]


TARGETS = (
    Target(
        "db01",
        "DB7222",
        "reports-orders-delivery",
        (
            "report", "reports", "order", "orders", "delivery", "deliverable",
            "status", "substatus", "product", "customer", "profile", "address",
            "measurement", "dxf", "email",
        ),
    ),
    Target(
        "db02",
        "Operations",
        "operations-workflow",
        (
            "operation", "operations", "workflow", "task", "tasks", "queue",
            "queued", "worker", "task state",
        ),
    ),
)
TOKEN = re.compile(r"[a-z0-9]+")


def _registered(environment: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (item["node"].casefold(), item["database"].casefold()): item
        for item in list_catalog_databases(environment)
        if item["query_enabled"]
        and any(
            target.node == item["node"]
            and target.database.casefold() == item["database"].casefold()
            for target in TARGETS
        )
    }


def _semantic_terms(target: Target) -> set[str]:
    terms = set(target.terms)
    model = load_semantic_model(target.node, target.database)
    for term, details in (model.get("business_terms") or {}).items():
        terms.update(TOKEN.findall(str(term).casefold()))
        for synonym in details.get("synonyms") or []:
            terms.update(TOKEN.findall(str(synonym).casefold()))
    return terms


def resolve_target(
    prompt: str,
    *,
    environment: str = "test",
    node: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    registered = _registered(environment)

    if node and database:
        key = (node.casefold(), database.casefold())
        if key not in registered:
            return {
                "ok": False,
                "mode": "routing_error",
                "error": (
                    f"Conflicting or unregistered target hints: {node}/{database}. "
                    "Registered targets are db01/DB7222 and db02/Operations."
                ),
                "routing": {"source": "explicit_hints", "confidence": 0.0},
            }

    candidates = list(TARGETS)
    if node:
        candidates = [target for target in candidates if target.node.casefold() == node.casefold()]
    if database:
        candidates = [
            target
            for target in candidates
            if target.database.casefold() == database.casefold()
        ]
    candidates = [
        target
        for target in candidates
        if (target.node.casefold(), target.database.casefold()) in registered
    ]
    if not candidates:
        return {
            "ok": False,
            "mode": "routing_error",
            "error": "The supplied node or database hint does not identify a registered target.",
            "routing": {"source": "explicit_hint", "confidence": 0.0},
        }

    explicit = bool(node or database)
    if explicit and len(candidates) == 1:
        target = candidates[0]
        scores = {f"{target.node}/{target.database}": 1.0}
        confidence = 1.0
        evidence = ["registered explicit hint"]
    else:
        prompt_tokens = set(TOKEN.findall(prompt.casefold()))
        scored: list[tuple[int, Target, list[str]]] = []
        for target in candidates:
            matched = sorted(prompt_tokens & _semantic_terms(target))
            phrase_matches = [
                term for term in target.terms if " " in term and term in prompt.casefold()
            ]
            score = len(matched) + 2 * len(phrase_matches)
            scored.append((score, target, matched + phrase_matches))
        scored.sort(key=lambda item: (-item[0], item[1].node, item[1].database))
        scores = {
            f"{target.node}/{target.database}": float(score)
            for score, target, _ in scored
        }
        best_score, target, evidence = scored[0]
        tied = [item for item in scored if item[0] == best_score]
        if best_score == 0 or len(tied) > 1:
            return {
                "ok": False,
                "mode": "routing_error",
                "error": "Target routing is ambiguous; supply a registered node or database hint.",
                "routing": {
                    "source": "semantic_scoring",
                    "confidence": 0.0,
                    "scores": scores,
                },
            }
        runner_up = scored[1][0] if len(scored) > 1 else 0
        confidence = round(min(0.99, 0.6 + 0.1 * (best_score - runner_up)), 2)

    metadata = registered[(target.node.casefold(), target.database.casefold())]
    routing = {
        "source": "explicit_hint" if explicit else "semantic_scoring",
        "node": target.node,
        "database": target.database,
        "domain": target.domain,
        "confidence": confidence,
        "evidence": evidence,
        "scores": scores,
        "compiled": metadata["compiled"] or (
            target.node == "db01" and target.database == "DB7222"
        ),
    }
    if not routing["compiled"]:
        return {
            "ok": False,
            "mode": "catalog_unavailable",
            "error": f"No compiled catalog pack for {environment}/{target.node}/{target.database}",
            "routing": routing,
        }
    return {"ok": True, "target": target, "routing": routing}
