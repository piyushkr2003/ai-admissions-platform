````markdown

\# Task 007 — Lead Intelligence \& Scoring



\## 1. Task Overview



Implement the production-grade Lead Intelligence and Scoring subsystem for the AI Admissions Platform.



This task builds on the already implemented Tasks 001–006:



\- Task 001 — Backend Foundation

\- Task 002 — Database \& Multi-Tenancy

\- Task 003 — Authentication \& RBAC

\- Task 004 — College Configuration \& Onboarding

\- Task 005 — Knowledge Base / RAG

\- Task 006 — AI Admissions Agent Core



The purpose of this task is to make the platform capable of identifying, creating, enriching, scoring, classifying, and managing prospective-student leads based on their admission intent and meaningful actions.



The system must work across multiple colleges without hardcoded college-specific lead logic.



The lead subsystem must integrate cleanly with the existing AI agent, conversation system, appointment system, and future application workflow.



This is a production implementation, not a mock/demo-only feature.



\---



\# 2. Source of Truth



Before making changes, read:



\- AGENTS.md

\- CLAUDE.md

\- docs/product-requirements.md

\- docs/architecture.md

\- docs/database.md

\- docs/api-contract.md

\- docs/agent-tools.md

\- docs/rag.md

\- docs/voice.md

\- docs/development.md

\- docs/tasks/001-backend-foundation.md

\- docs/tasks/002-database-multitenancy.md

\- docs/tasks/003-auth-rbac.md

\- docs/tasks/004-college-configuration-onboarding.md

\- docs/tasks/005-knowledge-base-rag.md

\- docs/tasks/006-ai-admissions-agent.md

\- this task file



Inspect the existing implementation before coding.



Do not assume that the task specifications perfectly match the current implementation. Reuse the existing architecture and conventions wherever appropriate.



Do not rewrite unrelated working code.



\---



\# 3. Primary Objective



Implement a lead intelligence subsystem that can:



1\. Create a lead from a prospective student interaction.

2\. Identify an existing lead and update it rather than creating duplicates.

3\. Store structured lead information.

4\. Track meaningful lead events.

5\. Calculate a deterministic and explainable lead score.

6\. Classify leads as COLD, WARM, or HOT.

7\. Recalculate scores when meaningful events occur.

8\. Preserve a complete scoring history.

9\. Integrate lead creation/update with the AI admissions agent.

10\. Support manual/admin lead management through APIs.

11\. Enforce strict college/tenant isolation.

12\. Prepare the system for future analytics and CRM-style workflows.



\---



\# 4. Product Context



The platform is an AI admissions assistant for colleges.



The agent should recognize when a student or parent is showing meaningful admission intent.



Examples:



\- "I am looking for B.Tech CSE."

\- "I scored 82% in 12th."

\- "Am I eligible?"

\- "How much is the CSE fee?"

\- "Do you have scholarships?"

\- "Can I talk to a counselor?"

\- "Book me an appointment."

\- "I want to apply."

\- "What documents do I need?"

\- "Please help me start my application."



These interactions should progressively enrich a lead.



The platform must distinguish between casual information seekers and serious admission prospects.



\---



\# 5. Lead Entity



Use the existing Lead database model from Task 002.



Do not create a duplicate lead table unless the existing schema is demonstrably insufficient.



A lead must be college-scoped.



Every lead must belong to exactly one college.



Minimum conceptual fields:



\- id

\- college\_id

\- student\_id when available

\- conversation\_id when available

\- name

\- phone

\- email

\- course\_id

\- course\_interest

\- qualification

\- qualification\_score/marks when applicable

\- entrance\_exam

\- entrance\_exam\_score

\- budget when voluntarily provided and relevant

\- hostel\_interest

\- scholarship\_interest

\- location

\- parent\_involved

\- intent

\- status

\- score

\- temperature/classification

\- source

\- notes

\- last\_contacted\_at

\- last\_activity\_at

\- created\_at

\- updated\_at



Reuse existing database conventions and naming.



Do not store unnecessary sensitive information.



Do not collect information merely for scoring if it is not needed for admissions.



\---



\# 6. Lead Lifecycle



Define a clear lifecycle.



At minimum support:



\- NEW

\- CONTACTED

\- QUALIFIED

\- APPOINTMENT\_BOOKED

