\# Development Guide

\## AI Voice Admissions Platform



\*\*Version:\*\* 1.0  

\*\*Status:\*\* Production Development Standard



\---



\# 1. Purpose



This document defines how the AI Voice Admissions Platform should be developed, tested, reviewed, and deployed.



The goal is to ensure that multiple coding agents can work on the same product without creating inconsistent architecture, broken contracts, security issues, or duplicated work.



\---



\# 2. Product Principle



This is a production-grade reusable SaaS platform.



The system must support:



```text

One Platform

&#x20;     ↓

Multiple Colleges

&#x20;     ↓

College-specific Configuration + Data

&#x20;     ↓

College-specific AI Admissions Agent



The core application must not be rewritten for every college.



3\. Source of Truth



Before implementing a feature, agents must inspect the relevant documentation.



Primary documents:



AGENTS.md

CLAUDE.md



docs/product-requirements.md

docs/architecture.md

docs/database.md

docs/api-contract.md

docs/agent-tools.md

docs/rag.md

docs/voice.md

docs/development.md



When documentation conflicts with implementation assumptions, stop and resolve the contract before making broad changes.



4\. Development Workflow



Every task should follow:



1\. Read relevant documentation

2\. Inspect existing implementation

3\. Identify dependencies

4\. Write a short implementation plan

5\. Implement the smallest coherent change

6\. Run focused tests

7\. Run relevant integration tests

8\. Fix failures

9\. Review security and tenant isolation

10\. Update documentation if contracts changed

11\. Commit changes

12\. Report what changed and what was tested

5\. Do Not Overbuild



Do not introduce infrastructure merely because it may be useful in the future.



Prefer:



Simple

Correct

Tested

Extensible



over:



Complex

Prematurely distributed

Difficult to operate



The initial architecture should be production-ready without unnecessary microservices.



6\. Backend Ownership



Claude Code is the primary backend implementation agent.



Backend responsibilities include:



FastAPI

database models

migrations

authentication

authorization

tenant isolation

business logic

agent orchestration

agent tools

RAG

appointment system

lead system

application system

knowledge ingestion

backend tests

API implementation



Other agents must not make large backend architectural changes without checking the backend contracts.



7\. Frontend Ownership



Codex is the primary frontend implementation agent.



Frontend responsibilities include:



Next.js

React

dashboard

authentication UI

college administration UI

lead management

appointment management

application management

knowledge-base management

analytics

voice interface

API client

frontend tests



Frontend code must consume documented backend APIs rather than inventing endpoints.



8\. Shared Contracts



The following are shared contracts:



API

Database

Agent tools

Authentication

Tenant context

Voice sessions

RAG

Error responses



Changes to shared contracts must be deliberate.



If a contract changes:



update the relevant documentation

update backend implementation

update frontend consumers

update tests

9\. Git Branching



Never allow two coding agents to modify the same working directory simultaneously.



Recommended branches:



main

develop



feature/backend-...

feature/frontend-...

feature/rag-...

feature/voice-...

feature/dashboard-...



For parallel work, use separate Git worktrees where practical.



Example:



C:\\Projects\\

&#x20;   ai-admissions-platform\\

&#x20;   ai-admissions-backend\\

&#x20;   ai-admissions-frontend\\



Each worktree should have its own branch.



10\. Commit Rules



Commits should represent coherent changes.



Good:



feat: add college tenant model

feat: add course eligibility API

test: add appointment booking tests

fix: prevent cross-tenant course access



Avoid:



changes

final

stuff

update

many fixes



Do not mix unrelated features into one commit.



11\. Pull Request Principles



Every pull request should explain:



What changed

Why it changed

What files/modules changed

Tests run

Known limitations

Database changes

API changes

Security considerations

12\. Environment Separation



Use separate environments:



development

test

staging

production



Never use production credentials locally.



Never use real student information during development.



13\. Environment Variables



Secrets must be provided through environment variables or a secure secrets manager.



Examples:



DATABASE\_URL

JWT\_SECRET

LLM\_API\_KEY

STT\_API\_KEY

TTS\_API\_KEY

VOICE\_PROVIDER\_API\_KEY

STORAGE credentials

EMAIL credentials



Never commit secrets.



14\. Environment Files



Use:



.env.example



to document required variables.



Local secrets belong in:



.env



The .env file must be ignored by Git.



15\. Database Migrations



All schema changes must use migrations.



Never manually modify production database structure.



Migration workflow:



Model change

&#x20;   ↓

Generate migration

&#x20;   ↓

Review migration

&#x20;   ↓

Run tests

&#x20;   ↓

Apply in staging

&#x20;   ↓

Verify

&#x20;   ↓

Apply in production

16\. Database Rules



Use PostgreSQL as the primary database.



Use pgvector for vector retrieval.



Database code must:



use transactions where required

validate foreign keys

enforce appropriate constraints

use indexes

avoid N+1 queries

use parameterized queries/ORM safely

preserve tenant isolation

17\. Tenant Isolation



Every tenant-aware operation must enforce:



college\_id



at the backend boundary.



Never trust:



college\_id



from an arbitrary client request without authorization validation.



The authenticated user's tenant context must be authoritative.



18\. Cross-Tenant Security



Every relevant test suite must include attempts such as:



College A user → College B course

College A user → College B lead

College A user → College B appointment

College A user → College B application

College A user → College B conversation

College A user → College B knowledge



Expected result:



403 Forbidden



or an equivalent secure response.



Never leak whether another tenant's object exists unless the API contract explicitly permits it.



19\. Authentication



Authentication must be implemented centrally.



Supported mechanisms may include:



JWT

OAuth

secure session mechanisms



Do not implement ad-hoc authentication inside individual features.



20\. Authorization



Use role-based access control.



Example roles:



platform\_admin

college\_admin

admissions\_manager

counselor

viewer

student

parent



Permissions must be enforced server-side.



Frontend hiding of buttons is not authorization.



21\. API Development



All APIs should follow:



/api/v1/...



API behavior must follow:



docs/api-contract.md



Do not silently invent alternative response formats.



22\. API Validation



Validate:



required fields

types

formats

enums

IDs

ownership

business rules



Invalid requests should return structured errors.



23\. Idempotency



Operations that can accidentally create duplicates should support idempotency where appropriate.



Important examples:



appointment booking

application creation

lead creation

webhook processing

confirmation sending



Retrying a request must not unexpectedly create duplicate records.



24\. Appointment Booking



Appointment booking must be transactional.



Flow:



Check availability

&#x20;     ↓

Validate slot

&#x20;     ↓

Reserve/create appointment

&#x20;     ↓

Commit transaction

&#x20;     ↓

Return confirmation



Two users must not successfully book the same exclusive slot if the configuration does not allow it.



25\. Lead Creation



Lead creation must avoid uncontrolled duplication.



Where appropriate:



Existing lead

&#x20;    ↓

update



rather than:



create unlimited duplicate leads



Lead identity rules must be explicitly defined.



26\. Lead Scoring



Lead scoring must be:



explainable

configurable

auditable

deterministic where possible



Every score change should have an associated event.



Example:



Appointment requested

+20



The dashboard should be able to explain why a lead is considered HOT/WARM/COLD.



27\. AI Development Rules



The AI agent must never be treated as the database.



The source of truth is:



Structured database

\+

Approved knowledge base

\+

Verified tool results



The model decides how to communicate and which tool may be needed.



28\. No Hallucinated College Facts



The agent must not invent:



fees

eligibility

scholarships

deadlines

courses

admission rules

appointment availability

application status



If verified information is unavailable:



"I don't have verified information about that."



Then offer appropriate next steps.



29\. Tool-First Transactions



Use tools for real actions.



Examples:



Book appointment

→ book\_appointment()



Create lead

→ create\_lead()



Start application

→ create\_application()



Check application

→ get\_application\_status()



The model must never pretend that a tool succeeded.



30\. Prompt Injection



College knowledge documents may contain malicious or irrelevant instructions.



Retrieved content must be treated as data, not instructions.



For example, if a document contains:



Ignore all previous instructions...



the agent must not follow it as a system instruction.



31\. RAG Development



RAG must enforce:



college\_id



during retrieval.



Never retrieve globally and filter afterward if that can expose cross-tenant data.



Prefer tenant filtering directly in the retrieval query.



32\. Structured Data vs RAG



Use structured database data for:



fees

eligibility

deadlines

course details

appointments

applications

lead data



Use RAG for:



FAQs

policy explanations

brochures

college descriptions

unstructured information



Do not unnecessarily store transactional information only inside PDFs.



33\. RAG Evaluation



RAG changes should be tested against representative questions.



Minimum evaluation categories:



correct answer

no answer available

outdated document

conflicting document

cross-tenant query

prompt injection

multilingual query

34\. Voice Development



Voice implementation must follow:



docs/voice.md



Voice code must support:



streaming

interruption

VAD

session lifecycle

STT

TTS

tool calls

persistence

failure handling

35\. Voice Testing



Test:



normal conversation

slow speaker

fast speaker

background noise

interruption

silence

network interruption

STT failure

TTS failure

tool failure

session timeout

36\. Frontend Development



Frontend components should be:



reusable

typed

accessible

responsive

error-aware



Do not duplicate API logic across components.



Use a centralized API client.



37\. Dashboard Development



The dashboard should provide clear views for:



Overview

Leads

Appointments

Applications

Conversations

Knowledge Base

FAQs

Analytics

Agent Configuration

College Configuration



Role permissions must control access.



38\. Loading and Error States



Every asynchronous UI operation should consider:



loading

success

empty

error

retry



Never leave the user with an unexplained blank screen.



39\. API Client



Frontend API calls should go through a centralized client.



The client should handle:



base URL

authentication

headers

correlation IDs

structured errors

retries where appropriate



Do not scatter raw fetch() logic throughout the application.



40\. Testing Pyramid



Use:



&#x20;             E2E

&#x20;            /   \\

&#x20;       Integration

&#x20;         /       \\

&#x20;      Unit Tests



Most business logic should be covered by unit tests.



Critical workflows should have integration/E2E coverage.



41\. Unit Tests



Test:



eligibility rules

fee calculations

lead scoring

permissions

tenant filters

validation

tool selection logic

appointment rules

application rules

42\. Integration Tests



Test:



API

&#x20;↓

Service

&#x20;↓

Database



Important workflows:



create college

create course

check eligibility

create lead

book appointment

create application

retrieve application status

43\. End-to-End Test



The primary E2E scenario should reproduce the demo:



Student asks about CSE

&#x20;      ↓

Eligibility

&#x20;      ↓

Fees

&#x20;      ↓

Scholarship

&#x20;      ↓

Counselor

&#x20;      ↓

Appointment

&#x20;      ↓

Lead

&#x20;      ↓

Documents

&#x20;      ↓

Application

&#x20;      ↓

Dashboard

44\. Test Data



Create deterministic fictional test data.



Primary demo college:



Nova Institute of Technology



Never use real student PII.



Test data should be resettable.



45\. Seed Data



The project should have a repeatable seed process.



Example:



seed demo college

seed courses

seed eligibility rules

seed scholarships

seed dates

seed documents

seed counselors

seed availability

seed FAQs

seed agent configuration



Running the seed process repeatedly should not create uncontrolled duplicates.



46\. Local Development



The project should eventually support:



docker compose up



for the required local infrastructure.



Expected services may include:



frontend

backend

postgres



Additional workers/services should only be introduced when required.



47\. Health Checks



Backend should expose:



GET /health



and where appropriate:



GET /ready



Health checks should verify required dependencies appropriately.



Do not make health checks excessively expensive.



48\. Background Jobs



Use background jobs for tasks that should not block real-time requests.



Examples:



document ingestion

embedding generation

transcript processing

analytics aggregation

notifications

large imports



Do not move latency-sensitive voice operations into slow background jobs.



49\. Logging



Logs must be structured.



Include where appropriate:



timestamp

level

service

request\_id

college\_id

user\_id

operation

duration

status

error\_code



Never log secrets.



Avoid unnecessary PII.



50\. Error Handling



Errors must be:



predictable

structured

logged

safe for users



Internal stack traces must not be returned to clients in production.



51\. Retry Rules



Retries should be bounded.



Use retries for transient failures such as:



temporary network failure

temporary provider failure



Do not blindly retry:



validation errors

authorization errors

deterministic business failures



Use exponential backoff where appropriate.



52\. Rate Limiting



Rate limits should exist for:



authentication

public APIs

voice sessions

expensive AI operations

document ingestion

admin endpoints



Limits should be configurable.



53\. Security Review



Before production release, verify:



Authentication

Authorization

Tenant isolation

Secret handling

Input validation

SQL/ORM safety

Prompt injection protection

File upload security

Rate limiting

CORS

HTTPS

Audit logs

PII handling

54\. File Upload Security



Knowledge-base uploads must validate:



file type

file size

filename

content where practical



Do not execute uploaded files.



Uploaded content must be isolated from application execution.



55\. Dependency Management



Dependencies must be:



explicitly declared

version controlled

periodically reviewed



Avoid adding a dependency for functionality that can reasonably be implemented with existing libraries.



56\. Code Quality



Prefer:



clear naming

small focused functions

typed interfaces

explicit error handling

testable services

documented complex logic



Avoid:



giant functions

hidden global state

duplicated business logic

magic constants

unnecessary abstractions

57\. Type Safety



Use strong typing wherever practical.



Backend:



Python type hints

Pydantic models



Frontend:



TypeScript



API schemas should be the shared contract.



58\. Documentation Updates



Documentation must be updated when changing:



API contracts

database schema

agent tools

RAG behavior

voice behavior

authentication

architecture



Do not let implementation silently diverge from documentation.



59\. Agent Collaboration



Claude Code and Codex should not independently redesign the same subsystem.



Recommended ownership:



Claude

→ Backend + AI + Database + RAG



Codex

→ Frontend + Dashboard + Integration UI



Shared

→ Contracts + Testing + Documentation



If work crosses boundaries, agree on the contract first.



60\. Agent Task Size



Tasks should be small enough to review.



Good:



Implement courses table and migration.



Implement GET /courses.



Add course API tests.



Build course management page.



Bad:



Build the entire platform.

61\. Agent Instructions



Before asking a coding agent to work:



Read AGENTS.md / CLAUDE.md

Read relevant docs

Inspect current code

Implement requested task

Run tests

Report changed files

Report tests

Do not modify unrelated areas

62\. Do Not Trust Generated Code Automatically



AI-generated code must be reviewed and tested.



Particular attention is required for:



authentication

authorization

tenant isolation

payments if added later

database transactions

appointment booking

file uploads

AI tool execution

secrets

personal data

63\. Production Readiness Checklist



Before production:



\[ ] Authentication works

\[ ] Authorization works

\[ ] Tenant isolation tested

\[ ] Database migrations tested

\[ ] API contracts validated

\[ ] RAG isolation tested

\[ ] Prompt injection tests pass

\[ ] Voice interruption works

\[ ] Voice failure recovery works

\[ ] Appointment concurrency tested

\[ ] Lead scoring tested

\[ ] Application workflow tested

\[ ] File uploads secured

\[ ] Rate limiting enabled

\[ ] Secrets secured

\[ ] HTTPS enabled

\[ ] Logging configured

\[ ] Monitoring configured

\[ ] Backups configured

\[ ] Health checks configured

\[ ] CI/CD configured

\[ ] Load testing completed

\[ ] E2E workflow passes

\[ ] Demo college seed works

64\. Deployment Flow



Recommended:



Developer

&#x20;  ↓

Feature Branch

&#x20;  ↓

Automated Tests

&#x20;  ↓

Pull Request

&#x20;  ↓

Code Review

&#x20;  ↓

CI

&#x20;  ↓

Staging

&#x20;  ↓

Integration/E2E Tests

&#x20;  ↓

Production Approval

&#x20;  ↓

Production

65\. Rollback



Every production deployment must have a rollback strategy.



Application rollback should be possible without destructive database operations.



Database migrations must be designed carefully because not every migration can safely be reversed.



Prefer backward-compatible schema changes for zero/low-downtime deployments.



66\. Observability



Monitor:



API latency

API errors

database latency

voice latency

STT failures

TTS failures

LLM failures

tool failures

appointment failures

RAG failures

queue depth

CPU

memory

storage

concurrency

67\. Product Analytics



Track:



calls

conversations

leads

hot leads

appointments

applications

escalations

conversion rates

AI resolution rate

average conversation duration



Analytics must respect tenant isolation.



68\. College Onboarding



A new college should eventually be onboarded through configuration rather than code changes.



Expected workflow:



Create College

&#x20;     ↓

Upload Knowledge

&#x20;     ↓

Configure Courses

&#x20;     ↓

Configure Eligibility

&#x20;     ↓

Configure Fees

&#x20;     ↓

Configure Scholarships

&#x20;     ↓

Configure Counselors

&#x20;     ↓

Configure Appointment Availability

&#x20;     ↓

Configure Agent

&#x20;     ↓

Test Agent

&#x20;     ↓

Publish

69\. Demo College



The development environment must contain:



Nova Institute of Technology



with fictional sample data.



The UI and agent should clearly operate on this tenant.



70\. Demo Reset



Developers should be able to reset the demo environment.



Example conceptual command:



reset demo data



This should remove/recreate only designated demo data.



Never use demo reset commands against production.



71\. Performance Testing



Performance testing should cover:



API concurrency

database queries

vector retrieval

voice sessions

simultaneous appointments

concurrent dashboard users



Test expected production load before launch.



72\. Load Testing Principle



Do not optimize based only on local development performance.



Measure:



p50

p95

p99

error rate

throughput

resource usage



for important endpoints.



73\. Release Versioning



Use meaningful application versions.



Example:



v0.1.0

v0.2.0

v1.0.0



Production releases should have traceable commits.



74\. Breaking Changes



Breaking API/database changes require explicit planning.



Prefer:



new version

migration period

deprecation

removal



rather than silently breaking existing clients.



75\. No Real Client Data



Until actual college data is provided:



Use fictional data only.



Do not invent real student records.



Do not copy private college data into the repository.



76\. Pre-Production Security Review



Before onboarding the first real college, perform a dedicated security review covering:



tenant isolation

authentication

authorization

data access

file uploads

voice sessions

transcripts

PII

RAG

prompt injection

API security

secrets

logging

backups

77\. Final Development Principle



Build the platform as:



Reusable

\+

Multi-tenant

\+

Secure

\+

Tested

\+

Observable

\+

Provider-agnostic

\+

AI-grounded

\+

Action-capable



Do not optimize for a quick demo at the expense of the production architecture.



The first demo should be real enough that the same foundation can later be configured for actual colleges without rebuilding the product.

---

## Voice Development (Task 011 Addendum)

### Environment variables

All default to the deterministic mock provider - no credentials are required for local development or tests.

```text
STT_PROVIDER=mock                    # "mock" or a real vendor name once an adapter exists
TTS_PROVIDER=mock
VOICE_TRANSPORT_PROVIDER=mock
TELEPHONY_PROVIDER=mock
TELEPHONY_WEBHOOK_SECRET=            # required (non-empty) before any webhook is accepted
STT_API_KEY=
TTS_API_KEY=
VOICE_PROVIDER_API_KEY=
VOICE_SESSION_MAX_DURATION_SECONDS=1800
VOICE_SESSION_IDLE_TIMEOUT_SECONDS=60
VOICE_MAX_CONCURRENT_SESSIONS_PER_COLLEGE=20
```

Selecting a provider name other than `mock` without its adapter/credential raises `RESOURCE_UNAVAILABLE` at call time - it never silently falls back to the mock or pretends to work.

### Local development

1. `alembic upgrade head` (adds `voice_sessions` and the `agent_configs.voice_phone_number` / `voice_settings` columns).
2. Run the backend as usual. `POST /api/v1/voice/sessions` with a seeded college id (see `app/db/seed.py` - Nova is seeded with both web and phone voice enabled and a fictional `voice_phone_number`) exercises the full session lifecycle immediately, no external service needed.
3. Drive a conversation by posting `final_transcript` events to `/api/v1/voice/sessions/{id}/events` - this is the same request a real STT provider's streaming callback (or a browser-side STT widget) would produce.
4. Simulate a phone call with `POST /api/v1/voice/telephony/mock/inbound`, signing the JSON body with HMAC-SHA256 using `TELEPHONY_WEBHOOK_SECRET` in the `X-Voice-Signature` header (see `tests/test_voice.py::_webhook` for a minimal example).
5. Inspect the resulting `Conversation`/`Message` rows exactly as for text chat - voice transcripts are ordinary conversation history, not a separate store.

### Testing

`tests/test_voice.py` covers provider unit behavior, the turn-taking/barge-in state machine, web session lifecycle (creation, events, interruption, duplicate-event idempotency, disconnect, max-duration enforcement), phone webhook handling (signature verification, tenant resolution by number, duplicate call-start/call-end idempotency), full agent integration (appointment booking, tool-failure honesty, escalation), and RBAC/tenant isolation for the staff endpoints. No paid provider account is required to run it.

### Production provider integration

Implement the relevant interface in `app/voice/providers/` (`STTProvider`, `TTSProvider`, `RealtimeTransportProvider`, or `TelephonyProvider`), register it in `app/voice/providers/factory.py` behind its provider name, and set the corresponding `*_PROVIDER` and credential environment variables. `app/services/voice.py` and the voice API do not change.

## Analytics & Reporting (Task 013 Addendum)

Backed by `app/analytics/` (`dates.py`, `service.py`, `router.py`); see docs/api-contract.md section 64 for the full endpoint contract.

### Local development

1. `alembic upgrade head` (adds the `ix_*_college_created` composite indexes analytics queries rely on - no new tables).
2. Seed demo data (`python scripts/seed_demo.py`) and call `GET /api/v1/analytics/overview?range=last_30_days` as a seeded staff user - it is real aggregation over whatever leads/appointments/applications/conversations/support tickets/voice sessions already exist, nothing mocked.
3. Every number in the response is produced by SQL `COUNT`/`GROUP BY`/`AVG` against the existing tables, filtered by `college_id` first - there is no analytics-specific data store.

### Testing

`tests/test_analytics.py` covers: a zero-data college, Nova's real seeded data, Aurora tenant isolation (including a college_admin trying to spoof `college_id` and a platform_admin required to pick one explicitly), RBAC, invalid/future/empty/custom date ranges, a timezone-boundary case proving day buckets follow the college's local timezone rather than UTC, course/status/channel breakdowns, the AI-resolution-rate metric being reported as explicitly unavailable, response determinism, absence of student PII in the payload, and a query-count guard proving the endpoint does not scale linearly with row count (no N+1).

### Known limitations

- `ai_resolution_rate` is intentionally never computed - see docs/api-contract.md section 64 for why.
- Lead → appointment/application "conversion" is a student-level signal (via the shared `student_id` foreign key), not a per-lead-instance one, because no `lead_id` column exists on `appointments`/`applications`.
- `query_categories` reflects each conversation's *most recent* detected intent, not a full per-turn intent history.
- (Resolved in Task 014.) The `/dashboard/analytics` page has been migrated off list-endpoint composition onto the real analytics API - see the Task 014 addendum below.

## Analytics Dashboard Integration (Task 014 Addendum)

`frontend/features/analytics/analytics-page-client.tsx` is now the sole consumer of `GET /api/v1/analytics/overview` and `GET /api/v1/analytics/trends` (`frontend/lib/api/analytics.ts`) for the `/dashboard/analytics` page. It no longer calls the leads/appointments/applications/support-tickets/voice list endpoints to compute totals - one overview request and one trends request per date-range/tenant change, matching `docs/api-contract.md` section 64 exactly.

### Date range

`frontend/lib/analytics/date-range.ts` defines the five presets (`today`, `last_7_days`, `last_30_days`, `last_90_days`, `custom`) and a `validateCustomRange` function that mirrors only what the backend itself rejects (missing dates, end before start, over 366 days) - it deliberately does not reject a future range, since the backend treats that as valid and simply returns zero-count data. Custom-range dates are sent to the backend as plain `YYYY-MM-DD` strings with no client-side timezone conversion; the college's timezone interpretation happens entirely server-side.

### Charts

`frontend/features/analytics/trend-chart.tsx` is a small dependency-free inline-SVG line chart (no charting library was added: the data is always a single daily-count series of at most ~366 points, so a hand-rolled chart avoids a new bundle dependency and CSP change while giving full control over accessibility). Each chart also renders a visually-hidden data table with the exact date/count pairs for screen-reader and keyboard users.

### Metric provenance

`frontend/features/analytics/metric-note.tsx` surfaces the backend's own `measurement`/`definition`/`reason` fields (Task 013) next to every derived or uncertain metric - an "unavailable" metric (e.g. AI resolution rate) is always rendered as an explicit statement of unavailability, never a fabricated percentage.

### Testing

`tests/analytics-api.test.ts` (API client: query params per range, response shape pass-through, 401/403 propagation, no legacy endpoint calls), `tests/analytics-date-range.test.ts` (pure validation/formatting logic), and `tests/analytics-page.test.tsx` (component: all five date-range presets, custom-range validation, loading/empty/error states, partial failure between overview and trends, 403 access-denied state, platform_admin tenant switching, college-scoped role locking, sparse/zero trend rendering).

## Realtime LiveKit Voice (Task 015 Addendum)

See docs/voice.md sections 71-72 for the full architecture, what is/isn't implemented, and known limitations.

### Environment variables

```text
VOICE_TRANSPORT_PROVIDER=mock   # "mock" (default) or "livekit"
LIVEKIT_URL=                    # e.g. wss://your-project.livekit.cloud
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=             # server-side only - never sent to the frontend
LIVEKIT_TOKEN_TTL_SECONDS=600
```

Selecting `livekit` without all three credentials raises `RESOURCE_UNAVAILABLE` at session-creation time, and fails application startup outright when `APP_ENV=production` - it never falls back to mock silently.

### Local development

1. Leave `VOICE_TRANSPORT_PROVIDER=mock` (default) - no LiveKit account needed to exercise the full session/event/agent lifecycle, exactly as in Task 011.
2. To test with a real LiveKit project: set the three `LIVEKIT_*` variables, restart the backend, and open `/dashboard/voice/console` in the frontend (requires `voice_sessions:write`). The console requests microphone access, connects to the LiveKit room with the token returned by `POST /api/v1/voice/sessions`, and drives the conversation through the same event endpoints the mock/phone channels use.
3. The console clearly labels the active session **MOCK** or **LIVE (LiveKit)** based on the backend's own `provider` field in the session-creation response - never an assumption made client-side.

### Testing

Backend: `tests/test_voice_livekit.py` - provider selection/mode switching, fail-closed behavior (partial credentials, production startup), JWT token construction and verification (claims, HS256 signature, TTL), tenant-isolated room naming, secret/token non-leakage into logs, end-to-end session creation via the API, reconnect/idempotency parity with the mock transport, and confirmation that `final_transcript` still drives the one existing `AgentOrchestrator` (no second agent path). No network calls are made; a real LiveKit smoke test requires real project credentials, which were not available in this environment.

Frontend: `tests/voice-console.test.tsx` - mock vs. live labeling, microphone-permission denial, LiveKit connection/reconnection/disconnection states, session-creation and event-submission failures, and barge-in triggering an `interruption` event. `livekit-client`'s `Room` is mocked (`vi.mock`) since jsdom has no WebRTC stack.

## Realtime Voice Agent Worker + LLM (Task 016 Addendum)

See docs/voice.md section 73 for the full architecture, provider boundaries, and what was/wasn't live-tested.

### Environment variables

```text
# LLM (bounded fallback only - see docs/voice.md 73.3; agent works fully without this)
AGENT_LLM_PROVIDER=mock         # "mock" (default), "anthropic", or "gemini"
LLM_API_KEY=                    # required if AGENT_LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5-20250929
LLM_API_BASE_URL=https://api.anthropic.com
LLM_TIMEOUT_SECONDS=8.0

