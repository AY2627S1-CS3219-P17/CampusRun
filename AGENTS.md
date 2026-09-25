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

# Required AI Attribution
Every submission using AI must include:
- Source & mode: which tool(s), how it was used (generate/refactor/debug/explain).
- Prompts: the exact prompts + key responses.
- Location(s):
  - place the attribution comment at the top of each AI-influenced file (see below) as a comment,
  - a consolidated disclosure in your project README as the last section. Add a link to the README in the slide deck
  - a usage log file in the project repository

### Example: Short File-Header Attribution (in each affected file)
AI Assistance Disclosure:
Tool: ChatGPT (model: GPT-5.6 Luna Light), date: 2026-08-11
Scope: Generated initial implementation of modules X and Y; suggested test cases for Z.
Author review: I validated correctness, edited for style, and added boundary checks.

### Example: Project-Level Disclosure
(put in README and add link to the README in submission slide deck)
AI Use Summary
Tools: ChatGPT (GPT-5.6 Luna Light), GitHub Copilot
Prohibited phases avoided: requirements elicitation; architecture/design decisions.
Used for:
- Generating boilerplate for Express server and Jest config.
- Getting suggestions for refactoring; for data parsing function; I retained A, rejected B
(explanation below).
- Generating unit tests for edge cases (I added two additional tests). Verification: All AI
outputs reviewed, edited, and tested by the authors. Prompts/Key Exchanges: See
/ai/usage-log.md at the end of this segment.
### Example: Logging
- Maintain a log, /ai/usage-log.md, in the repository with timestamps, prompts, and
usage scenarios.
- Mark any pasted AI code blocks with comments like:
// AI-generated (edited by <name>).
- Add all your SKILLS.md/AGENTS.md to the repository before the final submission.