\- APPLICATION\_STARTED

\- CONVERTED

\- LOST

\- DISQUALIFIED



If the existing database specification defines different canonical values, preserve the existing specification and adapt the service implementation accordingly.



Do not silently create incompatible duplicate statuses.



Status transitions must be validated.



Examples:



NEW

→ CONTACTED

→ QUALIFIED

→ APPOINTMENT\_BOOKED

→ APPLICATION\_STARTED

→ CONVERTED



A lead may also become:



NEW

→ LOST



or:



NEW

→ DISQUALIFIED



The system must retain historical scoring/activity information even when status changes.



\---



\# 7. Lead Temperature



Every scored lead must have a temperature/classification.



Use:



\- COLD

\- WARM

\- HOT



Temperature must be derived from the configured score thresholds rather than independently maintained arbitrary values.



Default thresholds:



\- COLD: 0–39

\- WARM: 40–69

\- HOT: 70–100



Make the thresholds configurable where the existing college configuration architecture supports it.



Do not hardcode thresholds into multiple parts of the application.



A single scoring policy must be the source of truth.



\---



\# 8. Lead Scoring Principles



Lead scoring must be:



\- deterministic

\- explainable

\- auditable

\- bounded

\- repeatable

\- college-aware

\- event-driven

\- safe against duplicate event inflation



The same lead state and event history should produce the same score.



Do not use an LLM to calculate the numeric score.



The AI agent may identify intent and trigger events, but the scoring engine must remain deterministic.



\---



\# 9. Default Scoring Rules



Implement the scoring rules defined by the product requirements.



Default examples:



\- Course identified: +20

\- Basic eligibility confirmed: +20

\- Fee information discussed: +10

\- Scholarship interest: +10

\- Counselor appointment requested: +20

\- Application started: +30



The raw sum must be bounded to 100.



Do not allow duplicate identical events to inflate the score indefinitely unless the scoring policy explicitly allows repeated events.



For example:



A student asking "What is the CSE fee?" five times should not automatically receive +50.



Meaningful events should be deduplicated or governed by event-specific rules.



\---



\# 10. Additional Useful Scoring Signals



Where supported by the existing schema and architecture, support additional deterministic signals such as:



\- qualification information provided

\- entrance exam score provided

\- required documents requested

\- counselor appointment booked

\- appointment rescheduled

\- application details submitted

\- application draft created

\- high-intent admission request

\- scholarship eligibility inquiry

\- repeated meaningful engagement

\- explicit statement of intent to apply



Do not assign arbitrary points simply because a signal exists.



Every scoring rule must be:



\- named

\- documented

\- bounded

\- testable

\- explainable



\---



\# 11. Negative Signals



The scoring architecture should support negative scoring signals in the future.



Examples:



\- explicit cancellation of admission intent

\- lead marked disqualified

\- admission cycle no longer applicable

\- invalid contact information

\- explicit statement that the student is no longer interested



Negative scores must not cause the final score to go below 0.



The default implementation should only add negative rules where they are explicitly justified by the existing product requirements.



Do not invent aggressive decay logic.



\---



\# 12. Score Events



Implement a Lead Score Event mechanism using the existing `lead\_score\_events` model from Task 002.



Each scoring event should record enough information to explain why the score changed.



Conceptual fields:



\- id

\- college\_id

\- lead\_id

\- event\_type

\- points

\- source

\- metadata

\- created\_at



Examples:



```text

COURSE\_IDENTIFIED       +20

ELIGIBILITY\_CONFIRMED   +20

FEE\_DISCUSSION          +10

SCHOLARSHIP\_INTEREST    +10

APPOINTMENT\_REQUESTED   +20

APPLICATION\_STARTED     +30

````



If negative events are implemented:



```text

DISQUALIFIED            -20

EXPLICITLY\_NOT\_INTERESTED -10

```



Do not expose internal implementation details unnecessarily to public users.



\---



\# 13. Idempotency



Scoring events must be safe against duplicate delivery.



The same underlying business event must not accidentally increase a lead's score multiple times because of:



\* API retries

\* agent retries

\* webhook retries

\* network retries

\* repeated service execution



Where appropriate, support an idempotency key or source event identifier.



The exact mechanism should follow existing API/database conventions.



Tests must prove duplicate processing does not incorrectly inflate the score.



\---



\# 14. Score Recalculation



Implement a clear scoring service.



Conceptually:



```text

