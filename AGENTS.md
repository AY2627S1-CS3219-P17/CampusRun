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