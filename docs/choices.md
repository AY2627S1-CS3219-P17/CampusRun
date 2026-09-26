# Services

- relational database: generally more suitable as the app expects a consistent and structured schema; no instances of unstructured or document based data
- FastAPI + SQLAlchemy Core: we expect to only use mostly simple queries for this app, so we went with a lighter query-building layer rather than a fully fledged ORM like Django; however, we still wanted the safety and ease of parameterised queries, hence SQLAlchemy Core.