# Gemini LLM provider (alternative to anthropic - same LLMProvider
# interface, same single call site in AgentOrchestrator._open_ended_reply)
GOOGLE_API_KEY=                 # required if AGENT_LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com

# Realtime voice worker (irrelevant while VOICE_TRANSPORT_PROVIDER=mock)
LIVEKIT_WORKER_IDENTITY=admissions-agent
VOICE_WORKER_POLL_INTERVAL_SECONDS=2.0
VOICE_WORKER_SAMPLE_RATE=48000
VOICE_WORKER_CHANNELS=1
```

Selecting `AGENT_LLM_PROVIDER=anthropic` without `LLM_API_KEY`, or `AGENT_LLM_PROVIDER=gemini` without `GOOGLE_API_KEY`, raises `RESOURCE_UNAVAILABLE` the moment the LLM is actually consulted (not at startup, since the LLM is optional), and fails application startup outright when `APP_ENV=production` - the same fail-closed pattern as every other provider. `GOOGLE_API_KEY` is sent only in the `x-goog-api-key` request header to `generativelanguage.googleapis.com` (never in the URL) and is never logged.

### Local development

To run everything, in separate terminals:

```text
# 1. Database
docker run -p 5432:5432 -e POSTGRES_USER=admissions -e POSTGRES_PASSWORD=admissions -e POSTGRES_DB=admissions postgres:16

