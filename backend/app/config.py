from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent.parent


class Settings(BaseSettings):
    app_name: str = "PPTKiller API"
    app_env: str = "development"
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite:///./backend/data/pptkiller.db"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "disabled"
    serpapi_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TAVILY_API_KEY", "TAVILY_KEY"),
    )
    semantic_scholar_api_key: Optional[str] = None
    unsplash_access_key: Optional[str] = None
    unsplash_secret_key: Optional[str] = None
    pexels_api_key: Optional[str] = None
    redis_url: Optional[str] = None
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", APP_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_directories(self) -> None:
        Path("backend/data").mkdir(parents=True, exist_ok=True)
        Path("backend/generated").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
