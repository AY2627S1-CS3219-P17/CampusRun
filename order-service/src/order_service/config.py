# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Loaded shared JWT, Groq, supplier, and FastAPI gateway settings.
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-added DATABASE_URL, RABBITMQ_URL, the JWT algorithm and log level, following credit-service/config.py;
#        made JWT_SECRET optional so the worker can run without it (main.py still requires it);
#        AI-added the served-area bounds and seed directory for delivery locations (copied from supplier-service),
#        and the user and credit service URLs, the expiry grace period and campus time zone (2026-10-19).
# Author review: <to be completed by author>

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# order-service/, so the seed files are found wherever the service is started from
SERVICE_ROOT = Path(__file__).resolve().parents[2]


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
    # Other services, reached on the Compose private network. Calls are made as the signed-in user (their token).
    supplier_service_url: str = "http://supplier-service:8000"
    user_service_url: str = "http://user-service:8000"
    credit_api_url: str = "http://credit-service:8000"
    # Seconds to wait for another service before treating it as unavailable
    service_timeout_seconds: float = 5.0

    # The "served area" from the glossary: a box around the NUS Kent Ridge campus (same as supplier-service)
    served_area_min_lat: float = 1.2870
    served_area_max_lat: float = 1.3100
    served_area_min_lng: float = 103.7640
    served_area_max_lng: float = 103.7880

    # Errands: deliver_by is a soft deadline; an unfinished errand expires this long after it (D2)
    expiry_grace_minutes: int = Field(default=5, ge=0)
    # Local campus time, used for deliverBy values sent without a time zone
    timezone: str = "Asia/Singapore"

    # The predefined delivery locations loaded by `python -m order_service.seed`
    seed_dir: Path = SERVICE_ROOT / "seed"

    log_level: str = "INFO"

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False

    # Path prefix the gateway serves this service under, e.g. "/api/orders"; empty when accessed directly
    root_path: str = ""


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
