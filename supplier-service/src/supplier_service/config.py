# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated settings for the supplier service, following user-service/config.py;
#        AI-added ENABLE_DOCS and ROOT_PATH (Claude Code, 2026-09-27).
#        AI-replaced JWT_SECRET and JWT_ALGORITHM with the User Service's RS256 public key JWT_PUBLIC_KEY (Claude Code, 2026-11-09),
#        and made it optional like order and credit, so migrations and seeding run without it (2026-11-09).
# Author review: I reviewed the code; the settings match compose.yaml.

from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# supplier-service/ (the folder holding pyproject.toml). In Docker this is /app.
SERVICE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the password in the URL is masked if settings are ever logged
    database_url: SecretStr

    # The User Service's RSA public key (PEM). It verifies access tokens but can't sign them, so it isn't a secret.
    # Only the HTTP API needs it (main.py refuses to start without it); migrations and the seed command don't.
    jwt_public_key: str | None = None

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

    @field_validator("jwt_public_key", mode="before")
    @classmethod
    def _check_public_key(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        # Compose passes an unset variable as an empty string
        if not value.strip():
            return None
        # .env files and secret managers often hold the PEM on one line with literal \n
        pem = value.strip().replace("\\n", "\n")
        try:
            key = load_pem_public_key(pem.encode())
        except ValueError as error:
            raise ValueError("JWT_PUBLIC_KEY is not a PEM public key (see scripts/generate-jwt-keys.sh)") from error
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("JWT_PUBLIC_KEY must be an RSA key of at least 2048 bits")
        return pem

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
