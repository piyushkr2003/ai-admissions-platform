\# Task 003 — Authentication \& RBAC



\## 1. Task Overview



Implement the production-grade authentication and authorization foundation for the AI Admissions Platform.



This task establishes secure identity management and role-based access control (RBAC) for platform users and college users.



The implementation must support the multi-tenant architecture defined in:



\- `AGENTS.md`

\- `CLAUDE.md`

\- `docs/product-requirements.md`

\- `docs/architecture.md`

\- `docs/database.md`

\- `docs/api-contract.md`

\- `docs/development.md`

\- `docs/tasks/001-backend-foundation.md`

\- `docs/tasks/002-database-multitenancy.md`



This task is backend-focused.



The objective is to ensure that every protected API operation has a reliable authenticated identity and that users can access only the resources and actions permitted by their role and college tenant.



\---



\# 2. Primary Objective



Build an authentication and authorization layer that provides:



1\. Secure user authentication

2\. Password hashing and verification

3\. Access-token based authentication

4\. Refresh-token/session handling where required by the architecture

5\. Role-based authorization

6\. College/tenant-scoped authorization

7\. Platform-level administrative access

8\. Protected API dependencies/middleware

9\. Consistent authentication errors

10\. Security-focused tests

11\. Cross-tenant access prevention



Authentication must integrate cleanly with the database and API contracts without implementing unrelated business features.



\---



\# 3. Roles



The system must support the roles defined by the product architecture.



At minimum implement:



\## 3.1 Platform Admin



Platform-level administrator.



Can manage or access platform-wide resources where explicitly permitted.



Platform admins are not restricted to a single college tenant when performing platform-level administrative operations.



However, platform-admin access must still be explicit and auditable.



\---



\## 3.2 College Admin



Administrator belonging to a specific college.



Can access administrative functionality for their own college only.



Examples:



\- College configuration

\- Courses

\- Scholarships

\- Admission information

\- Counselors

\- Appointments

\- Leads

\- Applications

\- Knowledge base

\- FAQs

\- Agent configuration

\- Analytics



Access must never cross into another college tenant.



\---



\## 3.3 Counselor / Admissions Staff



College-level operational user.



Can access permitted admissions workflows for their own college.



Examples:



\- Leads

\- Student information relevant to admissions

\- Appointments

\- Applications

\- Conversations

\- Escalations

\- Support tickets



Permissions should follow the RBAC matrix defined in `docs/api-contract.md`.



\---



\## 3.4 Student / Parent / Public User



The architecture must allow prospective students/parents to interact with the admission system.



Do not unnecessarily expose administrative APIs to these users.



Where public or unauthenticated admission interactions are required, they must use explicitly designed public endpoints rather than bypassing authorization.



\---



\# 4. Authentication Architecture



Implement authentication using a secure modern approach compatible with the existing FastAPI architecture.



Recommended baseline:



\- Username/email based authentication

\- Secure password hashing

\- Short-lived access tokens

\- Refresh-token/session mechanism

\- Bearer authentication for protected APIs

\- Token expiry

\- Token validation

\- User status checks



Use established security libraries rather than implementing cryptography manually.



Do not store plaintext passwords.



Do not store passwords in logs.



Do not expose password hashes through API responses.



\---



\# 5. Password Security



Passwords must be stored only as secure password hashes.



Use a modern password hashing algorithm supported by the project's Python security stack.



Recommended:



\- Argon2id where practical

\- bcrypt only where necessary for compatibility



Password requirements should be configurable and validated server-side.



At minimum:



\- Reject empty passwords

\- Enforce reasonable minimum length

\- Avoid accepting obviously invalid credentials

\- Never log passwords

\- Never return password hashes



Password verification must use constant-time-safe library implementations.



\---



\# 6. User Authentication Endpoints



Implement the authentication foundation according to `docs/api-contract.md`.



Expected capabilities include:



\### Register



Create an eligible user account where registration is permitted.



\### Login



Validate credentials and return authentication credentials according to the API contract.



\### Refresh



Issue a new access token/session according to the configured refresh mechanism.



\### Logout



Invalidate the appropriate refresh session/token where supported.



\### Current User



Provide the authenticated user's safe profile and authorization context.



Example conceptual endpoint:



```text

GET /api/v1/auth/me



Do not expose sensitive fields.



7\. Access Tokens



Access tokens must contain only the claims required for authorization and request context.



Potential claims:



user ID

role

college ID where applicable

token/session identifier

issued-at

expiry

issuer/audience where configured



Do not place unnecessary personal information in tokens.



Tokens must have an explicit expiration time.



Expired tokens must be rejected.



Malformed or invalid tokens must be rejected.



8\. Refresh Tokens / Sessions



Implement refresh-token handling in a secure manner consistent with the API contract.



Requirements:



Refresh credentials must expire

Refresh credentials must be revocable

Logout must invalidate the relevant session where applicable

Token rotation should be used where practical

Reuse of revoked/rotated refresh tokens should be detected where supported

Sensitive refresh credentials must not be logged



Store only the minimum necessary information.



If refresh tokens are persisted, store a secure representation rather than unnecessarily storing reusable raw secrets.



9\. Authentication Dependencies



Create reusable FastAPI dependencies for protected routes.



Conceptual dependencies:



get\_current\_user()

require\_authenticated\_user()

require\_role(...)

require\_any\_role(...)

require\_college\_access(...)

require\_platform\_admin(...)



Exact implementation may differ.



The dependencies must provide a consistent mechanism for route authorization.



Do not duplicate authentication logic across individual endpoints.



10\. Tenant Context



Tenant context is critical.



For college-scoped users:



authenticated\_user.college\_id



must determine the tenant they belong to.



A user must not be able to select another college\_id in a request and thereby gain access to another college.



For example, this is NOT sufficient:



GET /api/v1/courses?college\_id=OTHER\_COLLEGE



The authorization layer must verify that the authenticated user is permitted to access that tenant.



Tenant identity must be derived from trusted authenticated context wherever possible.



11\. Cross-Tenant Isolation



Implement and test strict cross-tenant authorization.



Example:



College A Admin

&#x20;       ↓

College A courses      ALLOWED



College A Admin

&#x20;       ↓

College B courses      DENIED



Same principle applies to:



Leads

Appointments

Applications

Conversations

Knowledge sources

Knowledge chunks

Counselors

FAQs

Analytics

Agent configuration

Support tickets

Any other college-owned entity



Authorization must happen server-side.



Never rely on frontend filtering for security.



12\. Platform Admin Authorization



Platform admins may have platform-wide access where explicitly defined.



However:



Platform-admin privileges must be explicit

Role checks must be server-side

Administrative actions must be auditable

Platform admin access must not accidentally grant unrestricted mutation of unrelated resources without an authorization rule



Avoid implementing a generic "god mode" bypass.



13\. College Admin Authorization



College admins must be restricted to their own college.



For example:



College A Admin

&#x20;   college\_id = A



Request:

&#x20;   college\_id = B



Result:

&#x20;   403 Forbidden



Even if the user manually changes URL parameters, request bodies, path IDs, or query parameters, authorization must remain enforced.



14\. Counselor Authorization



Counselors/admissions staff must be restricted to their own college.



Their permissions should be narrower than college administrators where required by the RBAC matrix.



For example:



Allowed:



View assigned/relevant leads

View appointments

Update permitted lead information

Handle admissions conversations

View permitted applications



Not automatically allowed:



Change platform settings

Manage authentication

Modify another college

Change global configuration



Implement only permissions required by the documented API contract.



15\. Public Endpoints



Some admission experiences may intentionally be available without an authenticated administrative account.



Examples could include:



Public college information

Public course information

Public admission information

Public voice session initiation



However, public endpoints must be explicitly marked as public.



Do not make an endpoint public simply because authentication has not yet been implemented.



Public endpoints must still enforce:



Input validation

Rate limiting where applicable

Tenant identification

Authorization for sensitive actions

Abuse prevention

16\. User Status



Authentication must account for user status.



At minimum support a concept equivalent to:



active

inactive

suspended



Inactive/suspended users must not be able to authenticate or use protected APIs.



Do not physically delete users merely to disable access unless the product's data-retention policy explicitly requires it.



17\. Email / Identity Uniqueness



User identity must follow the database constraints defined in docs/database.md.



At minimum:



Normalize email addresses consistently

Enforce uniqueness according to the intended scope

Prevent duplicate active identities

Avoid case-sensitive duplicate-account issues



Do not silently create duplicate users.



18\. Authorization Matrix



Create a centralized authorization model.



Do not scatter hardcoded role checks throughout the application.



Conceptual structure:



Resource / Action

&#x20;       ↓

Permission

&#x20;       ↓

Role

&#x20;       ↓

Tenant Scope



Examples:



courses:read

courses:write



leads:read

leads:write



appointments:read

appointments:write



applications:read

applications:write



knowledge:read

knowledge:write



analytics:read



agent\_config:read

agent\_config:write



Use the permissions defined in the API contract as the source of truth.



Do not invent a large unnecessary permission system.



19\. Authorization Rules



Authorization decisions should consider:



Is the user authenticated?

Is the account active?

What role does the user have?

Is the requested action permitted for that role?

Is the resource college-scoped?

Does the resource belong to the user's college?

Is the operation platform-level?

Is the user allowed to perform that platform-level operation?



Reject unauthorized operations before business logic executes.



20\. HTTP Error Semantics



Use consistent HTTP status codes.



Recommended:



401 Unauthorized



Use when authentication is missing or invalid.



Examples:



Missing bearer token

Expired token

Invalid token

Invalid credentials

403 Forbidden



Use when the identity is valid but the action/resource is not permitted.



Examples:



Counselor attempting an admin-only operation

College A admin attempting College B resource

Suspended authorization context



Do not reveal unnecessary information in authorization errors.



21\. Authentication Error Handling



Login failures should avoid revealing whether an email/account exists where this could enable account enumeration.



Prefer a generic message such as:



Invalid email or password.



Do not return:



Email exists but password is wrong.



or:



No account exists for this email.



unless the product explicitly requires such behavior.



22\. Rate Limiting Considerations



Authentication endpoints are abuse targets.



Prepare the authentication layer for rate limiting on:



Login

Registration

Password reset if implemented

Token refresh

Public session initiation



Do not implement an unnecessarily complex distributed rate-limiting system in this task unless already required by Task 001 infrastructure.



At minimum create clear extension points and configuration.



23\. Password Reset



If password reset infrastructure is included, implement it securely.



Requirements:



Single-use reset tokens

Expiration

No password exposure

No user enumeration

Audit logging

Invalidate appropriate sessions after password change



If email delivery is not yet available, implement the backend contract/service abstraction without inventing a fake email provider.



Do not make password reset a blocker for the rest of the authentication foundation.



24\. Security Headers / Transport



Authentication assumes production HTTPS.



Do not allow production credentials/tokens to be transported over plaintext HTTP.



Production deployment must use HTTPS/TLS.



Avoid putting access tokens into URLs.



Avoid sensitive authentication information in query parameters.



25\. Logging Rules



Never log:



Passwords

Password hashes

Raw access tokens

Raw refresh tokens

Authorization headers

Session secrets



Authentication logs may contain safe metadata such as:



Request ID

User ID

College ID

Event type

Success/failure

Timestamp

IP metadata where permitted by privacy policy



Be cautious with IP and device information.



26\. Audit Events



Authentication/security-sensitive events should be auditable.



At minimum consider:



Login success

Login failure

Logout

Token/session revocation

Password change

Password reset

Account activation/deactivation

Role changes

College assignment changes

Privilege changes



Use the audit model defined in docs/database.md.



Do not create a second incompatible audit-log architecture.



27\. Role Assignment



Role assignment must not be controlled by an untrusted public registration payload.



For example, a user must never be able to submit:



{

&#x20; "email": "attacker@example.com",

&#x20; "role": "platform\_admin"

}



and obtain administrator access.



Administrative role assignment must require appropriate authorization.



College assignment must also be protected.



A college user cannot choose another college during registration and gain access to it.



28\. College User Creation



Where college staff accounts are created by administrators:



Validate the target college

Verify the acting administrator has permission

Assign the correct tenant

Assign only permitted roles

Record the action in audit logs

Prevent privilege escalation



Do not implement a self-service staff-account workflow unless required by the existing API contract.



29\. API Contract Compliance



Authentication endpoints must follow:



docs/api-contract.md



Do not invent incompatible response formats.



Follow the established:



API versioning

Response envelope

Error envelope

Pagination conventions where relevant

Correlation/request IDs

HTTP semantics

Naming conventions



If implementation requires a contract clarification, document it rather than silently changing unrelated contracts.



30\. Database Integration



Use the models and constraints from:



docs/database.md



Do not create duplicate user/role/tenant models.



Use the database's established:



Primary keys

Foreign keys

Indexes

Unique constraints

Status fields

Audit relationships



Database migrations must be created using Alembic.



Never modify production schema manually outside migrations.



31\. Dependency Management



Use established project dependencies where possible.



Do not introduce multiple competing authentication frameworks.



Use maintained, production-grade libraries.



Pin or constrain dependencies according to the repository's dependency-management strategy.



32\. Testing Requirements



Authentication must be thoroughly tested.



32.1 Unit Tests



Test:



Password hashing

Password verification

Token creation

Token validation

Token expiration

Permission checks

Role checks

Tenant checks

User status checks

32.2 Integration Tests



Test:



Register → Login → Authenticated Request

Login → Access Token → Protected Endpoint

Refresh → New Access Token

Logout → Revoked Session/Token



where the implemented contract supports these flows.



33\. Authorization Tests



At minimum test:



Platform Admin

Platform Admin → permitted platform endpoint → ALLOWED

College Admin Same Tenant

College A Admin → College A resource → ALLOWED

College Admin Cross Tenant

College A Admin → College B resource → DENIED

Counselor Same Tenant

College A Counselor → permitted College A resource → ALLOWED

Counselor Privilege Escalation

College A Counselor → admin-only endpoint → DENIED

Unauthenticated

No token → protected endpoint → 401

Invalid Token

Invalid token → protected endpoint → 401

Expired Token

Expired token → protected endpoint → 401

Suspended User

Suspended user → protected endpoint → DENIED

34\. Cross-Tenant Security Test



Create explicit regression tests proving that changing IDs manually cannot bypass tenant authorization.



Test at least:



College A → College B course

College A → College B lead

College A → College B appointment

College A → College B application

College A → College B conversation

College A → College B knowledge source



These tests are mandatory.



35\. Security Regression Tests



Add tests for:



Missing authentication

Invalid JWT

Expired JWT

Wrong role

Wrong college

Suspended user

Privilege escalation

Forged college ID

Forged role

Token leakage prevention

Password hash not returned

Sensitive authentication data not logged

36\. Seed / Development Users



Create deterministic fictional development users only if needed for integration testing.



Example:



Platform Admin

College A Admin

College A Counselor

College B Admin

College B Counselor



Use clearly fictional accounts.



Never add real client credentials.



Never commit real passwords or API keys.



Development credentials must be generated/documented safely and should not be reused in production.



37\. Demo Tenant Compatibility



The authentication implementation must work with the Nova Institute of Technology demo tenant from Task 002.



It must also work with the second fictional tenant used for tenant-isolation tests.



The system must demonstrate:



Nova Institute Admin

&#x20;       ↓

Nova data

&#x20;       ↓

ALLOWED



and:



Nova Institute Admin

&#x20;       ↓

Other fictional college data

&#x20;       ↓

DENIED

38\. API Protection



Once authentication dependencies exist, demonstrate their usage with at least one protected test endpoint.



The endpoint can be a simple internal/test endpoint.



Do not implement the complete business API in this task.



The purpose is to prove:



Request

&#x20; ↓

Authentication

&#x20; ↓

User identity

&#x20; ↓

Role authorization

&#x20; ↓

Tenant authorization

&#x20; ↓

Endpoint

39\. Separation of Concerns



Keep authentication responsibilities separated from business services.



Suggested conceptual structure:



backend/app/

├── core/

│   ├── config.py

│   ├── security.py

│   └── ...

│

├── auth/

│   ├── router.py

│   ├── schemas.py

│   ├── service.py

│   ├── dependencies.py

│   ├── permissions.py

│   └── ...

│

├── models/

├── repositories/

├── services/

└── api/



Adapt to the actual project structure established by Task 001.



Do not create unnecessary duplicate layers.



40\. No Frontend Work



This task is backend-focused.



Do not build:



Login UI

Admin dashboard

Student dashboard

Frontend auth state

Frontend routing



Codex will handle frontend work later.



The backend must expose a clean contract for frontend integration.



41\. No Voice Work



Do not implement:



STT

TTS

WebRTC

LiveKit

Telephony

Voice session orchestration



Those are covered by later tasks.



Authentication should, however, be designed so voice-session APIs can use the same authorization infrastructure.



42\. No AI Agent Work



Do not implement:



LLM agent

RAG

Agent tools

Prompt orchestration

Lead scoring logic

Appointment business logic

Application workflow



Only provide the identity/authorization foundation required by those systems.



43\. Production Security Principles



The implementation must follow these principles:



Never trust client-provided role information.

Never trust client-provided college ownership.

Never expose passwords.

Never log secrets.

Never rely on frontend authorization.

Never bypass tenant checks.

Never use insecure homemade cryptography.

Never grant privileges by default.

Never allow privilege escalation.

Fail closed when authorization cannot be determined.

44\. Definition of Done



Task 003 is complete only when:



&#x20;Authentication architecture is implemented.

&#x20;Secure password hashing is implemented.

&#x20;Login is implemented.

&#x20;Access-token validation is implemented.

&#x20;Refresh/session handling is implemented where required by the API contract.

&#x20;Logout/revocation is implemented where applicable.

&#x20;Current-user endpoint is implemented.

&#x20;Authentication dependencies are reusable.

&#x20;Role-based authorization is implemented.

&#x20;Tenant-scoped authorization is implemented.

&#x20;Platform admin authorization is implemented.

&#x20;College admin authorization is implemented.

&#x20;Counselor authorization is implemented.

&#x20;Public endpoint handling is explicit.

&#x20;User status is enforced.

&#x20;Password hashes are never exposed.

&#x20;Secrets are never logged.

&#x20;Authentication errors follow the API contract.

&#x20;Audit events are implemented where required.

&#x20;Alembic migrations are created if schema changes are required.

&#x20;Unit tests pass.

&#x20;Integration tests pass.

&#x20;Cross-tenant authorization tests pass.

&#x20;Privilege-escalation tests pass.

&#x20;Existing Task 001 tests still pass.

&#x20;Existing Task 002 database/tenant tests still pass.

&#x20;No unrelated product features were implemented.

&#x20;Documentation is updated where implementation differs from the task specification.

45\. Required Agent Report



When complete, the implementing agent must report:



Implemented



List the authentication/RBAC components created.



Endpoints



List authentication endpoints implemented.



Roles



List supported roles and permissions.



Tenant Security



Explain how tenant isolation is enforced.



Security



Describe password/token/security decisions.



Database



List migrations/models changed.



Tests



Report:



Unit tests

Integration tests

Authorization tests

Cross-tenant tests

Total tests passed

Remaining Work



Clearly list anything intentionally deferred.



Risks / Decisions



Mention any important implementation decisions or unresolved issues.



46\. Intended Owner



Primary owner:



Claude Code



Claude should work primarily on the backend authentication/RBAC implementation.



Codex should not modify the same files simultaneously.



If frontend work later requires authentication contracts, Codex should consume the documented API rather than changing backend authentication independently.



47\. Git Workflow



Before implementation:



Read relevant repository instructions and docs.

Inspect the current backend implementation.

Inspect Task 001 and Task 002 results.

Plan the implementation.



During implementation:



Implement incrementally.

Run focused tests.

Fix failures.

Run the full relevant backend test suite.



Before completion:



Review tenant isolation.

Review authorization boundaries.

Review secret handling.

Review API contract compliance.

Review migrations.

Review logs.



Then commit the completed task on the assigned branch.



Suggested commit:



feat(auth): implement authentication and RBAC foundation



Do not commit secrets.



Do not modify unrelated files.



48\. Final Principle



Authentication is not merely a login feature.



For this platform it establishes the security boundary between:



Platform

&#x20;   ↓

College Tenant

&#x20;   ↓

User

&#x20;   ↓

Role

&#x20;   ↓

Permission

&#x20;   ↓

Resource



Every protected request must be evaluated through this chain.



The implementation must fail closed, preserve strict tenant isolation, prevent privilege escalation, and provide a secure foundation for the later admissions agent, RAG, appointment, application, voice, and dashboard systems.