Lead

&#x20;↓

Load scoring events

&#x20;↓

Apply scoring policy

&#x20;↓

Bound score 0–100

&#x20;↓

Determine temperature

&#x20;↓

Persist score + temperature

```



The scoring service should not depend on presentation-layer logic.



Do not duplicate scoring calculations across API endpoints and the agent.



There must be one canonical scoring implementation.



\---



\# 15. Explainability



Every score should be explainable.



The system should be able to answer:



\* Why is this lead HOT?

\* Which events increased the score?

\* How many points came from each signal?

\* When did the score change?

\* What was the previous score?

\* What caused the latest change?



Example internal explanation:



```text

Score: 80

Temperature: HOT



Contributing signals:

+20 Course identified

+20 Eligibility confirmed

+10 Fee discussed

+10 Scholarship interest

+20 Counselor appointment requested

```



This information should be available through authorized staff/admin APIs.



Do not expose internal scoring mechanics to the student unless the product explicitly requires it.



\---



\# 16. Lead Creation



Implement a lead service capable of creating a lead from:



\* agent conversation

\* authenticated staff action

\* future API/webhook integrations



Lead creation must:



1\. Resolve college context server-side.

2\. Validate all supplied fields.

3\. Normalize contact information where appropriate.

4\. Associate the conversation when available.

5\. Associate the student record when available.

6\. Set initial status.

7\. Calculate initial score.

8\. Record initial scoring events.

9\. Return the resulting lead.



Never trust a client-supplied `college\_id` for authorization.



\---



\# 17. Lead Deduplication



Prevent obvious duplicate leads.



Possible matching signals:



1\. existing student identity

2\. normalized phone

3\. normalized email

4\. active conversation/student relationship



Use the existing database constraints and architecture.



Do not merge leads aggressively when identity is ambiguous.



If a reliable match exists:



```text

Existing Lead

&#x20;     ↓

Update existing lead

&#x20;     ↓

Add new events

&#x20;     ↓

Recalculate score

```



If no reliable match exists:



```text

Create new Lead

```



Avoid accidentally combining two different students who share a parent phone number.



\---



\# 18. Lead Enrichment



As conversations progress, update lead fields.



Example:



Initial:



```text

Name: Rahul

Course: B.Tech CSE

```



Later:



```text

Qualification: 12th

Marks: 82%

Scholarship interest: Yes

Hostel interest: Yes

Location: Bengaluru

```



Later:



```text

Appointment requested

```



Later:



```text

Application started

```



The lead should represent the latest known structured information.



Do not overwrite valid existing data with empty or uncertain values.



\---



\# 19. Agent Integration



Integrate Task 006 with the lead subsystem.



The agent should be able to invoke the existing lead tools:



\* `create\_lead()`

\* `update\_lead()`

\* `calculate\_lead\_score()`



If these tools already exist from Task 006, connect them to the real lead service.



Do not create duplicate agent tool implementations.



The agent should not directly manipulate database tables.



Use service interfaces.



\---



\# 20. Agent Lead Capture Rules



The agent should not interrogate students unnecessarily.



Collect lead information naturally when relevant.



Good example:



Student:



> I want B.Tech CSE.



Agent:



> Sure. May I know your Class 12 percentage so I can check your eligibility?



After the student responds, the agent can update the lead.



Do not ask for:



\* phone

\* email

\* budget

\* location

\* parent details



unless useful and appropriate for the current admission workflow.



Respect voluntary disclosure.



\---



\# 21. Lead Intent



Support a structured intent value.



Possible intent values:



\* INFORMATIONAL

\* EXPLORING

\* INTERESTED

\* HIGH\_INTENT

\* READY\_TO\_APPLY



If the existing database/API contract defines canonical values, use those values.



Intent should be updated based on meaningful actions, not arbitrary keyword matching alone.



Examples:



```text

"What courses do you have?"

→ INFORMATIONAL



"I am interested in B.Tech CSE."

→ INTERESTED



"Can I speak to a counselor?"

→ HIGH\_INTENT



"I want to apply today."

→ READY\_TO\_APPLY

