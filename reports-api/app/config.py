from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "reports-api"
    app_version: str = "0.3.0"
    api_prefix: str = "/api/v1"
    port: int = 10000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
