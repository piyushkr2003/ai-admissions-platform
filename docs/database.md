\# Database Specification



\## 1. Purpose



This document defines the database architecture for the AI Voice Admissions Platform.



The database must support:



\- Multiple colleges

\- Strict tenant isolation

\- Students and prospective students

\- Courses

\- Eligibility rules

\- Fees

\- Scholarships

\- Admission dates

\- Required documents

\- Counselors

\- Appointments

\- Leads

\- Applications

\- Conversations

\- Knowledge-base/RAG data

\- Agent configuration

\- FAQs

\- Support tickets

\- Audit logs

\- Analytics



The database must be designed for production use and future expansion.



\---



\# 2. Database Technology



Primary database:



```text

PostgreSQL



Vector search:



pgvector



PostgreSQL will store both structured application data and vector embeddings used by the college knowledge base.



The database must support:



Transactions

Foreign keys

Constraints

Indexes

JSONB where appropriate

Vector similarity search

Database migrations

Automated backups

Production monitoring

3\. Multi-Tenancy



The platform is multi-tenant.



Each college is a tenant.



Example:



College A

College B

College C



The same application code serves all colleges.



College-specific information must be stored against the appropriate college\_id.



Tenant-owned entities must contain:



college\_id



unless the entity is explicitly platform-wide.



3.1 Tenant Isolation



A user belonging to College A must never be able to:



retrieve College B leads

retrieve College B applications

retrieve College B conversations

retrieve College B appointments

retrieve College B knowledge

modify College B configuration

access College B analytics



Tenant filtering must be enforced in the backend service/repository layer.



Do not rely only on frontend filtering.



Where appropriate, PostgreSQL Row Level Security may also be used as an additional protection layer.



4\. Entity Overview



Main entities:



colleges

users

students

courses

course\_eligibility\_rules

scholarships

admission\_dates

required\_documents

counselors

counselor\_availability

appointments

leads

lead\_score\_events

applications

application\_documents

conversations

messages

knowledge\_sources

knowledge\_chunks

agent\_configs

faqs

support\_tickets

audit\_logs

5\. Colleges



Table:



colleges



Purpose:



Stores tenant-level college information.



Fields:



id UUID PRIMARY KEY

name VARCHAR(255) NOT NULL

slug VARCHAR(100) UNIQUE NOT NULL

description TEXT

logo\_url TEXT

website\_url TEXT

email VARCHAR(255)

phone VARCHAR(50)

address TEXT

city VARCHAR(100)

state VARCHAR(100)

country VARCHAR(100)

timezone VARCHAR(100) DEFAULT 'Asia/Kolkata'

default\_language VARCHAR(20) DEFAULT 'en'

supported\_languages JSONB

status VARCHAR(30) DEFAULT 'active'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Status values:



active

inactive

suspended



Indexes:



slug

status

6\. Users



Table:



users



Purpose:



Stores platform and college staff authentication accounts.



Fields:



id UUID PRIMARY KEY

college\_id UUID NULL REFERENCES colleges(id)

email VARCHAR(255) UNIQUE NOT NULL

password\_hash TEXT

full\_name VARCHAR(255) NOT NULL

role VARCHAR(50) NOT NULL

is\_active BOOLEAN DEFAULT TRUE

last\_login\_at TIMESTAMP WITH TIME ZONE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Roles:



platform\_admin

college\_admin

admissions\_staff

counselor



Important:



college\_id may be NULL only for platform-level administrators.



College users must always have a valid college\_id.



Indexes:



college\_id

email

role

7\. Students



Table:



students



Purpose:



Stores prospective student information collected through conversations, applications, forms, or other admission interactions.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

full\_name VARCHAR(255)

email VARCHAR(255)

phone VARCHAR(50)

date\_of\_birth DATE

city VARCHAR(100)

state VARCHAR(100)

country VARCHAR(100)

qualification VARCHAR(255)

qualification\_score NUMERIC(6,2)

entrance\_exam VARCHAR(255)

entrance\_exam\_score NUMERIC(8,2)

budget\_range VARCHAR(100)

hostel\_interest BOOLEAN

scholarship\_interest BOOLEAN

parent\_name VARCHAR(255)

parent\_phone VARCHAR(50)

consent\_status VARCHAR(50)

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Consent values:



unknown

granted

withdrawn



Indexes:



college\_id

email

phone

8\. Courses



Table:



courses



Purpose:



Stores structured course/program information.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

name VARCHAR(255) NOT NULL

code VARCHAR(100)

degree\_type VARCHAR(100)

department VARCHAR(255)

description TEXT

duration\_years NUMERIC(4,1)

total\_seats INTEGER

annual\_fee NUMERIC(12,2)

application\_fee NUMERIC(12,2)

eligibility\_summary TEXT

admission\_process TEXT

placement\_summary TEXT

hostel\_available BOOLEAN DEFAULT FALSE

status VARCHAR(30) DEFAULT 'active'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Each course belongs to exactly one college.



Indexes:



college\_id

college\_id + status

college\_id + name

9\. Course Eligibility Rules



Eligibility must not be hardcoded into the AI prompt.



Table:



course\_eligibility\_rules



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

course\_id UUID NOT NULL REFERENCES courses(id)

minimum\_percentage NUMERIC(6,2)

required\_qualification VARCHAR(255)

required\_subjects JSONB

entrance\_exam\_required BOOLEAN DEFAULT FALSE

entrance\_exam\_name VARCHAR(255)

minimum\_entrance\_score NUMERIC(8,2)

additional\_conditions JSONB

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



The eligibility service evaluates these structured rules.



The AI explains the result but does not independently invent eligibility criteria.



10\. Scholarships



Table:



scholarships



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

name VARCHAR(255) NOT NULL

description TEXT

eligibility\_criteria TEXT

amount NUMERIC(12,2)

percentage NUMERIC(5,2)

application\_required BOOLEAN DEFAULT FALSE

deadline TIMESTAMP WITH TIME ZONE

status VARCHAR(30) DEFAULT 'active'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Indexes:



college\_id

college\_id + status

11\. Admission Dates



Table:



admission\_dates



Purpose:



Stores important admission-related dates.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

course\_id UUID NULL REFERENCES courses(id)

title VARCHAR(255) NOT NULL

description TEXT

date TIMESTAMP WITH TIME ZONE NOT NULL

date\_type VARCHAR(100)

status VARCHAR(30) DEFAULT 'active'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Examples:



application\_open

application\_deadline

entrance\_exam

counselling

document\_verification

admission\_deadline

12\. Required Documents



Table:



required\_documents



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

course\_id UUID NULL REFERENCES courses(id)

name VARCHAR(255) NOT NULL

description TEXT

mandatory BOOLEAN DEFAULT TRUE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Examples:



10th marksheet

12th marksheet

Transfer certificate

Government ID

Passport photographs

Entrance examination scorecard

13\. Counselors



Table:



counselors



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

user\_id UUID NULL REFERENCES users(id)

name VARCHAR(255) NOT NULL

email VARCHAR(255)

phone VARCHAR(50)

specialization VARCHAR(255)

active BOOLEAN DEFAULT TRUE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



A counselor belongs to one college.



14\. Counselor Availability



Table:



counselor\_availability



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

counselor\_id UUID NOT NULL REFERENCES counselors(id)

day\_of\_week INTEGER NOT NULL

start\_time TIME NOT NULL

end\_time TIME NOT NULL

timezone VARCHAR(100) DEFAULT 'Asia/Kolkata'

active BOOLEAN DEFAULT TRUE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



day\_of\_week:



0 = Monday

1 = Tuesday

2 = Wednesday

3 = Thursday

4 = Friday

5 = Saturday

6 = Sunday

15\. Appointments



Table:



appointments



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

student\_id UUID NOT NULL REFERENCES students(id)

counselor\_id UUID NOT NULL REFERENCES counselors(id)

course\_id UUID NULL REFERENCES courses(id)

start\_time TIMESTAMP WITH TIME ZONE NOT NULL

end\_time TIMESTAMP WITH TIME ZONE NOT NULL

status VARCHAR(50) DEFAULT 'scheduled'

meeting\_type VARCHAR(50) DEFAULT 'phone'

meeting\_link TEXT

notes TEXT

source VARCHAR(50) DEFAULT 'ai\_agent'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Status:



scheduled

completed

cancelled

rescheduled

no\_show



Source:



ai\_agent

admin

student



Critical requirement:



The application must prevent double-booking of the same counselor/time slot.



Booking must be transactional.



Appointment creation must verify:



Counselor belongs to the same college.

Student belongs to the same college.

Course belongs to the same college if provided.

Requested slot is valid.

Counselor is available.

No conflicting appointment exists.

Appointment is created atomically.

16\. Leads



Table:



leads



Purpose:



Stores admission prospects and their sales/admission intent.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

student\_id UUID NOT NULL REFERENCES students(id)

course\_id UUID NULL REFERENCES courses(id)

status VARCHAR(50) DEFAULT 'new'

intent VARCHAR(50)

lead\_score INTEGER DEFAULT 0

lead\_temperature VARCHAR(20)

source VARCHAR(50) DEFAULT 'voice\_agent'

notes TEXT

next\_action TEXT

last\_contacted\_at TIMESTAMP WITH TIME ZONE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Lead temperature:



hot

warm

cold



Lead status:



new

contacted

qualified

appointment\_booked

application\_started

converted

lost



Score range:



0–100

17\. Lead Score Events



Table:



lead\_score\_events



Purpose:



Makes lead scoring explainable.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

lead\_id UUID NOT NULL REFERENCES leads(id)

event\_type VARCHAR(100) NOT NULL

points INTEGER NOT NULL

reason TEXT

created\_at TIMESTAMP WITH TIME ZONE



Example events:



course\_identified +20

eligibility\_confirmed +20

fee\_discussed +10

scholarship\_interest +10

appointment\_requested +20

application\_started +30



Scores must be calculated by backend logic.



The AI must not directly write arbitrary lead scores.



18\. Applications



Table:



applications



Purpose:



Stores admission applications created through the AI-assisted application workflow or administrative systems.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

student\_id UUID NOT NULL REFERENCES students(id)

course\_id UUID NOT NULL REFERENCES courses(id)

application\_number VARCHAR(100)

status VARCHAR(50) DEFAULT 'draft'

completion\_percentage INTEGER DEFAULT 0

submitted\_at TIMESTAMP WITH TIME ZONE

reviewed\_at TIMESTAMP WITH TIME ZONE

notes TEXT

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Application status:



draft

in\_progress

submitted

under\_review

documents\_pending

approved

rejected

withdrawn



The AI may create a draft application after collecting sufficient information.



The AI must never claim that an application has been officially submitted unless the backend confirms submission.



19\. Application Documents



Table:



application\_documents



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

application\_id UUID NOT NULL REFERENCES applications(id)

document\_type VARCHAR(100) NOT NULL

file\_name VARCHAR(255)

file\_url TEXT

status VARCHAR(50) DEFAULT 'pending'

verified\_at TIMESTAMP WITH TIME ZONE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Status:



pending

uploaded

verified

rejected



The database should store metadata and secure references to files.



Actual files should use secure object storage rather than database blobs unless there is a specific reason otherwise.



20\. Conversations



Table:



conversations



Purpose:



Stores AI voice/text conversation sessions.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

student\_id UUID NULL REFERENCES students(id)

channel VARCHAR(50) NOT NULL

session\_id VARCHAR(255)

status VARCHAR(50) DEFAULT 'active'

started\_at TIMESTAMP WITH TIME ZONE

ended\_at TIMESTAMP WITH TIME ZONE

duration\_seconds INTEGER

summary TEXT

intent VARCHAR(100)

outcome VARCHAR(100)

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Channels:



voice

web\_voice

phone

chat



Conversation status:



active

completed

failed

escalated

21\. Messages



Table:



messages



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

conversation\_id UUID NOT NULL REFERENCES conversations(id)

sender\_type VARCHAR(50) NOT NULL

content TEXT

audio\_url TEXT

transcript\_confidence NUMERIC(5,4)

tool\_name VARCHAR(100)

tool\_arguments JSONB

tool\_result JSONB

created\_at TIMESTAMP WITH TIME ZONE



Sender types:



student

parent

ai

system

counselor



Sensitive data should not be logged unnecessarily.



Audio retention must follow the platform's configured privacy policy.



22\. Knowledge Sources



Table:



knowledge\_sources



Purpose:



Tracks documents and external sources used to build a college knowledge base.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

name VARCHAR(255) NOT NULL

source\_type VARCHAR(50) NOT NULL

source\_url TEXT

file\_url TEXT

status VARCHAR(50) DEFAULT 'pending'

version VARCHAR(100)

content\_hash VARCHAR(255)

last\_synced\_at TIMESTAMP WITH TIME ZONE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Source types:



pdf

website

csv

xlsx

faq

manual

text



Status:



pending

processing

ready

failed

archived

23\. Knowledge Chunks



Table:



knowledge\_chunks



Purpose:



Stores chunked knowledge-base content and vector embeddings.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

knowledge\_source\_id UUID NOT NULL REFERENCES knowledge\_sources(id)

content TEXT NOT NULL

chunk\_index INTEGER

metadata JSONB

embedding VECTOR

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



The exact vector dimension must match the embedding model selected by the platform.



Vector indexes should be added according to the selected pgvector indexing strategy.



Every retrieval query must include tenant filtering:



college\_id = current\_college\_id



A vector similarity search must never search across colleges.



24\. Agent Configurations



Table:



agent\_configs



Purpose:



Stores college-specific AI agent configuration.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

agent\_name VARCHAR(255)

system\_prompt TEXT

personality VARCHAR(100)

voice\_provider VARCHAR(100)

voice\_id VARCHAR(255)

default\_language VARCHAR(20)

supported\_languages JSONB

greeting\_message TEXT

fallback\_message TEXT

escalation\_message TEXT

enabled\_tools JSONB

lead\_scoring\_config JSONB

business\_hours JSONB

active BOOLEAN DEFAULT TRUE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



Important:



The system prompt must not contain all college facts manually.



College-specific factual information should primarily come from:



Structured database data

Knowledge retrieval

Configured tools



The agent configuration controls behavior and presentation.



25\. FAQs



Table:



faqs



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

question TEXT NOT NULL

answer TEXT NOT NULL

category VARCHAR(100)

active BOOLEAN DEFAULT TRUE

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE



FAQs can be used as a structured knowledge source.



26\. Support Tickets



Table:



support\_tickets



Purpose:



Stores issues that require human assistance.



Fields:



id UUID PRIMARY KEY

college\_id UUID NOT NULL REFERENCES colleges(id)

student\_id UUID NULL REFERENCES students(id)

conversation\_id UUID NULL REFERENCES conversations(id)

assigned\_to UUID NULL REFERENCES users(id)

category VARCHAR(100)

subject VARCHAR(255) NOT NULL

description TEXT

priority VARCHAR(30) DEFAULT 'normal'

status VARCHAR(50) DEFAULT 'open'

created\_at TIMESTAMP WITH TIME ZONE

updated\_at TIMESTAMP WITH TIME ZONE

resolved\_at TIMESTAMP WITH TIME ZONE



Priority:



low

normal

high

urgent



Status:



open

assigned

in\_progress

resolved

closed

27\. Audit Logs



Table:



audit\_logs



Purpose:



Records important administrative and system actions.



Fields:



id UUID PRIMARY KEY

college\_id UUID NULL REFERENCES colleges(id)

user\_id UUID NULL REFERENCES users(id)

action VARCHAR(100) NOT NULL

entity\_type VARCHAR(100)

entity\_id UUID

metadata JSONB

ip\_address INET

created\_at TIMESTAMP WITH TIME ZONE



Examples:



college\_created

course\_updated

scholarship\_updated

appointment\_created

appointment\_cancelled

lead\_updated

application\_created

application\_submitted

agent\_config\_updated

knowledge\_source\_uploaded

user\_created



Audit logs should be append-only.



28\. Relationships



Main relationships:



college

&#x20; ├── users

&#x20; ├── students

&#x20; ├── courses

&#x20; ├── scholarships

&#x20; ├── admission\_dates

&#x20; ├── required\_documents

&#x20; ├── counselors

&#x20; ├── leads

&#x20; ├── applications

&#x20; ├── conversations

&#x20; ├── knowledge\_sources

&#x20; ├── knowledge\_chunks

&#x20; ├── agent\_configs

&#x20; ├── faqs

&#x20; ├── support\_tickets

&#x20; └── audit\_logs



Student relationships:



student

&#x20; ├── leads

&#x20; ├── appointments

&#x20; ├── applications

&#x20; └── conversations



Course relationships:



course

&#x20; ├── eligibility\_rules

&#x20; ├── admission\_dates

&#x20; ├── required\_documents

&#x20; ├── leads

&#x20; └── applications



Counselor relationships:



counselor

&#x20; ├── availability

&#x20; └── appointments



Conversation relationships:



conversation

&#x20; ├── messages

&#x20; └── support\_tickets



Application relationships:



application

&#x20; └── application\_documents

29\. Foreign Key Rules



Foreign keys must be used wherever relationships exist.



Tenant-owned records must reference the appropriate college.



The backend must validate that related records belong to the same college before performing operations.



Example:



A lead cannot reference:



College A lead

\+

College B student



A booking cannot reference:



College A appointment

\+

College B counselor



Cross-tenant references must be rejected.



30\. Uniqueness Constraints



Use appropriate uniqueness constraints.



Examples:



colleges.slug

users.email



Recommended tenant-scoped uniqueness:



college\_id + course.code

college\_id + counselor.email

college\_id + application.application\_number



Do not use global uniqueness where the business requirement is tenant-scoped.



31\. Indexing



Important indexes should include:



college\_id

college\_id + status

college\_id + created\_at

college\_id + updated\_at

student\_id

course\_id

counselor\_id

appointment start\_time

lead\_score

lead\_temperature

application status

conversation created\_at

knowledge\_source\_id



Indexes should be created based on actual query patterns.



Do not add unnecessary indexes to every column.



32\. Vector Search



Use pgvector for semantic retrieval.



Basic retrieval flow:



User Question

&#x20;     ↓

Create Query Embedding

&#x20;     ↓

Filter by college\_id

&#x20;     ↓

Vector Similarity Search

&#x20;     ↓

Retrieve Relevant Chunks

&#x20;     ↓

Optional Reranking

&#x20;     ↓

LLM Context

&#x20;     ↓

Grounded Answer



Critical rule:



Tenant filtering must happen before or as part of vector retrieval.



Never retrieve all-college chunks and filter afterward in application code.



33\. Structured Data vs RAG



Use structured database data for facts that require deterministic answers.



Examples:



course name

course fee

duration

eligibility

application deadline

scholarship amount

counselor availability

appointment slots

application status

lead score



Use RAG for unstructured information.



Examples:



college handbook

course brochure

FAQ documents

admission guidelines

policy documents

website content

hostel information

placement documents



The AI should use the appropriate source.



For example:



"How much is B.Tech CSE?"



should prefer structured course/fee data.



Question:



"What is the hostel policy?"



may use the knowledge base.



34\. Appointment Transaction Requirements



Appointment booking must be implemented as a backend transaction.



Flow:



Check counselor

&#x20;     ↓

Check college ownership

&#x20;     ↓

Check availability

&#x20;     ↓

Check existing appointments

&#x20;     ↓

Create appointment

&#x20;     ↓

Commit transaction

&#x20;     ↓

Return confirmed appointment



If booking fails, the AI must not claim success.



Example:



Backend: booking failed

AI: "I couldn't complete that booking. Let me try another available slot."



Never:



Backend: booking failed

AI: "Your appointment is confirmed."

35\. Lead Scoring Requirements



Lead scoring must be deterministic and explainable.



Example scoring:



Course identified            +20

Eligibility confirmed       +20

Fees discussed              +10

Scholarship interest        +10

Appointment requested       +20

Application started         +30



Maximum score:



100



The final score must be normalized or capped at 100.



Temperature can be derived from configurable thresholds.



Example:



0–39   = cold

40–69  = warm

70–100 = hot



These thresholds must be configurable.



Each score change should create a lead\_score\_events record.



36\. Application Requirements



The application system must support:



Draft applications

Application progress

Required document checklist

Document upload metadata

Application submission

Application status

Application history



The AI may assist with application completion.



The AI must not invent missing student information.



If required information is missing, it should ask the student.



37\. Data Privacy



The system may handle personal information.



Minimum requirements:



Do not log passwords.

Do not expose API keys.

Avoid unnecessary storage of sensitive information.

Restrict staff access using RBAC.

Use encrypted connections.

Protect file storage.

Apply tenant isolation.

Provide appropriate consent handling.

Support data retention policies.

Keep audit logs for sensitive administrative actions.

Do not expose student information to unauthorized users.



Production deployment must use secure secrets management.



38\. Environment Separation



Use separate environments:



development

test

staging

production



Each environment must have separate:



Database

Credentials

Secrets

API keys

Storage

Configuration



Never use production student data in development.



The demo environment must use fictional data.



39\. Seed Data



The project must include seed data for a fictional college.



Demo college:



Nova Institute of Technology



The demo dataset should include:



B.Tech Computer Science and Engineering

B.Tech Artificial Intelligence and Machine Learning

BCA

MCA

MBA



Seed data should also include:



Course fees

Eligibility

Scholarships

Admission dates

Required documents

Counselors

Counselor availability

FAQs

Agent configuration

Sample students

Sample leads

Sample appointments

Sample applications

Sample knowledge-base documents/chunks



All demo information must be clearly fictional.



Never use real student personal information in seed data.



40\. Database Migrations



Use a proper migration system.



Recommended:



Alembic



All schema changes must be represented by migrations.



Do not manually modify production databases.



Migration workflow:



Create migration

&#x20;     ↓

Review migration

&#x20;     ↓

Run tests

&#x20;     ↓

Apply to development

&#x20;     ↓

Apply to staging

&#x20;     ↓

Validate

&#x20;     ↓

Apply to production

41\. Repository Organization



Database-related code should be separated from API routes.



Recommended backend structure:



backend/

&#x20; app/

&#x20;   api/

&#x20;   models/

&#x20;   schemas/

&#x20;   repositories/

&#x20;   services/

&#x20;   db/

&#x20;     session.py

&#x20;     migrations/

&#x20;   agents/

&#x20;   rag/

&#x20;   core/



Responsibilities:



models/

&#x20;   Database models



schemas/

&#x20;   API validation models



repositories/

&#x20;   Database queries



services/

&#x20;   Business logic



api/

&#x20;   HTTP endpoints



agents/

&#x20;   AI agent logic and tools



rag/

&#x20;   Knowledge retrieval



Do not put complex database logic directly inside route handlers.



42\. Service and Repository Layer



Use a clear separation:



API

&#x20;↓

Service

&#x20;↓

Repository

&#x20;↓

Database



Example:



POST /appointments

&#x20;       ↓

AppointmentService

&#x20;       ↓

AppointmentRepository

&#x20;       ↓

PostgreSQL



Services enforce business rules.



Repositories handle database operations.



43\. Tenant Context



Every authenticated college request should have a tenant context.



Example:



current\_user

&#x20;   ↓

college\_id

&#x20;   ↓

service

&#x20;   ↓

repository

&#x20;   ↓

tenant-filtered query



Never accept an arbitrary college\_id from the client and trust it.



The backend must derive the authorized college from the authenticated identity/context.



Platform administrators may have controlled cross-tenant access according to their role.



44\. Background Jobs



Background jobs may be used for:



Knowledge ingestion

Document parsing

Embedding generation

Website synchronization

Conversation summarization

Analytics aggregation

Notifications



Long-running operations should not block voice conversations unnecessarily.



Example:



Upload PDF

&#x20;   ↓

Create knowledge source

&#x20;   ↓

Queue processing job

&#x20;   ↓

Parse document

&#x20;   ↓

Chunk document

&#x20;   ↓

Generate embeddings

&#x20;   ↓

Store vectors

&#x20;   ↓

Mark source ready

45\. Analytics



Analytics should be derived from transactional data.



Important metrics:



total calls

total conversations

new leads

hot leads

warm leads

cold leads

appointments booked

applications started

applications submitted

applications converted

AI resolution rate

escalation rate

appointment conversion rate

application conversion rate

average conversation duration

query categories

peak conversation times



Analytics must always be tenant-aware.



College A analytics must never include College B data.



46\. Production Requirements



The database layer must support:



Connection pooling

Transactions

Timeouts

Retry-safe operations

Health checks

Backups

Restore testing

Migration management

Monitoring

Error logging

Slow query monitoring

Proper indexes

Secure credentials

Tenant isolation

Data retention policies



Database credentials must never be hardcoded.



47\. Testing Requirements



Database tests must cover:



Tenant isolation



Verify that:



College A cannot access College B data.

Appointment booking



Test:



valid booking

invalid counselor

invalid student

cross-tenant booking

double booking

cancelled appointment

rescheduling

Lead scoring



Test:



individual score events

combined score

score cap

temperature calculation

Applications



Test:



draft creation

missing information

document status

submission

status updates

cross-tenant access

Knowledge retrieval



Test:



College A query

College B query

cross-tenant retrieval prevention

empty retrieval

Authentication



Test:



platform admin

college admin

admissions staff

counselor

unauthorized user

48\. Demo College



Use:



Nova Institute of Technology



as the initial fictional tenant.



Initial courses:



B.Tech Computer Science and Engineering

B.Tech Artificial Intelligence and Machine Learning

BCA

MCA

MBA



The demo should demonstrate the complete admission workflow:



Student asks about course

&#x20;       ↓

AI provides course information

&#x20;       ↓

AI asks qualification

&#x20;       ↓

Eligibility service checks rules

&#x20;       ↓

AI explains eligibility

&#x20;       ↓

AI explains fees

&#x20;       ↓

AI explains scholarships

&#x20;       ↓

Student asks for counselor

&#x20;       ↓

Availability service checks slots

&#x20;       ↓

Student selects slot

&#x20;       ↓

Appointment is created

&#x20;       ↓

Lead is created/updated

&#x20;       ↓

Lead score calculated

&#x20;       ↓

Student asks about documents

&#x20;       ↓

AI retrieves document requirements

&#x20;       ↓

Student wants to apply

&#x20;       ↓

Draft application created

&#x20;       ↓

Dashboard shows lead

&#x20;       ↓

Dashboard shows appointment

&#x20;       ↓

Dashboard shows application

49\. Non-Goals



The initial product does NOT include post-admission student services.



Do not build the following into the initial scope:



orientation information

hostel check-in

campus navigation

academic calendar

exam information

department contacts

transport services

general post-admission student services



Hostel information may still be provided as a pre-admission decision-support topic.



The platform is focused on:



prospective students

parents

admissions

lead generation

counseling

appointments

application assistance

pre-admission support

50\. Final Database Principle



The database must make the platform:



Multi-tenant

Secure

Deterministic

Auditable

Scalable

AI-ready

Production-ready



The most important architectural rule is:



Platform logic is shared.

College data is isolated.

AI behavior is configurable.

Structured facts come from structured data.

Unstructured information comes from RAG.

Backend tools perform real actions.

Every tenant-owned operation is tenant-aware.



The AI must never fabricate college information, appointment confirmations, application submissions, eligibility decisions, fees, scholarships, or other structured facts.



The database is the source of truth for transactional information, while the knowledge base is the source for approved unstructured college information.







