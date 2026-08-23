from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ApiResponse(BaseModel):
    ok: bool = True
    source: Literal["seed"] = "seed"
    row_count: int = 0
    data: Any = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TriageVerdict(BaseModel):
    level: Literal["issue", "attention", "healthy", "info"]
    summary: str
    confidence: int = Field(ge=0, le=100)


class QuickInvestigateRequest(BaseModel):
    lookup: str = Field(..., min_length=1, max_length=32, examples=["44840403", "99100234"])
    lookup_kind: Literal["auto", "ReportID", "OrderID", "CustomerID", "OrgNodeID", "ProfileID"] = "auto"

    @field_validator("lookup")
    @classmethod
    def lookup_must_be_numeric_id(cls, value: str) -> str:
        from .validation import JIRA_KEY, NUMERIC_ID

        raw = value.strip()
        if JIRA_KEY.fullmatch(raw):
            raise ValueError(
                "Jira keys are not supported. Use a numeric ReportID, OrderID, CustomerID, OrgNodeID, or ProfileID."
            )
        if not NUMERIC_ID.fullmatch(raw) or int(raw) < 1:
            raise ValueError("Identifier must be a positive whole number.")
        return raw


class QuickInvestigateResponse(BaseModel):
    ok: bool = True
    source: Literal["seed"] = "seed"
    report_id: int | None = None
    lookup: str | None = None
    lookup_kind: str | None = None
    verdict: TriageVerdict
    report: dict[str, Any] | None = None
    delivery_rules: list[dict[str, Any]] = Field(default_factory=list)
    products: list[dict[str, Any]] = Field(default_factory=list)
    email_availability: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