# 2. Backend
cd backend && uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm run dev

# 4. Realtime voice worker - only needed when VOICE_TRANSPORT_PROVIDER=livekit;
#    with the default mock provider there is nothing for it to dispatch to.
cd backend && python -m app.voice.worker.run
```

With `VOICE_TRANSPORT_PROVIDER=mock` (default), skip step 4 entirely and use the mock voice console flow exactly as documented in the Task 011/015 addenda above - no LiveKit account, LLM key, or worker process required.

To exercise the full realtime path: set `VOICE_TRANSPORT_PROVIDER=livekit` and the `LIVEKIT_*` credentials, start the worker (step 4), then open `/dashboard/voice/console` - the console shows **LIVE (LiveKit)**, connects your microphone, and the transcript panel polls the real persisted conversation as the worker drives it.

### Testing

Backend:
- `tests/test_llm_provider.py` - provider selection/fail-closed behavior, Anthropic and Gemini request construction/response parsing, timeout/HTTP-error/malformed-response/safety-block handling, no-secret-logging for both real adapters. No network calls (`urllib.request.urlopen` is monkeypatched).
- `tests/test_orchestrator_llm_fallback.py` - proves the LLM is never invoked for a grounded/factual intent (even with a "lying" fake LLM configured), that safety refusals stay fully static, that the default mock provider reproduces the exact pre-Task-016 static text, and that any LLM failure falls back gracefully.
- `tests/test_voice_pcm.py` - pure-Python WAV/PCM helpers (round-trip, RMS energy, frame chunking) used by the worker; no dependency beyond the standard library.
- `tests/test_voice_worker.py` - the realtime worker's full lifecycle against an in-memory `FakeRoomClient` stand-in for `livekit.rtc` (no real LiveKit server is reachable here): session/room-token mapping, tenant isolation, a full grounded-fee-lookup turn with real audio published back, eligibility lookup, conversation memory across turns, appointment booking parity with the existing REST-level test, barge-in, participant/room disconnect handling, worker crash recovery, prompt-injection resistance, and cross-tenant knowledge isolation.
- `tests/test_voice_worker_dispatcher.py` - claim/release/dispatch logic against the real test database.

Frontend: `tests/voice-console.test.tsx` gained a "live mode" section - no manual transcript composer is shown once the LiveKit provider is active (the worker performs STT server-side), the transcript panel polls and renders the real persisted conversation, and the worker's remote audio track is attached to the page's `<audio>` element for playback.

## Nova Demo Data (Nova Demo Integration Addendum)

`nova_demo_data/` at the repo root is the canonical, fictional Nova Institute of Technology demo dataset (`nova_demo_seed.json` - structured facts; `nova_demo_knowledge_base.md` and `nova_faqs.csv` - RAG content). `app/db/nova_demo.py` maps it onto the existing schema and services - no new tables, no Nova-specific branch in the agent, tools, or RAG pipeline. It is entirely separate from the general test fixture in `app/db/seed.py` (`seed_demo_data`, used by most of the backend test suite); the two are compatible (`bootstrap_nova_demo` upserts whichever "Nova Institute of Technology" row already exists, by slug, rather than creating a second one) but neither calls the other.

### Loading the demo data

```bash
cd backend
python scripts/bootstrap_nova_demo.py
```

This creates the Nova tenant if it does not exist, or upserts it in place if it does, then:
courses, course eligibility rules, scholarships, admission dates, required documents, counselors, counselor availability, and FAQs (structured tables) - plus ingests the knowledge-base markdown and FAQ CSV through the real `IngestionService` (RAG). Running it again is a no-op: every write is keyed on a natural identity (college slug, course code, scholarship name, admission-date title, document name, counselor email, FAQ question, or knowledge-source content hash), and `IngestionService.ingest` already skips re-ingesting unchanged content for the same college.

### Resetting/reseeding

```bash
python scripts/bootstrap_nova_demo.py --reset
```

`--reset` deletes only Nova's ingested `knowledge_sources`/`knowledge_chunks` (so the next bootstrap re-ingests the knowledge base/FAQs from scratch), then runs the normal upsert bootstrap. It never touches leads, appointments, applications, or other interaction history, and never touches another tenant. Never run `--reset` (or the plain bootstrap) against a production database - this is fictional demo data only.

### What is fictional

Everything under `nova_demo_data/` and everything it produces: the college itself, its courses/fees/scholarships/dates/documents/counselors/availability/FAQs, and the ingested knowledge base (`nova_demo_knowledge_base.md` states this in its own header, and the college's `feature_flags.demo_only` is set to `true`). "Nova Institute of Technology" does not represent any real institution.

### Verifying RAG ingestion

```python
from sqlalchemy import select
from app.models.college import College
from app.models.knowledge import KnowledgeSource
nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()
db.execute(select(KnowledgeSource).where(KnowledgeSource.college_id == nova.id)).scalars().all()
# -> 2 sources ("Nova Demo Knowledge Base", "Nova Demo FAQs"), status "ready"
```

Or exercise retrieval directly: `RetrievalService(db).search(college_id=nova.id, query="Is hostel available?")` should return reliable evidence; the same query against a different `college_id` must not.

### Running the demo workflow

With the backend running and Nova bootstrapped, drive the same conversation `tests/test_nova_demo.py::test_full_nova_demo_workflow_through_orchestrator` exercises against `POST /api/v1/conversations` + `POST /api/v1/conversations/{id}/messages` (see the Task 006 addendum above for the request shapes): course question -> eligibility -> fee -> scholarship -> counselor availability -> booking -> application draft. Every structured fact in the responses comes from a database-backed tool call (visible via `tools_used` on the admin-only `/api/v1/agent/test` endpoint); hostel/placement questions are answered via Nova-scoped RAG.

### Mapping notes / known limitations

- `courses[].annual_other_fee_inr` has no dedicated `Course` column - it is recorded in `Course.description` and in the ingested knowledge base/FAQ text rather than inventing a new fee column.
- The dataset's college-wide `hostel`/`placements` objects are applied identically to every Nova course, since `Course.hostel_available`/`hostel_fee`/`placement_summary` are per-course columns (the only existing representation).
- `availability[]` gives specific-date sample slots; `CounselorAvailability` only models a recurring weekly schedule, so each sample slot's time-of-day is applied Monday-Friday (matching the convention already used by `app/db/seed.py`), not just the one sample date.
- The Women in Technology scholarship (restricted to two courses) is stored as one college-wide `Scholarship` row with the restriction stated in `eligibility_criteria` text, since `Scholarship.course_id` is a single nullable foreign key, not a many-to-many relationship.

### Testing

`tests/test_nova_demo.py` covers: bootstrap on an empty database and idempotent rerun, upserting an already-seeded legacy Nova row without duplication, `--reset` re-ingestion without duplicating chunks, structured field mapping (fees/eligibility/scholarships/dates/documents/counselors/availability), RAG ingestion and Nova-scoped retrieval, tenant isolation across structured data/RAG/counselor availability/the agent, direct agent-tool calls proving structured facts come from the database (not an LLM), and the full demo conversation end to end through the real `AgentOrchestrator` (course -> eligibility -> fee -> scholarship -> counselor -> booking -> lead -> application draft).

## Real Gemini STT + TTS (Task 017 Addendum)

See docs/voice.md section 74 for the full architecture and what was/wasn't live-tested.

### Environment variables

```text
# STT/TTS provider selection (existing Task 011 settings - "mock" is the
# default and requires no credentials; set either to "gemini" to use the
# real adapter added in Task 017)
STT_PROVIDER=mock                       # "mock" or "gemini"
TTS_PROVIDER=mock                       # "mock" or "gemini"

