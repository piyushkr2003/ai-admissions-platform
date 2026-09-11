\# Task 002 — Database \& Multi-Tenancy



\## Objective



Implement the production-ready PostgreSQL database foundation and multi-tenant data model for the AI Voice Admissions Platform.



This task must follow:



\- docs/database.md

\- docs/architecture.md

\- docs/api-contract.md

\- docs/product-requirements.md

\- docs/development.md



Do not redesign the database independently of the documented specification.



\---



\# Read First



Before implementation, read:



\- AGENTS.md

\- CLAUDE.md

\- docs/database.md

\- docs/architecture.md

\- docs/api-contract.md

\- docs/product-requirements.md

\- docs/development.md

\- docs/tasks/001-backend-foundation.md



Inspect the backend foundation created by Task 001 before making changes.



\---



\# Scope



Implement the database schema required by the documented product.



This includes:



1\. college/tenant model

2\. users and roles

3\. students

4\. courses

5\. eligibility rules

6\. scholarships

7\. admission dates

8\. required documents

9\. counselors

10\. counselor availability

11\. appointments

12\. leads

13\. lead score events

14\. applications

15\. application documents

16\. conversations

17\. messages

18\. knowledge sources

19\. knowledge chunks

20\. support tickets

21\. agent configuration

22\. FAQs

23\. audit logs



Implement appropriate relationships, constraints, indexes, timestamps, and tenant isolation.



\---



\# Primary Requirement



The most important database requirement is strict tenant isolation.



The platform must support:



```text

College A

College B

College C



using the same software.



College-specific records must never be accessible across tenants.



College Model



Create the primary colleges entity.



It should support information such as:



id

name

slug

description

logo/configuration references where appropriate

status

contact information

created\_at

updated\_at



Use an appropriate stable primary key.



The college slug should be unique.



User Model



Create users according to the database specification.



Support appropriate roles including:



platform\_admin

college\_admin

admissions\_manager

counselor

viewer

student

parent



Do not assume frontend authorization is sufficient.



Backend authorization will use these records later.



User Tenant Relationship



College staff must belong to a college.



Platform-level administrators may have broader access according to the documented RBAC model.



Do not create an ambiguous tenant relationship.



Student Model



Create the student entity required by the product.



It should support information needed for:



admission conversations

lead management

application assistance

appointment booking

eligibility evaluation



Avoid storing unnecessary personal information.



Parent Support



The schema should support parent users/relationships where required by the database specification.



Do not duplicate student records merely because a parent interacts with the agent.



Course Model



Create:



courses



with the fields and relationships defined in:



docs/database.md



Courses must belong to a college.



A course from College A must never appear as a course belonging to College B.



Eligibility Rules



Create the eligibility rule model.



It must support configurable requirements such as:



qualifying examination

stream

minimum percentage

entrance examination requirements

other documented conditions



Eligibility rules must belong to the correct college/course context.



Scholarships



Create scholarship entities supporting:



scholarship name

eligibility

benefit/value

applicable course(s)

validity

relevant conditions



Use structured fields for information the agent must reliably query.



Admission Dates



Create admission-date entities supporting:



application opening

application deadline

relevant admission milestones

academic year

status/effective period



Dates must be tenant scoped.



Required Documents



Create the required-document model.



Documents may be associated with:



college

course

application stage



The schema must support different document requirements for different programs where necessary.



Counselors



Create:



counselors



with appropriate relationships to:



college

user where applicable

counselor profile

active/inactive status

Counselor Availability



Create counselor availability supporting:



date

time

duration

availability status

counselor

college



The schema must support future appointment booking.



Appointments



Create the appointment model.



It must support:



student

counselor

college

start time

end time

status

appointment type

notes where appropriate



Statuses should follow the documented API/database contracts.



Appointment Concurrency



The schema must help prevent conflicting bookings.



Use appropriate:



unique constraints

indexes

transactional patterns

database constraints



Do not rely only on frontend checks.



Final booking logic will be implemented in a later task.



Leads



Create the lead model.



Lead information should support:



student

course interest

qualification

entrance score

budget where voluntarily provided

hostel interest

scholarship interest

location

parent involvement

intent

next action

lead status

lead score



Only store fields defined by the product/database specification.



Lead Score Events



Create an auditable score-event model.



Example:



course identified

+20



eligibility confirmed

+20



appointment requested

+20



The event should preserve enough information to explain score changes.



Do not hardcode the final scoring algorithm inside the database model.



Applications



Create the application entity.



It must support:



student

college

course

application status

academic year

application reference

timestamps



The schema must support the later "Apply with me" workflow.



Application Documents



Create application-document records.



Support:



document type

application

storage reference

status

verification metadata where required



Do not store large binary files directly in PostgreSQL unless the documented architecture explicitly requires it.



Prefer object storage references.



Conversations



Create conversation records.



A conversation must be associated with:



college

student/user when known

channel

status

timestamps



Support both:



web\_voice

phone



and future channels if the architecture requires them.



Messages



Create message records supporting:



conversation

speaker/role

content

timestamp

message type

metadata where appropriate



Support:



student

agent

system/tool



as appropriate to the documented model.



Voice Session Relationship



Voice sessions must be traceable to conversations.



Do not duplicate entire conversation data inside a voice-session record.



Store session-specific metadata separately.



Knowledge Sources



Create the knowledge-source entity.



Support:



college

source type

source name

status

version

effective dates where appropriate

metadata



Possible sources:



PDF

CSV

Excel

FAQ

website

manual entry

Knowledge Chunks



Create vector/RAG chunk storage according to:



docs/rag.md



Requirements include:



college ownership

source ownership

chunk text

metadata

embedding

embedding model/version information where required

timestamps



Use pgvector where appropriate.



RAG Tenant Isolation



Vector retrieval must be capable of enforcing:



college\_id



at query time.



The schema/index design must support efficient tenant filtering.



Never design retrieval around:



retrieve everything

→ filter tenant later

Agent Configuration



Create agent configuration records.



Support college-specific configuration such as:



agent name

greeting

tone

language configuration

voice configuration

behavior settings



Platform safety rules must remain outside tenant-controlled configuration.



FAQs



Create FAQ records.



FAQs should belong to a college and support:



question

answer

category

active status

ordering/priority where appropriate

timestamps

Support Tickets



Create support ticket records supporting:



college

student/user

conversation where applicable

category

priority

status

assigned counselor/staff member

timestamps

Audit Logs



Create audit logs for important actions.



Examples:



appointment created

appointment cancelled

application created

lead updated

knowledge source uploaded

agent configuration changed

user permission changed



Audit logs should capture enough information to investigate important events.



Do not store secrets in audit logs.



Common Columns



Use consistent timestamp conventions.



Where appropriate:



created\_at

updated\_at

deleted\_at



Do not add soft deletion everywhere automatically.



Use it where the documented lifecycle requires it.



Primary Keys



Use a consistent primary-key strategy across the application.



The choice must be appropriate for:



distributed systems

security

external API exposure

database performance



Do not expose sequential internal identifiers unnecessarily through public APIs.



Foreign Keys



Use foreign keys wherever relationships are mandatory.



Examples:



course → college

lead → college

appointment → college

appointment → counselor

application → student

application → course

conversation → college

knowledge\_source → college

knowledge\_chunk → knowledge\_source

Indexing



Create indexes for common queries.



At minimum consider:



college\_id

college\_id + status

college\_id + created\_at

college\_id + updated\_at

course lookups

lead filtering

appointment scheduling

application lookup

conversation lookup

knowledge retrieval



Do not create indexes blindly on every column.



Unique Constraints



Use unique constraints for values that must not be duplicated.



Examples may include:



college slug

college-scoped course identifiers

application references

appropriate external IDs



Follow the exact database specification.



Tenant Composite Constraints



Where required, use composite unique constraints to prevent cross-tenant collisions.



For example:



(college\_id, slug)



or equivalent documented combinations.



Database Transactions



The schema must support transactional business operations.



Important future workflows:



appointment booking

lead creation/update

application creation

document status updates



Do not implement complete service-layer workflows in this task.



Soft Delete / Data Lifecycle



Follow the lifecycle requirements in:



docs/database.md



Do not automatically delete historical records that are required for:



auditing

applications

appointments

analytics

compliance

Migrations



Create Alembic migrations for the implemented schema.



Migration requirements:



deterministic

reviewable

ordered

safe

tested



Do not manually edit the database instead of creating migrations.



Seed Data



Create a deterministic development seed for:



Nova Institute of Technology



The seed should include enough data to verify tenant isolation and future workflows.



At minimum:



college

users

courses

eligibility rules

scholarships

admission dates

documents

counselors

availability

FAQs

agent configuration



Use fictional data only.



Multiple Tenants



Seed at least one additional fictional college or tenant fixture specifically for isolation tests.



Example:



Nova Institute of Technology

Demo College B



The second tenant exists primarily to prove that tenant boundaries work.



Tenant Isolation Tests



Create automated tests proving:



College A cannot query College B courses.

College A cannot query College B leads.

College A cannot query College B appointments.

College A cannot query College B applications.

College A cannot query College B conversations.

College A cannot query College B knowledge.



Test both:



application/service-level filtering

database-level relationships/constraints where applicable

Migration Tests



Verify:



database can be created from migrations

migrations apply cleanly

schema matches expected models

seed data can be inserted

rollback behavior is safe where supported

Performance



Avoid obvious database performance problems.



Check:



indexes

relationship loading

N+1 patterns

large table queries

vector search readiness



Do not prematurely optimize.



Security



Verify:



no secrets in migrations

no real student data

tenant relationships are explicit

foreign keys are enforced

sensitive fields are not unnecessarily exposed

audit records do not contain credentials

Non-Goals



Do NOT implement in this task:



complete authentication flow

complete RBAC API

complete college CRUD API

agent implementation

RAG ingestion pipeline

voice system

frontend dashboard

appointment service logic

lead scoring service

application service

notification service



Those belong to later tasks.



Definition of Done



This task is complete only when:



\[ ] Database models implemented

\[ ] College tenant model implemented

\[ ] User/role model implemented

\[ ] Student model implemented

\[ ] Course model implemented

\[ ] Eligibility model implemented

\[ ] Scholarship model implemented

\[ ] Admission dates implemented

\[ ] Required documents implemented

\[ ] Counselor model implemented

\[ ] Counselor availability implemented

\[ ] Appointment model implemented

\[ ] Lead model implemented

\[ ] Lead score events implemented

\[ ] Application model implemented

\[ ] Application documents implemented

\[ ] Conversation model implemented

\[ ] Message model implemented

\[ ] Knowledge source implemented

\[ ] Knowledge chunk/vector model implemented

\[ ] Support ticket implemented

\[ ] Agent configuration implemented

\[ ] FAQ implemented

\[ ] Audit log implemented

\[ ] Relationships and foreign keys implemented

\[ ] Appropriate indexes implemented

\[ ] Appropriate unique constraints implemented

\[ ] Alembic migration created

\[ ] Migration tested

\[ ] Seed data created

\[ ] Multiple tenant fixtures exist

\[ ] Tenant isolation tests pass

\[ ] Database tests pass

\[ ] No real PII used

\[ ] No secrets committed

Required Agent Report



When finished, report:



Files created/modified.

Models implemented.

Migration name.

Seed data created.

Tenant isolation approach.

Tests run.

Test results.

Any schema decisions that required interpretation.

Any unresolved issues.



Do not modify unrelated files.



Do not implement future tasks.

