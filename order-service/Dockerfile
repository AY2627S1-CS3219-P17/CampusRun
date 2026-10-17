# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Containerized the database-free FastAPI order service using the repository's uv pattern.
# Author review: <to be completed by author>

FROM python:3.14.7-slim

# Use the same uv release as the other services.
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Cache dependencies separately from the application code.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Run the API without root privileges.
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000

# Shell form expands PORT on Cloud Run; local Compose uses 8000.
CMD fastapi run src/order_service/main.py --host 0.0.0.0 --port ${PORT:-8000}