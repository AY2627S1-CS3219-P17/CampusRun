# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated settings for the credit service, following supplier-service/config.py.
# Author review: <to be completed by author>

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the passwords in these URLs are masked if settings are ever logged
    database_url: SecretStr
    # Only the worker and the demo connect to RabbitMQ; the HTTP API never does
    rabbitmq_url: SecretStr | None = None

    # Shared with the User Service, which signs the access tokens. At least 32 characters. Only the HTTP API
    # needs it (main.py refuses to start without it); the worker never sees it.
    jwt_secret: SecretStr | None = Field(default=None, min_length=32)
    jwt_algorithm: str = "HS256"

    # Credits every new wallet starts with (F1.1.7, F12.1.1). The credit service owns this policy:
    # the User Service only asks for a wallet. A change applies to wallets opened afterwards.
    initial_credits: int = Field(default=100, ge=1)

    # Messages the worker takes from RabbitMQ before acknowledging earlier ones. It still applies them one at a time.
    worker_prefetch: int = Field(default=10, ge=1)

    # A reservation still HELD after this long is reported by the audit: an errand can wait at most 24 hours to be
    # accepted, so a hold this old probably missed its transfer or release message.
    stale_hold_hours: int = Field(default=48, ge=1)

    log_level: str = "INFO"

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False

    # Path prefix the gateway serves this service under, e.g. "/api/credits"; empty when accessed directly
    root_path: str = ""


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