```



The numeric score remains the canonical quantitative signal.



\---



\# 22. Appointment Signals



Integrate with the appointment subsystem without rebuilding the appointment engine.



Supported lead events should include:



\* appointment requested

\* appointment booked

\* appointment rescheduled

\* appointment cancelled



Appointment booking itself belongs to the appointment task.



This task should provide the clean integration points needed for appointment services to update leads.



Example:



```text

Student requests counselor

&#x20;       ↓

Appointment service

&#x20;       ↓

Appointment successfully booked

&#x20;       ↓

Lead event: APPOINTMENT\_BOOKED

&#x20;       ↓

Score recalculated

```



Do not award appointment points merely because a booking was attempted if the booking failed.



\---



\# 23. Application Signals



Integrate with the future application subsystem.



Support events such as:



\* APPLICATION\_STARTED

\* APPLICATION\_SUBMITTED

\* APPLICATION\_COMPLETED



Do not implement the complete application engine here.



The lead subsystem should expose service methods/interfaces that future application services can call.



Example:



```text

Application service

&#x20;       ↓

Application started successfully

&#x20;       ↓

Lead event

&#x20;       ↓

Lead score recalculated

```



\---



\# 24. API Endpoints



Implement or complete the lead APIs defined in:



`docs/api-contract.md`



At minimum support appropriate endpoints for:



\* create lead

\* list leads

\* get lead

\* update lead

\* retrieve lead scoring/history

\* trigger/recalculate score where authorized

\* filter leads by status

\* filter leads by temperature

\* filter by course

\* filter by intent

\* filter by date/activity

\* retrieve score events



Follow the existing API conventions.



Use:



```text

/api/v1

```



Do not invent a separate API version.



\---



\# 25. Authorization



Apply the RBAC system from Task 003.



At minimum:



\### Platform Admin



May access platform-level lead administration according to existing authorization rules.



\### College Admin



May access leads belonging to their own college.



\### Counselor / Admissions Staff



May access leads belonging to their assigned/authorized college.



\### Student / Parent / Public



Must not gain unrestricted access to internal lead-management endpoints.



Public/agent operations must use narrowly scoped service capabilities.



Do not expose internal lead lists publicly.



\---



\# 26. Tenant Isolation



Tenant isolation is mandatory.



Every lead query must be scoped by authenticated/server-resolved `college\_id`.



Never trust:



```text

?college\_id=...

```



or:



```json

{

&#x20; "college\_id": "..."

}

```



as an authorization boundary.



If a client attempts to access another college's lead:



\* return the appropriate authorization/not-found response according to existing API policy

\* never return the other college's data



Test cross-tenant access explicitly.



\---



\# 27. Filtering and Pagination



Lead listing APIs must support the existing pagination conventions.



Support useful filters:



\* status

\* temperature

\* course

\* intent

\* source

\* created date

\* last activity date

\* score range



Use database-level filtering rather than loading all leads and filtering in Python.



Use appropriate indexes.



\---



\# 28. Sorting



Support useful sorting such as:



\* newest

\* recently active

\* highest score

\* lowest score

\* recently updated



Default ordering should be deterministic.



Avoid unstable pagination caused by non-unique ordering.



\---



\# 29. Lead Activity



Maintain meaningful activity information.



At minimum support:



\* last activity timestamp

\* latest meaningful event

\* score changes

\* status changes



Do not create an unbounded duplicate activity table if the existing audit/event architecture already supports the requirement.



Reuse existing mechanisms where appropriate.



\---



\# 30. Auditability



Important staff actions should be auditable.



Examples:



\* lead created

\* lead updated

\* lead status changed

\* lead manually qualified

\* score manually recalculated

\* lead reassigned where supported

\* lead marked lost/disqualified



Use the existing audit-log architecture.



Do not log sensitive data unnecessarily.



\---



\# 31. Privacy



Lead data can contain personal information.



Follow the existing privacy/security requirements.



Rules:



\* Never log passwords.

\* Never log authentication tokens.

\* Minimize PII in application logs.

\* Do not expose email/phone unnecessarily.

\* Do not include sensitive lead fields in error messages.

\* Do not store unnecessary sensitive information.

\* Respect existing retention/audit policies.



\---



\# 32. Score Policy Configuration



Design the scoring service so that scoring rules are not scattered throughout the codebase.



Conceptually:



```python

