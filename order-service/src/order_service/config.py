# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Loaded shared JWT, Groq, supplier, and FastAPI gateway settings.
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-added DATABASE_URL, RABBITMQ_URL, the JWT algorithm and log level, following credit-service/config.py;
#        made JWT_SECRET optional so the worker can run without it (main.py still requires it).
# Author review: <to be completed by author>

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the passwords in these URLs are masked if settings are ever logged
    database_url: SecretStr
    # This service's RabbitMQ login (user order-service). Only the worker connects; the HTTP API never does.
    rabbitmq_url: SecretStr | None = None

    # Shared with the User Service, which signs the access tokens. At least 32 characters. Only the HTTP API
    # needs it (main.py refuses to start without it); the worker never sees it.
    jwt_secret: SecretStr | None = Field(default=None, min_length=32)
    jwt_algorithm: str = "HS256"

    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    supplier_service_url: str = "http://supplier-service:8000"

    log_level: str = "INFO"

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False

    # Path prefix the gateway serves this service under, e.g. "/api/orders"; empty when accessed directly
    root_path: str = ""


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
