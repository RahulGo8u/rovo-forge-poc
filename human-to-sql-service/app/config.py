from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "human-to-sql-service"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    port: int = 10001

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 30.0
    gemini_max_output_tokens: int = 8192

    nl2sql_max_tables: int = 12
    nl2sql_row_limit: int = 200
    query_planner_mode: Literal[
        "auto", "templates_only", "generated_only"
    ] = "auto"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