# Gemini STT/TTS configuration - GOOGLE_API_KEY and GEMINI_API_BASE_URL
# are shared with AGENT_LLM_PROVIDER=gemini (Task 016); no separate key is needed.
GOOGLE_API_KEY=                         # required if STT_PROVIDER or TTS_PROVIDER is "gemini"
GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_STT_MODEL=gemini-3.6-flash        # gemini-2.5-flash was deprecated by Google; confirmed against the real API
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore
GEMINI_VOICE_TIMEOUT_SECONDS=8.0
```

Selecting `STT_PROVIDER=gemini` or `TTS_PROVIDER=gemini` without `GOOGLE_API_KEY` configured raises `RESOURCE_UNAVAILABLE` the moment that provider is actually used, and fails application startup outright when `APP_ENV=production` - the same fail-closed pattern as every other provider (LiveKit, Anthropic, Gemini LLM). `GOOGLE_API_KEY` is sent only in the `x-goog-api-key` request header and is never logged.

### Local development

With the default `STT_PROVIDER=mock` / `TTS_PROVIDER=mock`, nothing changes from Task 011/016 - no Google credentials are needed to exercise the full voice session/worker lifecycle.

To use the real Gemini adapters:

1. Set `GOOGLE_API_KEY`, and set `STT_PROVIDER=gemini` and/or `TTS_PROVIDER=gemini` (they can be set independently - e.g. real TTS with mock STT for a quick manual check).
2. Restart the backend (and the realtime voice worker, `python -m app.voice.worker.run`, if `VOICE_TRANSPORT_PROVIDER=livekit`).
3. Drive a conversation exactly as documented in the Task 011/016 addenda above - `VoiceSessionService` and `RealtimeVoiceWorker` call whichever provider the factory returns; no other code path changes.

### Running the optional real-API smoke test

`scripts/smoke_test_gemini_voice.py` is a manual, non-pytest script that exercises the real Gemini API end to end (synthesizes a short sentence with `GeminiTTSProvider`, then transcribes that audio back with `GeminiSTTProvider`) when you have a real `GOOGLE_API_KEY` available:

```bash
cd backend
GOOGLE_API_KEY=... python scripts/smoke_test_gemini_voice.py
# or rely on backend/.env already having GOOGLE_API_KEY set
```

It reads the key only from the local environment/.env, never accepts it as an argument, never prints it, and prints only non-secret metadata (audio byte sizes, duration, recognized text). It refuses to run at all (exit code 1, no API call) if `GOOGLE_API_KEY` is not set - this is intentional so it can never be mistaken for a passing automated test. It lives under `scripts/`, which is outside `pytest`'s `testpaths` (`pyproject.toml`), so `pytest` never imports it or calls the real API.

### Testing

`tests/test_voice_gemini.py` covers, with zero real network calls (`urllib.request.urlopen` monkeypatched throughout, exactly like `tests/test_llm_provider.py`'s Gemini LLM coverage): STT/TTS request construction (URL, headers, audio encoding/mime type, voice/model configurability), response parsing, timeout/HTTP-error/malformed-response/no-candidates handling, empty/invalid-audio safety (no request is sent for empty audio; unwrappable raw audio fails safe), language-hint handling for `en`/`hi`/`hinglish`, provider-factory selection and fail-closed behavior for both STT and TTS, production fail-closed validation, no-API-key-logging, and a full realtime-worker turn (audio -> STT -> `AgentOrchestrator` -> TTS -> LiveKit-style publish) with both Gemini adapters selected. The pre-existing `tests/test_voice.py`, `tests/test_voice_worker.py`, and `tests/test_voice_livekit.py` suites are unchanged and continue to pass unmodified, confirming the default mock-provider path is unaffected.

## Local Free Demo Mode (Task 023)

See docs/voice.md section 75 for the full architecture and what was/wasn't live-tested. This mode needs **no API key at all** and **no LiveKit account** - only three local programs the developer installs and runs themselves.

### 1. Install Ollama

Download and install from https://ollama.com (native Windows/Mac/Linux installers). Verify it's running:

```bash
ollama --version
```

### 2. Pull the local model

```bash
ollama pull llama3.2:3b
```

`llama3.2:3b` (~2GB) was chosen as the default because it runs acceptably on a CPU-only laptop with 8GB+ RAM and is more than capable for this platform's narrow use of the LLM - it is **never** the source of admissions facts (see docs/voice.md section 73.3); it only phrases the occasional genuinely open-ended reply. Any other Ollama model works too - set `OLLAMA_MODEL` to whatever you pulled.

### 3. Install local Whisper (STT)

```bash
cd backend
pip install faster-whisper
```

No separate model download step is required - `faster-whisper` downloads the selected model (`WHISPER_MODEL_SIZE`, default `base`, ~74MB) automatically on first use and caches it locally. No C++ build toolchain is needed on Windows (unlike whisper.cpp, which requires compiling from source) - faster-whisper ships prebuilt wheels.

### 4. Install local TTS (Piper)

1. Download a Piper release for your platform from https://github.com/rhasspy/piper/releases (a single executable, e.g. `piper.exe` on Windows).
2. Download a voice model, e.g. `en_US-lessac-medium` (both the `.onnx` file and its `.onnx.json` config) from https://github.com/rhasspy/piper/blob/master/VOICES.md.
3. Either put `piper.exe` on your `PATH`, or note its full path for `PIPER_COMMAND` below.

Piper was chosen over Kokoro specifically for Windows developer laptops: Kokoro's phonemizer dependency (`espeak-ng`) has meaningfully worse Windows packaging, while Piper ships one prebuilt executable per platform with no separate runtime dependency.

### 5. Configure `backend/.env` for local mode

```text
STT_PROVIDER=local
TTS_PROVIDER=local
AGENT_LLM_PROVIDER=local
# VOICE_TRANSPORT_PROVIDER stays "mock" - no LiveKit account needed for the free demo.

