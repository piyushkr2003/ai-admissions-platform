\# Task 004 — College Configuration \& Onboarding



\## 1. Task Overview



Implement the backend foundation for creating, configuring, validating, publishing, and managing colleges on the AI Admissions Platform.



The platform is a reusable multi-tenant product.



The same application must support:



```text

College A

College B

College C

...



without requiring application-code changes for each college.



College-specific behavior must come from configuration and college-owned data.



This task establishes the configuration layer that later powers:



AI admissions agent

RAG/knowledge base

Courses

Eligibility

Fees

Scholarships

Admission dates

Required documents

Counselors

Appointments

FAQs

Agent personality

Supported languages

College branding

Admissions workflows



The implementation must follow:



AGENTS.md

CLAUDE.md

docs/product-requirements.md

docs/architecture.md

docs/database.md

docs/api-contract.md

docs/development.md

docs/tasks/001-backend-foundation.md

docs/tasks/002-database-multitenancy.md

docs/tasks/003-auth-rbac.md



This task is primarily backend-focused.



2\. Primary Objective



Create a clean college configuration system that allows an authorized platform/college administrator to manage college-specific settings without changing application code.



The system must support:



College identity

Branding

Contact information

Supported languages

Admission configuration

Agent configuration references

College status

College lifecycle

Configuration validation

Tenant-safe access

Configuration versioning where required

Publishing/activation

Auditability

API contracts

Tests

3\. Core Principle



The platform must separate:



PLATFORM LOGIC

&#x20;       +

COLLEGE CONFIGURATION

&#x20;       +

COLLEGE DATA



Platform logic should remain reusable.



For example:



Agent code:

&#x20;   "Check eligibility using configured rules."



College A:

&#x20;   B.Tech CSE requires 60% PCM



College B:

&#x20;   B.Tech CSE requires 55% PCM



The agent implementation does not change.



Only the college data/configuration changes.



4\. College Lifecycle



A college should have an explicit lifecycle.



Recommended states:



draft

active

suspended

archived



Meaning:



draft



College is being configured.



It may not be publicly available.



active



College is fully configured and available for supported platform functionality.



suspended



College temporarily cannot be used for normal public interactions.



archived



College is no longer actively used but historical data may remain available according to retention rules.



5\. College Identity



Support configuration for:



College name

Short name

Slug

Description

Legal/official name where required

Website

Primary contact email

Contact phone

Address

City

State

Country

Postal code

Time zone

Admission contact information



Use structured fields rather than putting everything into an unstructured text blob.



6\. College Slug



Each college should have a stable unique slug suitable for URLs and tenant identification where required.



Example:



nova-institute-of-technology



Requirements:



Normalized

URL-safe

Unique

Stable

Cannot silently collide with another college

Changes should be controlled because external references may depend on it



Do not use college display name as the primary tenant identifier.



7\. College Tenant ID



The college primary identifier established by the database design must remain the authoritative tenant identifier.



Do not use:



College name

Slug

User-provided arbitrary IDs



as the primary tenant security boundary.



The authenticated user's tenant context and database relationships must use the established college ID.



8\. Branding Configuration



Support college-specific branding such as:



Logo URL/reference

Favicon/reference where required

Primary branding information

Secondary branding information

Website URL

Contact details



Do not store large binary images directly in PostgreSQL unless the architecture explicitly requires it.



Use object/file storage abstractions where appropriate.



Do not hardcode Nova Institute branding into application code.



9\. Supported Languages



College configuration should define the languages supported by the AI agent.



Initial supported language values:



en

hi

hinglish



Architecture should allow future additions such as regional Indian languages.



Example:



{

&#x20; "languages": \[

&#x20;   "en",

&#x20;   "hi",

&#x20;   "hinglish"

&#x20; ]

}



The configuration should not automatically imply that a language is operationally available unless the voice/AI providers support it.



10\. Default Language



Each college may configure a default language.



Example:



default\_language = en



Requirements:



Default language must be one of the configured supported languages.

A college cannot configure a default language that is disabled.

Validation must happen server-side.

11\. Time Zone



Each college must have a configured time zone.



This is important for:



Appointment availability

Admission deadlines

Date/time communication

Analytics

Scheduled tasks

Voice interactions



Do not assume UTC or the server's local time when interpreting college-specific dates.



Store timestamps in a consistent canonical format while preserving the college's configured time zone for presentation and scheduling.



12\. Admission Configuration



Support college-specific admission settings such as:



Admission season

Admission status

Application availability

Application deadline

Admission contact

General admission instructions

Whether applications are currently open



Do not duplicate detailed course eligibility or fee structures inside a generic college settings JSON field when structured tables already exist.



Use the structured entities defined in docs/database.md.



13\. College Data vs Configuration



Use the appropriate storage model.



Structured relational data



Use database entities for:



Courses

Eligibility rules

Fees

Scholarships

Admission dates

Required documents

Counselors

Availability

Leads

Applications

Configuration



Use configuration for:



Branding

Supported languages

Agent defaults

College contact details

Feature flags

General admission settings

Knowledge base



Use RAG for:



Prospectus

Policies

Detailed admission guides

FAQ documents

Website content

Brochures

Long-form institutional information



Do not put the entire college knowledge base into a giant configuration JSON object.



14\. Feature Flags



Allow controlled college-level feature configuration where required.



Potential examples:



voice\_enabled

phone\_enabled

appointment\_booking\_enabled

application\_assistance\_enabled

knowledge\_search\_enabled



Feature flags must have safe defaults.



Do not use feature flags as a substitute for authorization.



A disabled feature should not bypass permissions.



15\. Agent Configuration Reference



The college configuration system should provide a relationship to the college's agent configuration.



Agent configuration will later control:



Agent name

Greeting

Tone

Personality

Language behavior

Response style

Escalation settings

Voice settings

Allowed capabilities



Do not implement the full AI agent in this task.



Do not duplicate agent orchestration logic here.



The configuration layer should provide a clean association to the agent configuration defined by the architecture.



16\. Configuration Validation



College configuration must be validated before activation.



At minimum validate:



Required identity fields

Valid slug

Valid email formats

Valid phone format where applicable

Valid website URL

Valid country/state information

Valid time zone

Supported language values

Default language is supported

Feature flag types

Valid lifecycle state transitions

Required admission configuration

Required contact information



Do not allow an invalid college to become active.



17\. Draft Configuration



A newly created college should normally begin as:



draft



Administrators should be able to progressively configure:



Identity

↓

Branding

↓

Languages

↓

Admissions

↓

Courses

↓

Fees

↓

Eligibility

↓

Scholarships

↓

Documents

↓

Counselors

↓

Knowledge

↓

Agent

↓

Validation

↓

Publish



Do not require every future feature to be completed in this task.



The onboarding system should be designed so later tasks can plug into this lifecycle.



18\. Configuration Completeness



Provide a way to determine whether a college is sufficiently configured for activation.



Conceptually:



configuration\_status



may expose categories such as:



identity: complete

branding: complete

languages: complete

admissions: complete

courses: complete

knowledge: incomplete

agent: incomplete



Do not use a simplistic percentage alone as the source of truth.



Validation should identify actual missing requirements.



19\. Publish / Activate



Implement a controlled activation/publish operation.



Conceptually:



POST /api/v1/colleges/{college\_id}/publish



The exact endpoint must follow docs/api-contract.md.



Publishing should:



Authenticate the user

Authorize the action

Validate the college

Verify required configuration

Prevent activation if required configuration is invalid

Update the lifecycle state

Record an audit event

Return the resulting state



Do not allow the frontend to directly set:



status = active



without backend validation.



20\. Suspend College



Authorized platform administrators should be able to suspend a college.



Suspension should:



Prevent appropriate public interactions

Preserve historical records

Preserve configuration

Preserve leads/applications according to policy

Record an audit event



Do not delete tenant data when suspending.



21\. Archive College



Archiving should preserve historical data subject to the platform retention policy.



Archived colleges should not behave as active tenants.



Do not physically delete historical data simply because a college is archived.



Deletion/retention workflows are outside this task unless already explicitly defined by the database policy.



22\. Lifecycle State Transitions



Define allowed transitions.



Example:



draft → active

draft → archived



active → suspended

active → archived



suspended → active

suspended → archived



Invalid transitions must be rejected.



For example:



archived → active



should not happen accidentally.



If reactivation of archived tenants is required later, it should be an explicit administrative workflow.



23\. College CRUD APIs



Implement the college management APIs required by the API contract.



Expected capabilities include:



Create college

Get college

Update college

List colleges

Get configuration

Update configuration

Validate configuration

Publish/activate

Suspend

Archive



Exact routes, request schemas, response schemas, and permissions must follow:



docs/api-contract.md



Do not invent conflicting routes.



24\. Tenant Authorization



College configuration APIs are highly sensitive.



Rules:



Platform Admin



May create/manage colleges where permitted.



College Admin



May manage configuration for their own college.



Counselor



Should not automatically receive college configuration write access.



Cross-Tenant



Must always be denied.



Example:



College A Admin

&#x20;       ↓

Update College B configuration

&#x20;       ↓

403 Forbidden



Never trust a client-provided college ID without authorization.



25\. Platform Admin College Creation



Platform administrators may create a new college.



The creation process must:



Validate input

Create tenant

Create default configuration

Initialize lifecycle as draft

Create required default records where defined

Create audit event

Return the new college



Do not automatically activate a newly created college unless the configuration validation passes.



26\. College Admin Onboarding



Once a college exists, an authorized college administrator should be able to configure its own tenant.



The API should support incremental updates.



Example:



PATCH college identity

PATCH branding

PATCH language configuration

PATCH admission configuration



Use the established API conventions.



Avoid one enormous endpoint that accepts every possible college setting.



27\. Partial Updates



Configuration updates should support safe partial updates where appropriate.



Requirements:



Validate incoming fields

Preserve unspecified fields

Reject invalid values

Enforce tenant authorization

Record changes where appropriate



Do not accidentally overwrite unrelated configuration.



28\. Optimistic Concurrency



Where multiple administrators may edit configuration, consider optimistic concurrency controls.



At minimum avoid silently overwriting a newer configuration with stale data.



Possible mechanisms include:



Updated timestamp checks

Version number

ETag/If-Match



Use the simplest reliable mechanism compatible with the API architecture.



29\. Configuration Versioning



College configuration may evolve over time.



Where versioning is required by the database architecture:



Version 1

Version 2

Version 3



must be distinguishable.



Historical audit information should allow administrators to determine what changed.



Do not create a complicated version-control system unless required.



30\. Auditability



Record important configuration actions.



At minimum:



College created

College updated

Configuration changed

College published

College suspended

College archived

College reactivated

Feature enabled/disabled

Supported languages changed

Agent configuration association changed



Audit entries should include safe metadata such as:



Acting user

College

Action

Timestamp

Request/correlation ID

Relevant resource identifier



Do not store secrets in audit records.



31\. Configuration Change Safety



Sensitive configuration changes should be validated before persistence where practical.



For example:



default\_language = "fr"

supported\_languages = \["en", "hi"]



must be rejected.



Likewise:



time\_zone = "invalid"



must be rejected.



Fail validation clearly rather than silently fixing user input.



32\. API Response Design



College endpoints must return safe, structured data.



Example conceptual response:



{

&#x20; "id": "college-id",

&#x20; "name": "Nova Institute of Technology",

&#x20; "slug": "nova-institute-of-technology",

&#x20; "status": "active",

&#x20; "timezone": "Asia/Kolkata",

&#x20; "supported\_languages": \[

&#x20;   "en",

&#x20;   "hi",

&#x20;   "hinglish"

&#x20; ],

&#x20; "configuration\_status": {

&#x20;   "identity": "complete",

&#x20;   "branding": "complete",

&#x20;   "languages": "complete",

&#x20;   "admissions": "complete"

&#x20; }

}



Exact response format must follow the API contract.



Do not expose internal database implementation details unnecessarily.



33\. Public College Configuration



Public APIs should expose only information intended for prospective students/parents.



Do not expose:



Internal admin configuration

Audit logs

Internal user IDs

Security settings

Private counselor data

Internal feature-management details

Secrets

Internal database identifiers unless explicitly safe



Create a deliberate public representation rather than returning the full admin configuration object.



34\. College Configuration for the AI Agent



Later, the AI agent must be able to obtain a reliable college context.



The configuration service should provide a normalized representation containing information such as:



college identity

supported languages

timezone

admission status

feature availability

agent configuration reference

contact information



The AI agent must not need to query arbitrary database tables directly.



Provide a service/API abstraction for retrieving validated college configuration.



35\. College Context Object



Create a reusable backend representation conceptually similar to:



CollegeContext



It may contain:



college\_id

name

timezone

supported\_languages

default\_language

admission\_status

feature\_flags

agent\_config\_id

contact information



This object will later be consumed by:



Agent

RAG

Voice

Appointment system

Application system

Analytics



Keep it focused and avoid loading the entire college database into memory.



36\. Configuration Caching



If configuration is read frequently by the AI agent, it may later benefit from caching.



Do not introduce Redis or a distributed caching architecture unless needed at this stage.



Create clean service boundaries so caching can be added later without changing callers.



Correctness and tenant isolation are more important than premature optimization.



37\. Default Configuration



When a college is created, initialize safe defaults.



Examples:



status = draft

default\_language = en

supported\_languages = \[en]

voice\_enabled = false

phone\_enabled = false

appointment\_booking\_enabled = false

application\_assistance\_enabled = false



Defaults must be safe.



Do not activate capabilities automatically unless validation and required dependencies exist.



38\. Demo College



Use the fictional:



Nova Institute of Technology



as the primary demo tenant.



It should remain clearly fictional.



The configuration should support the previously defined demo programs:



B.Tech CSE

B.Tech AI \& ML

BCA

MBA

MCA



Course-specific information belongs in the course entities, not hardcoded into college configuration.



39\. Second Tenant



Maintain compatibility with the second fictional tenant introduced in Task 002.



Use it to prove:



Tenant A configuration

≠

Tenant B configuration



and:



Tenant A Admin

&#x20;   ↓

Tenant B configuration

&#x20;   ↓

DENIED

40\. Onboarding Readiness



The backend should expose enough information for a future onboarding UI to show:



College Setup



✓ Basic Information

✓ Branding

✓ Languages

✓ Admissions

✓ Courses

✓ Eligibility

✓ Fees

✓ Scholarships

✓ Documents

○ Knowledge Base

○ Agent Configuration

○ Counselor Availability



\[Validate]

\[Publish]



The UI itself is outside this task.



41\. No Hardcoded College Logic



Do not write code such as:



if college.name == "Nova Institute of Technology":

&#x20;   ...



or:



if college\_id == "nova":

&#x20;   ...



College-specific behavior must come from persisted configuration/data.



The Nova tenant is test/seed data, not a special code path.



42\. Security



Follow the security principles from:



docs/development.md

docs/tasks/003-auth-rbac.md



Requirements:



Authentication required for admin APIs

RBAC required

Tenant isolation

Input validation

No mass-assignment vulnerabilities

No arbitrary role assignment

No arbitrary tenant assignment

Safe error messages

Audit important mutations

No secrets in configuration

No secrets in logs



Never allow a request body to override server-derived tenant ownership.



43\. Mass Assignment Protection



Do not blindly deserialize every request field directly into a database model.



For example, an update request must not allow users to submit:



{

&#x20; "id": "other-college",

&#x20; "status": "active",

&#x20; "created\_at": "...",

&#x20; "owner\_id": "..."

}



and mutate protected fields.



Use explicit request schemas.



44\. Validation Service



Create a reusable college configuration validation service.



Conceptually:



validate\_college\_configuration(college\_id)



It should return structured validation results.



Example:



valid: false



errors:

\- default language is not supported

\- primary contact email missing

\- no active course configured



The exact validation rules can grow as later tasks add dependencies.



Avoid duplicating validation logic across multiple endpoints.



45\. Future Extensibility



The configuration system must allow future colleges to have differences such as:



College A:

English + Hindi



College B:

English + Hindi + Kannada



College C:

English only



or:



College A:

Appointment booking enabled



College B:

Appointment booking disabled



or:



College A:

Application assistance enabled



College B:

Application assistance disabled



without changing the agent source code.



46\. Testing Requirements

46.1 Unit Tests



Test:



Slug normalization

Email validation

Language validation

Default language validation

Time zone validation

Feature flag validation

Lifecycle transition validation

Configuration completeness

Publish validation

46.2 Integration Tests



Test:



Create college

&#x20;   ↓

Configure college

&#x20;   ↓

Validate

&#x20;   ↓

Publish

&#x20;   ↓

Active



Also test:



Create college

&#x20;   ↓

Incomplete configuration

&#x20;   ↓

Publish

&#x20;   ↓

Rejected

47\. Tenant Isolation Tests



Test:



College A Admin → College A configuration → ALLOWED

College A Admin → College B configuration → DENIED



Test this for:



GET

PATCH

Publish

Suspend

Archive



where applicable.



Also test that changing the college\_id in:



URL

request body

query parameters



cannot bypass authorization.



48\. Lifecycle Tests



Test valid transitions:



draft → active

active → suspended

suspended → active

active → archived

suspended → archived



Test invalid transitions such as:



archived → active



unless explicitly supported by the final implementation.



49\. Configuration Safety Tests



Test:



Unsupported language

Invalid default language

Invalid timezone

Duplicate slug

Missing required field

Invalid lifecycle transition

Unauthorized publish

Unauthorized configuration update

Cross-tenant configuration access

50\. Existing Test Compatibility



All tests from:



Task 001

Task 002

Task 003



must continue to pass.



Do not break:



Database migrations

Tenant isolation

Authentication

RBAC

Health endpoints

51\. No Frontend Work



Do not implement:



Onboarding dashboard UI

College settings UI

Admin navigation

React components



Codex will consume the backend API later.



52\. No RAG Work



Do not implement:



Document parsing

Embeddings

Vector search

Retrieval

Knowledge ingestion



Those belong to the dedicated RAG task.



This task only establishes the college/configuration foundation that RAG will use.



53\. No Agent Work



Do not implement:



LLM prompts

Agent orchestration

Tool calling

Voice conversations

Lead scoring

Appointment booking

Application workflows



Only expose the configuration services those components will later consume.



54\. No Voice Work



Do not implement:



STT

TTS

WebRTC

LiveKit

Telephony

Voice session management



Voice will consume college configuration later.



55\. Suggested Backend Structure



Adapt to the structure created by Task 001.



Conceptually:



backend/app/

├── colleges/

│   ├── router.py

│   ├── schemas.py

│   ├── service.py

│   ├── repository.py

│   ├── validators.py

│   └── ...

│

├── auth/

├── models/

├── services/

├── repositories/

└── core/



Do not create unnecessary abstraction layers.



56\. API Documentation



Update API documentation if implementation details require clarification.



The source of truth remains:



docs/api-contract.md



Any meaningful deviation must be documented.



Do not silently alter the contract.



57\. Migration Requirements



If Task 004 requires schema changes:



Create Alembic migrations

Keep migrations deterministic

Preserve existing data

Add appropriate indexes/constraints

Test migration upgrade

Test migration downgrade where supported by project policy



Never manually edit the database schema outside the migration system.



58\. Performance



College configuration retrieval is expected to be frequent.



Ensure:



Appropriate indexes

Efficient queries

No unnecessary N+1 queries

No full database scans for normal tenant lookup

Configuration retrieval remains college-scoped



Do not prematurely add distributed infrastructure.



59\. Observability



Configuration mutations should produce useful structured logs.



Include safe metadata such as:



Request ID

User ID

College ID

Operation

Result

Duration

Error category



Do not log secrets or sensitive configuration unnecessarily.



60\. Definition of Done



Task 004 is complete only when:



&#x20;College lifecycle is implemented.

&#x20;College identity configuration is implemented.

&#x20;Branding configuration is implemented.

&#x20;Contact configuration is implemented.

&#x20;Time zone configuration is implemented.

&#x20;Supported language configuration is implemented.

&#x20;Default language validation is implemented.

&#x20;Feature configuration is implemented where required.

&#x20;College configuration validation exists.

&#x20;Configuration completeness can be determined.

&#x20;College create/read/update/list APIs are implemented as required.

&#x20;Publish/activation workflow is implemented.

&#x20;Suspend workflow is implemented where required.

&#x20;Archive workflow is implemented where required.

&#x20;Lifecycle transitions are validated.

&#x20;Tenant authorization is enforced.

&#x20;Cross-tenant access is denied.

&#x20;Platform admin permissions work.

&#x20;College admin permissions work.

&#x20;Counselor permissions remain appropriately restricted.

&#x20;Audit events are recorded for important mutations.

&#x20;College context service exists.

&#x20;Nova demo tenant works.

&#x20;Second tenant works.

&#x20;No college-specific behavior is hardcoded.

&#x20;Unit tests pass.

&#x20;Integration tests pass.

&#x20;Tenant isolation tests pass.

&#x20;Existing Task 001–003 tests pass.

&#x20;No unrelated features are implemented.

&#x20;API documentation is updated where necessary.

61\. Required Agent Report



When complete, the implementing agent must report:



Implemented



List all college/configuration components created.



APIs



List endpoints implemented.



Configuration



List supported configuration categories.



Lifecycle



Describe supported college states and transitions.



Tenant Security



Explain how cross-tenant access is prevented.



Validation



Explain configuration validation and publish checks.



Database



List models/migrations changed.



Tests



Report:



Unit tests

Integration tests

Authorization tests

Tenant isolation tests

Lifecycle tests

Total tests passed

Remaining Work



Clearly identify anything intentionally deferred.



Risks / Decisions



Document important implementation decisions.



62\. Intended Owner



Primary owner:



Claude Code



Claude should implement the backend college configuration and onboarding foundation.



Codex should consume the API later for the onboarding/admin UI.



Do not have both agents modify the same backend files simultaneously.



63\. Git Workflow



Before implementation:



Read AGENTS.md

Read CLAUDE.md

Read architecture.md

Read database.md

Read api-contract.md

Read development.md

Read Tasks 001–003

Inspect the current backend

Plan the implementation



During implementation:



Implement incrementally

Run focused tests

Fix failures

Run all relevant backend tests



Before completion:



Review tenant isolation

Review RBAC

Review lifecycle transitions

Review validation

Review audit logging

Review API contract

Review migrations

Review security



Suggested commit:



feat(colleges): implement college configuration and onboarding foundation



Do not commit secrets.



Do not modify unrelated files.



64\. Final Principle



The college configuration system is what turns this project from a one-college demo into a reusable education-industry product.



The desired architecture is:



&#x20;                   AI ADMISSIONS PLATFORM

&#x20;                             │

&#x20;                 ┌───────────┴───────────┐

&#x20;                 │                       │

&#x20;            CORE ENGINE             CONFIG/DATA

&#x20;                 │                       │

&#x20;       ┌─────────┼─────────┐       ┌─────┼─────┐

&#x20;       ▼         ▼         ▼       ▼     ▼     ▼

&#x20;      AI       Voice      APIs     A     B     C

&#x20;      RAG      Tools               │     │     │

&#x20;      Leads    Apps                Config Config Config

&#x20;      Booking                     Data  Data  Data

&#x20;       │                           │     │     │

&#x20;       └───────────────────────────┴─────┴─────┘

&#x20;                             │

&#x20;                             ▼

&#x20;                        FINAL AGENT



The same software must be able to onboard a new college by supplying its configuration and data rather than rewriting the application.



Configuration changes. Core platform code does not.

