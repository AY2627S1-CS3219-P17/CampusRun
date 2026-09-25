# Service Overview
The User Service manages user registration, authentication, profile information, and a user’s ability to participate as both a requester and a courier; as well as admin accounts.

It uses FastAPI with SQLAlchemy Core to handle SQL queries with a Postgres 18 database.

uv is the package manager of choice, optionally with mise for python versioning. 

# Getting started
[Install uv](https://docs.astral.sh/uv/getting-started/installation/) first, then run:

> `mise run serve`

If you're not using `mise`, run

> `fastapi dev src/user_service/main.py`

