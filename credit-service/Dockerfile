# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: Dockerfile copied from supplier-service/Dockerfile with credit-service paths. One image serves the API,
#        the RabbitMQ worker and the one-off commands; Compose picks which one each container runs.
# Author review: <to be completed by author>

FROM python:3.14.7-slim

# Pinned to match the uv version used to generate uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

WORKDIR /app

# Compile bytecode for faster startup; copy (not hardlink) from the cache mount
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Install dependencies only, so this layer stays cached until the lockfile changes
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install the project itself (also copies alembic.ini and migrations/)
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000

# The HTTP API by default. The worker runs the same image with `credit-worker` (see compose.yaml).
# Shell form so ${PORT} is expanded; Cloud Run injects PORT, locally it defaults to 8000
CMD fastapi run src/credit_service/main.py --host 0.0.0.0 --port ${PORT:-8000}