ScoringPolicy

&#x20;   rules

&#x20;   thresholds

&#x20;   calculate()

&#x20;   classify()

```



The implementation can use constants initially if the existing college configuration model does not yet support configurable scoring.



However, keep the architecture ready for per-college configuration.



Future example:



```text

College A:

appointment booked = +20



College B:

appointment booked = +15

```



Do not hardcode college names into scoring code.



\---



\# 33. College-Specific Configuration



If Task 004 already provides a suitable configuration mechanism for lead scoring, use it.



Otherwise:



\* use platform defaults

\* provide a clean extension point

\* document that per-college scoring configuration can be added later



Do not create a complex configuration subsystem solely for this task if it is not justified by the current schema.



\---



\# 34. Service Architecture



Use clean separation.



Recommended conceptual structure:



```text

app/leads/

&#x20;   \_\_init\_\_.py

&#x20;   schemas.py

&#x20;   service.py

&#x20;   scoring.py

&#x20;   repository.py

&#x20;   policies.py

```



Adapt to the repository's existing structure if different.



Responsibilities:



\### Repository



Database access only.



\### Service



Lead business operations.



\### Scoring



Deterministic scoring policy.



\### Schemas



Request/response validation.



\### API



HTTP/auth/authorization concerns.



\### Agent Tools



Thin adapters around lead services.



Do not put business logic inside route handlers.



\---



\# 35. Transactional Behavior



Lead updates and scoring events must be transactional where appropriate.



Example:



```text

Update lead

\+

Create score event

\+

Recalculate score

\+

Persist score

```



These operations should not leave the lead in a partially updated state.



If an operation fails:



\* rollback appropriately

\* return a safe error

\* do not claim success to the agent



\---



\# 36. Concurrency



Handle concurrent lead updates safely.



Possible scenario:



```text

Agent request A

\+

Agent retry B

\+

Appointment webhook C

```



The resulting lead score must remain correct.



Use:



\* database transactions

\* unique constraints

\* idempotency

\* appropriate locking/versioning where needed



Do not rely solely on in-memory state.



\---



\# 37. Error Handling



Handle:



\* lead not found

\* duplicate lead

\* invalid student/course

\* invalid status transition

\* duplicate score event

\* database failure

\* unauthorized access

\* cross-tenant access

\* invalid score rule

\* malformed input



Errors must follow the existing API error envelope.



Never expose stack traces in production responses.



\---



\# 38. Agent Failure Behavior



If lead creation/update fails during an agent conversation:



The agent must not say:



> "I've created your lead."



unless the backend operation actually succeeded.



Instead it should safely continue the conversation and, where appropriate:



> "I couldn't save your details right now, but I can still help you with your admission questions."



Do not expose internal database errors to the student.



\---



\# 39. Lead Score Examples



\### Example A — Casual Visitor



```text

Student asks:

"What courses do you offer?"



Score:

0



Temperature:

COLD

```



\### Example B — Interested Student



```text

Course identified       +20

Fee discussed           +10

Scholarship interest    +10



Total = 40



Temperature:

WARM

```



\### Example C — High Intent



```text

Course identified             +20

Eligibility confirmed         +20

Fee discussed                 +10

Scholarship interest          +10

Appointment requested         +20



Total = 80



Temperature:

HOT

```



\### Example D — Application Started



```text

Course identified             +20

Eligibility confirmed         +20

Fee discussed                 +10

Appointment requested         +20

Application started           +30



Raw total = 100+



Final score = 100

Temperature = HOT

```



\---



\# 40. Score Recalculation Example



Given:



```text

Existing score = 40

Temperature = WARM

```



Student successfully books a counselor appointment:



```text

APPOINTMENT\_BOOKED +20

```



Result:



```text

Score = 60

Temperature = WARM

```



If the score crosses 70:



```text

Score = 70

Temperature = HOT

```



The classification must always be derived from the canonical score.



\---



\# 41. Duplicate Event Example



Student asks the same fee question repeatedly.



Bad implementation:



```text

Fee event  +10

Fee event  +10

Fee event  +10

Fee event  +10

Score = 40

```



Correct behavior:



```text

First meaningful fee discussion +10

Duplicate equivalent event ignored

Score remains 10 from this signal