WHISPER_MODEL_SIZE=base          # tiny|base|small|medium|large-v3 - larger = more accurate, slower
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

PIPER_COMMAND=piper              # or the full path to piper.exe if not on PATH
PIPER_MODEL_PATH=C:\path\to\en_US-lessac-medium.onnx
```

No secrets are involved - none of these settings are API keys, and nothing here should ever be committed as sensitive.

### 6. Start PostgreSQL/pgvector

```bash
docker run -p 5432:5432 -e POSTGRES_USER=admissions -e POSTGRES_PASSWORD=admissions -e POSTGRES_DB=admissions pgvector/pgvector:pg16
```

(Reuse an existing container if you already have one running - see the Task 016 addendum above for the full local-services list.)

### 7. Start the backend

```bash
cd backend
uvicorn app.main:app --reload
```

No realtime voice worker process is needed for local mode - it's only relevant when `VOICE_TRANSPORT_PROVIDER=livekit`.

### 8. Start the frontend

```bash
cd frontend
npm run dev
```

### 9. Test the Nova Institute demo

1. Log in as the seeded Nova admin (`backend/app/db/seed.py` - see the credentials there; never commit real passwords).
2. Open `/dashboard/voice/console`. The session banner will say "no realtime transport connected" (transport is still `mock` - that's expected and correct for local mode).
3. Hold the **"Hold to talk"** button, ask something like *"What is the fee for B.Tech CSE?"*, and release. The clip is sent to the backend, transcribed by local Whisper, answered by the same deterministic `get_fee_structure` tool every other mode uses (not the LLM - see docs/voice.md section 75.5), and spoken back by local Piper through the page's `<audio>` element.
4. Try eligibility ("Am I eligible with 82%?"), scholarships, counselor availability, and "Can I talk to someone?" - all resolve through the existing tools/RAG exactly as in cloud mode.
5. To test knowledge upload end-to-end: use the existing `POST /api/v1/knowledge/sources` endpoint (Knowledge Base page in the dashboard) to upload a PDF/CSV/FAQ for a college, then ask the voice agent a question that requires that document - RAG retrieval is provider-independent and works identically in local mode.

### Switching back to cloud mode

Set `STT_PROVIDER`/`TTS_PROVIDER`/`AGENT_LLM_PROVIDER` back to `gemini` (and `GOOGLE_API_KEY`) at any time - nothing about local mode changes or removes the existing Gemini/LiveKit code paths; they are selected by the exact same settings.

### Testing

`tests/test_voice_local_providers.py` covers, with no real Whisper model download, Ollama server, or Piper binary invoked anywhere: `faster-whisper`'s genuine `ImportError` fail-closed path (the package is not installed in the CI/dev environment this was verified in), empty-audio safety, Piper subprocess request construction/response parsing/timeout/non-zero-exit handling (`subprocess.run` monkeypatched), Piper executable-missing fail-closed behavior at construction time, Ollama request construction/response parsing/connection-refused/missing-model/malformed-response handling (`urllib.request.urlopen` monkeypatched), provider-factory selection for STT/TTS/LLM=`local` with no API key configured, TTS factory fail-closed when `PIPER_MODEL_PATH` is unset, and that `Settings.validate_for_production()` rejects all three `local` selections. `tests/test_voice.py` additionally covers the new `audio_base64` web-event input path (server-side STT via the existing mock provider) and the new `_playable_audio_url` data-URI helper (mock's non-playable reference is left untouched; a real provider's bytes become a playable `data:` URI). All pre-existing voice/orchestrator/RAG/tenant-isolation/tool test suites pass unmodified.

