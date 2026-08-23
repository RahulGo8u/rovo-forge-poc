from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import HTTPException, Path, Query

LookupKind = Literal["auto", "ReportID", "OrderID", "CustomerID", "OrgNodeID", "ProfileID"]
CatalogName = Literal["delivery-methods", "file-types", "email-types", "workflow-states"]
LOOKUP_KINDS = ("auto", "ReportID", "OrderID", "CustomerID", "OrgNodeID", "ProfileID")
JIRA_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]+-\d+$")
NUMERIC_ID = re.compile(r"^\d+$")

PositiveId = Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807, description="Positive integer identifier")]
LimitQuery = Annotated[int, Query(ge=1, le=50)]
TimelineLimitQuery = Annotated[int, Query(ge=1, le=100)]
SampleLimitQuery = Annotated[int, Query(ge=1, le=50)]


def parse_identifier(value: str) -> int:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="Identifier is required.")
    if JIRA_KEY.fullmatch(raw):
        raise HTTPException(
            status_code=422,
            detail="Jira keys are not supported. Use a numeric ReportID, OrderID, CustomerID, OrgNodeID, or ProfileID.",
        )
    if not NUMERIC_ID.fullmatch(raw):
        raise HTTPException(
            status_code=422,
            detail="Identifier must be a positive whole number.",
        )
    number = int(raw)
    if number < 1:
        raise HTTPException(status_code=422, detail="Identifier must be a positive whole number.")
    return number