```



The exact deduplication mechanism should follow the event identity/idempotency architecture.



\---



\# 42. Test Requirements



Add comprehensive tests.



Tests must use the project's real test infrastructure.



Do not replace database integration tests with mocks where real PostgreSQL is already available.



\---



\## 42.1 Lead Creation Tests



Test:



\* create lead

\* create lead with minimum information

\* create lead with full information

\* invalid fields

\* missing required fields

\* correct initial status

\* correct college association



\---



\## 42.2 Lead Update Tests



Test:



\* update course

\* update qualification

\* update scholarship interest

\* update hostel interest

\* update intent

\* update status

\* empty values do not unexpectedly erase useful data



\---



\## 42.3 Scoring Tests



Test every default scoring rule:



\* course identified

\* eligibility confirmed

\* fee discussion

\* scholarship interest

\* appointment requested

\* application started



Verify:



```text

score

\+

temperature

```



\---



\## 42.4 Score Bound Tests



Test:



```text

score < 0 → 0

score > 100 → 100

```



Verify temperature remains valid.



\---



\## 42.5 Temperature Tests



Test boundaries:



```text

0   → COLD

39  → COLD

40  → WARM

69  → WARM

70  → HOT

100 → HOT

```



\---



\## 42.6 Duplicate Event Tests



Test:



\* duplicate API request

\* duplicate agent event

\* duplicate webhook-style event

\* retry of same event



Verify the score is not incorrectly inflated.



\---



\## 42.7 Explainability Tests



Verify score history returns:



\* event type

\* points

\* timestamp

\* source

\* resulting score where supported



\---



\## 42.8 Tenant Isolation Tests



Create:



```text

College A

College B

```



Create leads in both.



Verify:



\* College A cannot read College B leads.

\* College B cannot read College A leads.

\* list endpoints are isolated.

\* score-event endpoints are isolated.

\* agent lead operations are isolated.

\* spoofed college\_id is ignored/rejected.

\* database queries contain proper tenant scoping.



\---



\## 42.9 RBAC Tests



Verify:



\* platform admin access

\* college admin access

\* counselor/admissions staff access

\* student/public denial of internal lead-management endpoints

\* cross-college access denial



\---



\## 42.10 Deduplication Tests



Test:



\* same student

\* same normalized email

\* same normalized phone

\* ambiguous shared contact

\* separate students



Verify safe behavior.



\---



\## 42.11 Status Transition Tests



Verify valid transitions.



Verify invalid transitions are rejected safely.



\---



\## 42.12 Agent Integration Tests



Verify:



```text

Conversation

&#x20;   ↓

Agent identifies lead signal

&#x20;   ↓

Lead service

&#x20;   ↓

Lead created/updated

&#x20;   ↓

Score event

&#x20;   ↓

Score recalculated

```



Verify the agent does not claim success when the lead operation fails.



\---



\## 42.13 Appointment Integration Tests



Where the appointment service is available, verify:



```text

appointment successfully booked

&#x20;       ↓

lead event recorded

&#x20;       ↓

score recalculated

```



Do not implement duplicate appointment logic.



\---



\## 42.14 Application Integration Tests



If the application service is not yet implemented, test against a clean interface/fake service contract.



Do not build the complete application engine here.



\---



\## 42.15 API Tests



Test:



\* authentication

\* authorization

\* validation

\* pagination

\* filtering

\* sorting

\* error responses

\* tenant isolation

\* score history



\---



\# 43. Performance



Avoid N+1 queries.



Lead listing must remain efficient with thousands of leads.



Use:



\* indexes

\* database filtering

\* appropriate joins

\* pagination

\* aggregate queries where appropriate



Do not load complete lead histories for every row in a list response.



\---



\# 44. Observability



Add structured logging for important lead operations.



Useful events:



```text

lead.created

lead.updated

lead.score\_changed

lead.temperature\_changed

lead.status\_changed

lead.score\_event\_created

lead.duplicate\_event\_ignored

```



Logs must include safe correlation information.



Do not log unnecessary PII.



Where the existing observability architecture supports metrics, expose:



\* leads created

\* leads updated

\* HOT leads

\* WARM leads

\* COLD leads

\* score changes

\* appointment-driven lead conversions

\* application-driven lead conversions



\---



\# 45. Seed Data



Update deterministic demo seed data where appropriate.



The fictional college is:



\*\*Nova Institute of Technology\*\*



Use fictional/sample data only.



Create several realistic demo leads covering:



\### Lead 1 — Cold



```text

