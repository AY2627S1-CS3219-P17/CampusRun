# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated settings for the supplier service, following user-service/config.py;
#        AI-added ENABLE_DOCS and ROOT_PATH (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# supplier-service/ (the folder holding pyproject.toml). In Docker this is /app.
SERVICE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the password in the URL is masked if settings are ever logged
    database_url: SecretStr

    # Shared with the User Service, which signs the access tokens. At least
    # 32 characters: shorter HS256 keys can be guessed.
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    seed_dir: Path = SERVICE_ROOT / "seed"

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False

    # Path prefix the gateway serves this service under, e.g. "/api/suppliers"; empty when accessed directly
    root_path: str = ""

    # Comma-separated browser origins allowed to call this service directly,
    # e.g. "http://localhost:5173". Empty: no cross-origin access.
    cors_origins: str = ""

    # The "served area" from the glossary: a box around the NUS Kent Ridge campus
    served_area_min_lat: float = 1.2870
    served_area_max_lat: float = 1.3100
    served_area_min_lng: float = 103.7640
    served_area_max_lng: float = 103.7880

    # Supplier opening hours are local campus times
    timezone: str = "Asia/Singapore"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
