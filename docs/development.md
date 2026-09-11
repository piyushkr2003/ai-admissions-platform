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

