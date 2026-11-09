# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated pydantic-settings Settings class reading DATABASE_URL and ENABLE_DOCS; AI-added Pyright ignore on Settings();
#        AI-added INITIAL_ADMIN_EMAIL (Claude Code, 2026-09-28); AI-added RABBITMQ_URL and OUTBOX_POLL_SECONDS (Claude, claude.ai, 2026-10-17);
#        AI-replaced JWT_SECRET with the RS256 private key JWT_PRIVATE_KEY (Claude Code, 2026-11-09).
# Author review: reviewed by Nathan

from functools import lru_cache

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables (e.g. injected by Compose) take priority over .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr so the password in the URL is masked if settings are ever logged
    database_url: SecretStr
    
    # RSA private key (PEM) that signs access tokens. Only this service has it; the others verify with the public
    # key. Optional so Alembic and the create-initial-admin script run without it; main.py refuses to start without it.
    jwt_private_key: SecretStr | None = None
    # Minutes an access token stays valid
    jwt_access_token_ttl: int = 60

    # Only read by the create-initial-admin script; the server runs without them
    initial_admin_email: str | None = None
    initial_admin_username: str | None = None
    initial_admin_password: SecretStr | None = None

    # Off by default so deployed services don't publish their API schema
    enable_docs: bool = False

    # Path prefix the gateway serves this service under, e.g. "/api/users"; empty when accessed directly
    root_path: str = ""

    # This service's RabbitMQ login (user user-service), for the outbox relay. Unset: the relay doesn't run and
    # messages wait in the outbox table, so registration still works without RabbitMQ.
    rabbitmq_url: SecretStr | None = None
    # How often the relay checks the outbox for messages to publish
    outbox_poll_seconds: float = 1.0

    @field_validator("jwt_private_key", mode="before")
    @classmethod
    def _check_private_key(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        # Compose passes an unset variable as an empty string
        if not value.strip():
            return None
        # .env files and secret managers often hold the PEM on one line with literal \n
        pem = value.strip().replace("\\n", "\n")
        try:
            key = load_pem_private_key(pem.encode(), password=None)
        except ValueError as error:
            raise ValueError("JWT_PRIVATE_KEY is not a PEM private key (see scripts/generate-jwt-keys.sh)") from error
        if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("JWT_PRIVATE_KEY must be an RSA key of at least 2048 bits")
        return pem


@lru_cache
def get_settings() -> Settings:
    # Fields are populated from the environment, which Pyright can't see
    return Settings()  # pyright: ignore[reportCallIssue]
