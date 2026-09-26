# Project Overview
This project is CampusRun, a peer-to-peer campus errand platform localised to the National University of Singapore (NUS). It allows students to request items to be collected from predefined campus suppliers, and for other students fulfill those requests for platform credits.

The project will follow a microservice-based architecture, with the following microservices in their corresponding directories at the project directory: user-service, supplier-service, credit-service and order-service.

All application services and supporting components should be containerized using Docker and built to be deployed to the cloud.

# Glossary
| Term | Definition |
| --- | --- |
| Caller | An unconfirmed identity making an Application Programming Interface (API) request to the system. |
| Session | The authenticated state the system creates when it accepts a user's credentials, represented by a credential (e.g. a token) the client presents with subsequent requests. |
| Errand | A request by a requester for items to be collected from a supplier and delivered to a chosen delivery point, in exchange for a stated reward in credits. |
| Errand state | OPEN (awaiting a courier), ACCEPTED, PICKED_UP, DELIVERED (courier has reported delivery), COMPLETED (requester has confirmed), CANCELLED (by either), EXPIRED. |
| Delivery point | An errand’s destination: either one of the predefined campus delivery locations, or a user-specified map position. |
| Served area | A predefined area around NUS within which will be considered valid campus grounds where errands can take place. |
| Available balance | Credits free to fund a new errand. |
| Reserved balance | Credits committed to errands that have not ended. |
| Protected operation | Every operation except viewing the landing (login) page, registering, authenticating and starting password recovery. |
| Peak load | 10,000 total user accounts, 500 concurrent active users and 2,000 errands per day. |

# Gateway and Service Conventions
- All browser traffic enters through the nginx gateway (`gateway/nginx.conf`, published at `localhost:8080`), which also serves the web app from the `frontend` container at `/`. The frontend calls the API with relative `/api/...` URLs, never a hard-coded host. The gateway is the only container with a public port; services talk to each other on the Compose private network by service name (e.g. `http://user-service:8000`).
- The gateway routes `/api/<service>/...` to each service and strips the prefix. Define routes relative to the service root, and don't repeat the service name as a route prefix (supplier-service uses `/{id}`, not `/suppliers/{id}`).
- Every FastAPI service reads `ROOT_PATH` (the gateway prefix, e.g. `/api/users`) into `FastAPI(root_path=...)`. Any absolute URL a service returns, such as a `Location` header, must start with it. It stays empty when a service runs directly on the host.
- API docs (`/docs`, `/redoc`, `/openapi.json`) are opt-in with `ENABLE_DOCS=true`, which is set only in `compose.yaml` and `.env.example` files. Deployed services leave it unset.
- A new service needs a `location /api/<service>/` block in `gateway/nginx.conf`, `ROOT_PATH` and `ENABLE_DOCS` in `compose.yaml`, and an entry in the gateway's `depends_on`. If it has a route at its root, it also needs an exact-match `location = /api/<service>` block, or requests without the trailing slash get a 404.

# Required AI Attribution
Every submission using AI must include:
- Source & mode: which tool(s), how it was used (generate/refactor/debug/explain).
- Prompts: the exact prompts + key responses.
- Location(s):
  - Place the attribution comment at the top of each AI-influenced file (see below) as a comment.
  - A consolidated disclosure in your project README as the last section. Add new points whenever there is a significantly new AI use.
  - A usage log file in the project repository. Update this upon request, summarising conversations. Don't update it after every prompt.

### Example: Short File-Header Attribution (in each affected file)
```
# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated async SQLAlchemy engine factory and per-request transaction dependency.
# Author review: <to be completed by author>