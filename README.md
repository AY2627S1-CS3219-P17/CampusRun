# CS3219 — Software Design and Architecture (AY2627 Sem 1)

## CampusRun

**CampusRun** is a peer-to-peer campus errand platform where
students can request items to be collected from stores or facilities on
campus, and other students can fulfil (and deliver) those requests. The
platform runs on a closed credit economy — credits cannot be bought,
withdrawn, or exchanged for money, and only circulate within the platform.

---

## Running the project

Local service-specific development can be done with a service-level .env file, where environment variables like the local database URL is provided.

The local database can be run using the service-specific database service in the project-level [`compose.yaml`](compose.yaml). For example, to run the user-service database: `docker compose up -d user-db`

To run the entire project locally, use `docker compose up` with [`compose.yaml`](compose.yaml), where the env vars overwrite those in the service-level .env file.

For cloud deployments, separate configuration will be required.

## Team Members

| Name | Role |
| ----- | ----- |
| Nathan Tew | User Service |
| Your Name | Your ownership |
| Your Name | Your ownership |

---

## Repository Structure

This repository follows a **one-service-per-folder** structure: each
microservice (`user-service/`, `supplier-service/`, `order-service/`,
`credit-service/`) lives in its own top-level folder.

```text
.
├── user-service/
├── supplier-service/
├── order-service/
├── credit-service/
├── <n2h-service>/
└── README.md
```

- Any **nice-to-have (N2H)** feature that warrants its own service should
  be added as an **additional folder** at the same level, following the
  same per-service structure.
- Files for agentic coding tools (e.g. agent configs, prompts, skills)
  may be added as needed, but must still **respect the
  one-service-per-folder skeleton** for core implementation.

---

## AI Use Summary

**Tools:** Claude Code (model: Claude Opus 5.5)

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy Core for the user service; a `users` table with an auto-increment integer id; a separate admin table.

**Used for:**
- **Explaining** implementation order (tables → Alembic → FastAPI), Docker Compose networking and service-name DNS, environment variable handling (`pydantic-settings` precedence, root vs. service `.env`), Docker layer caching with uv, and how a Compose setup differs from a Google Cloud Run deployment.
- **Suggesting** separate admin accounts (their own credentials, not a foreign key to `users`), which the team adopted, plus case-insensitive unique indexes on email and username.
- **Suggesting** a local Compose layout (separate `user-db`, `user-migrate` and `user-service` containers). This was an AI suggestion; the AI retracted its initial claim that a separate migration service is "standard practice" after being asked for documentation.
- **Generating** boilerplate for the user service: root `compose.yaml` and `.env.example` entries, `user-service/Dockerfile`, `user-service/.dockerignore`, `user-service/.env.example`, `src/user_service/{config,db,main}.py` (settings, database engine and `GET /health`), and `src/user_service/tables.py` (the `users` and `admins` table definitions, to the team's column spec). The AI also added the `pydantic-settings` dependency to `user-service/pyproject.toml`.

**Verification:** `GET /health` and settings loading were checked in-process against an unreachable database and a missing `DATABASE_URL`. <!-- TODO(author): describe your own review and testing of the AI outputs -->

**Files affected:** each carries an "AI Assistance Disclosure" header comment.

**Prompts and key exchanges:** see [`ai/usage-log.md`](ai/usage-log.md).