Name: Demo Student 1

Course: BCA

Score: 20

Temperature: COLD

```



\### Lead 2 — Warm



```text

Name: Demo Student 2

Course: B.Tech CSE

Eligibility: confirmed

Fee discussed: yes

Score: 50

Temperature: WARM

```



\### Lead 3 — Hot



```text

Name: Demo Student 3

Course: B.Tech AI \& ML

Eligibility: confirmed

Scholarship interest: yes

Appointment requested: yes

Score: 70+

Temperature: HOT

```



Do not use real student information.



Ensure the seed is deterministic and safe to rerun.



\---



\# 46. Demo Workflow



The lead subsystem must support the main product demonstration.



Example:



```text

Student:

"I want B.Tech CSE."



&#x20;       ↓



Agent:

collects course interest



&#x20;       ↓



Lead created/updated



&#x20;       ↓



+20 course signal



&#x20;       ↓



Student provides qualification



&#x20;       ↓



Eligibility confirmed



&#x20;       ↓



+20 eligibility signal



&#x20;       ↓



Student asks about fees



&#x20;       ↓



+10 fee signal



&#x20;       ↓



Student asks about scholarship



&#x20;       ↓



+10 scholarship signal



&#x20;       ↓



Student asks for counselor



&#x20;       ↓



+20 appointment intent signal



&#x20;       ↓



Lead becomes HOT



&#x20;       ↓



Admin dashboard can see the lead

```



The score and event history must be accurate.



\---



\# 47. No Hallucination / Data Integrity



Lead intelligence must never invent student information.



If the student has not provided:



```text

phone

email

qualification

marks

budget

location

```



do not invent it.



Unknown values remain unknown.



Similarly, do not infer a confirmed admission decision merely because the lead has a high score.



A HOT lead means:



> high admission intent



It does not mean:



> admission guaranteed



\---



\# 48. Security Requirements



Verify:



\* tenant isolation

\* authorization

\* input validation

\* safe database access

\* no SQL injection

\* no unsafe dynamic query construction

\* PII minimization

\* safe logs

\* auditability

\* no client-controlled college context

\* idempotency

\* transaction integrity



Do not introduce new security dependencies unless necessary.



\---



\# 49. Backward Compatibility



Do not break:



\* existing Tasks 001–006 APIs

\* existing database migrations

\* authentication

\* college context

\* RAG

\* agent orchestration

\* conversation APIs



Run the full backend test suite after implementation.



If existing tests fail because of this task, fix the regression rather than weakening the existing tests.



\---



\# 50. Non-Goals



Do NOT implement:



\* frontend dashboard

\* UI lead management

\* full CRM

\* email campaigns

\* WhatsApp campaigns

\* SMS campaigns

\* marketing automation

\* predictive ML lead scoring

\* LLM-based numeric scoring

\* complete appointment engine

\* complete application engine

\* voice transport

\* STT

\* TTS

\* telephony

\* post-admission services

\* hostel check-in

\* campus navigation

\* academic calendar

\* exam information

\* general student services



This task is specifically the backend Lead Intelligence \& Scoring subsystem.



\---



\# 51. Production Quality Requirements



Implementation must be:



\* typed

\* modular

\* testable

\* transactional

\* tenant-safe

\* deterministic

\* explainable

\* observable

\* maintainable

\* production-oriented



Do not create placeholder code where real functionality is required.



Do not use fake success responses.



Do not silently swallow errors.



Do not weaken security for demo convenience.



\---



\# 52. Documentation



If implementation decisions materially differ from the existing specifications:



\* document the decision

\* update the appropriate documentation if necessary

\* do not silently diverge from the architecture



Keep task-specific implementation details concise.



\---



\# 53. Git Workflow



Before implementation:



```text

Inspect current branch and status.

```



Do not destroy or rewrite existing commits.



Implement Task 007 as a focused change.



Run tests.



Fix failures.



Review the diff.



Commit the completed task with a clear message such as:



```text

feat(leads): implement lead intelligence and scoring

