from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SqlGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)
    environment: Literal["test"] = "test"
    node: Literal["db01", "db02"] | None = None
    server: Literal["db01", "db02"] | None = None
    database: str | None = Field(
        default="DB7222",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_. -]+$",
    )
    query_mode: Literal["auto", "templates_only", "generated_only"] = "auto"
    report_id: int | None = Field(default=None, ge=1)
    order_id: int | None = Field(default=None, ge=1)
    customer_id: int | None = Field(default=None, ge=1)
    organization_node_id: int | None = Field(default=None, ge=1)
    profile_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def consistent_node_hints(self) -> "SqlGenerateRequest":
        if self.node and self.server and self.node != self.server:
            raise ValueError("node and server hints conflict")
        return self

    @property
    def node_hint(self) -> str | None:
        return self.node or self.server
