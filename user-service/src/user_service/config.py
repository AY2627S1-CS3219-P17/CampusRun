# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated pydantic-settings Settings class reading DATABASE_URL and ENABLE_DOCS; AI-added Pyright ignore on Settings().
# Author review: reviewed by Nathan

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the password in the URL is masked if settings are ever logged
    database_url: SecretStr

    # Only read by the create-initial-admin script; the server runs without them
    initial_admin_username: str | None = None
    initial_admin_password: SecretStr | None = None

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