```



Do not create unrelated commits.



Keep the working tree clean at the end.



\---



\# 54. Required Agent Workflow



Follow this exact workflow:



1\. Read all required documentation.

2\. Inspect the existing implementation.

3\. Inspect the existing Lead and LeadScoreEvent models.

4\. Inspect existing agent lead tools from Task 006.

5\. Inspect existing API conventions.

6\. Inspect existing authorization and tenant dependencies.

7\. Inspect existing database/repository/service patterns.

8\. Produce a concise implementation plan.

9\. Implement the scoring policy.

10\. Implement lead service functionality.

11\. Implement/update lead repository functionality.

12\. Implement/update schemas.

13\. Implement/update APIs.

14\. Integrate agent lead tools.

15\. Add integration points for appointment/application services.

16\. Add deterministic seed/demo data.

17\. Run focused tests.

18\. Fix failures.

19\. Run the complete backend test suite.

20\. Review tenant isolation and security.

21\. Review the diff.

22\. Commit the task.

23\. Report the results.



Do not stop at planning.



Do not ask for permission for ordinary implementation steps.



Only ask the user when a genuine architectural ambiguity cannot be resolved from the repository documentation.



\---



\# 55. Final Definition of Done



Task 007 is complete only when:



\* \[ ] Lead service is implemented.

\* \[ ] Lead creation works.

\* \[ ] Lead update works.

\* \[ ] Lead deduplication works safely.

\* \[ ] Lead enrichment works.

\* \[ ] Lead lifecycle is validated.

\* \[ ] Lead intent is supported.

\* \[ ] Deterministic scoring engine works.

\* \[ ] Default scoring rules are implemented.

\* \[ ] Score is bounded 0–100.

\* \[ ] COLD/WARM/HOT classification works.

\* \[ ] Score events are persisted.

\* \[ ] Duplicate score events are handled safely.

\* \[ ] Score history is explainable.

\* \[ ] Agent lead tools use the real lead service.

\* \[ ] Appointment integration points exist.

\* \[ ] Application integration points exist.

\* \[ ] Lead APIs are implemented.

\* \[ ] RBAC is enforced.

\* \[ ] Strict tenant isolation is enforced.

\* \[ ] Pagination/filtering/sorting work.

\* \[ ] Auditability is implemented where required.

\* \[ ] Privacy requirements are followed.

\* \[ ] Error handling is production-safe.

\* \[ ] Observability is present.

\* \[ ] Nova demo leads are seeded deterministically.

\* \[ ] Unit tests pass.

\* \[ ] Integration tests pass.

\* \[ ] API tests pass.

\* \[ ] Tenant-isolation tests pass.

\* \[ ] Agent integration tests pass.

\* \[ ] Full backend regression suite passes.

\* \[ ] No existing Task 001–006 functionality is broken.

\* \[ ] Working tree is clean.

\* \[ ] Task 007 is committed.



\---



\# 56. Required Final Report



At completion, report:



\## Files created/modified



List all relevant files.



\## Implementation summary



Briefly explain what was implemented.



\## Scoring policy



Show the implemented default scoring signals and thresholds.



\## Lead lifecycle



Show supported lead statuses and transitions.



\## API endpoints



List implemented/updated endpoints.



\## Agent integration



Explain how Task 006 now interacts with the lead subsystem.



\## Security / tenant isolation



Explain how isolation was enforced and tested.



\## Tests



Report:



```text

Focused tests:

X passed

Y failed



Full suite:

X passed

Y failed

```



Do not claim tests passed unless they were actually executed.



\## Seed/demo



Explain the demo lead data created for Nova Institute of Technology.



\## Known limitations



List genuine limitations only.



\## Git



Report:



\* branch

\* commit hash

\* commit message

\* working tree status



\---



\# 57. Final Principle



The Lead Intelligence subsystem is not merely a database CRUD layer.



It is the platform's deterministic admission-intent intelligence layer.



The goal is:



```text

Student interaction

&#x20;       ↓

Meaningful admission signal

&#x20;       ↓

Lead event

&#x20;       ↓

Explainable score

&#x20;       ↓

COLD / WARM / HOT

&#x20;       ↓

Next best admission action

```



The system must remain:



\*\*tenant-safe, deterministic, explainable, auditable, and ready for real college deployments.\*\*



````





