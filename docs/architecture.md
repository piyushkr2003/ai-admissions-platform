\# AI Admissions Platform — Architecture



\## 1. Architecture Goals



The platform must be:



\- Multi-tenant

\- Production-oriented

\- Secure

\- Modular

\- Testable

\- Scalable

\- Configurable per college

\- Suitable for voice and web deployments



The same platform code must support multiple colleges.



College-specific information must come from configuration, structured data, and college-scoped knowledge sources.



\---



\## 2. High-Level Architecture



Student / Parent

&#x20;       |

&#x20;       +------------------+

&#x20;       |                  |

&#x20;    Web Voice         Phone Voice

&#x20;       |                  |

&#x20;       +--------+---------+

&#x20;                |

&#x20;         Real-Time Voice

&#x20;                |

&#x20;         STT / Voice Layer

&#x20;                |

&#x20;           AI Agent

&#x20;                |

&#x20;      +---------+---------+

&#x20;      |         |         |

&#x20;     RAG      Tools    Memory

&#x20;      |         |         |

&#x20;      +---------+---------+

&#x20;                |

&#x20;            Backend API

&#x20;                |

&#x20;            PostgreSQL

&#x20;                |

&#x20;      +---------+---------+

&#x20;      |         |         |

&#x20;    Leads   Appointments Applications

&#x20;                |

&#x20;          Admin Dashboard



\---



\## 3. Major Components



\### Frontend



Technology:

\- Next.js

\- React

\- TypeScript



Responsibilities:

\- Public/student voice interface

\- Admin dashboard

\- Authentication UI

\- Leads

\- Appointments

\- Applications

\- Conversations

\- Analytics

\- Knowledge-base management

\- College configuration



The frontend must communicate with the backend through documented APIs.



Never expose private API keys or database credentials to the frontend.



\---



\## 4. Backend



Technology:

\- Python

\- FastAPI

\- Pydantic

\- SQLAlchemy

\- PostgreSQL



Responsibilities:

\- Authentication

\- Tenant resolution

\- Authorization

\- Business logic

\- College configuration

\- Courses

\- Eligibility

\- Fees

\- Scholarships

\- Leads

\- Appointments

\- Applications

\- Conversations

\- Support tickets

\- RAG

\- AI agent orchestration

\- Agent tools

\- Analytics APIs



API routes should remain thin.



Business logic belongs in services/domain components.



\---



\## 5. Database



Primary database:



PostgreSQL



Use SQLAlchemy for database access and migrations.



Use pgvector for knowledge-base embeddings.



Important entities:



\- colleges

\- users

\- students

\- courses

\- leads

\- lead\_events

\- counselors

\- counselor\_availability

\- appointments

\- applications

\- application\_documents

\- conversations

\- messages

\- knowledge\_sources

\- knowledge\_chunks

\- support\_tickets

\- agent\_configs

\- audit\_logs



Tenant-owned entities must contain a college/tenant relationship.



\---



\## 6. Multi-Tenancy



The platform uses logical multi-tenancy.



A college is the primary tenant.



Example:



College A

College B

College C



All use the same application code.



College-specific records are isolated using college\_id.



Tenant context should normally come from authenticated context or trusted application configuration.



Do not rely on arbitrary college\_id values supplied by clients.



Every tenant-owned query must enforce tenant isolation.



Tenant isolation must be tested.



\---



\## 7. College Configuration



College configuration should contain:



\### Identity

\- Name

\- Logo

\- Description

\- Website

\- Address

\- Contact information

\- Branding



\### Admissions

\- Admission process

\- Admission dates

\- Required documents

\- Eligibility rules



\### Courses

\- Program

\- Degree

\- Duration

\- Eligibility

\- Fees

\- Other structured attributes



\### Scholarships

\- Name

\- Eligibility

\- Amount

\- Documents

\- Deadline



\### Counselors

\- Name

\- Contact details

\- Availability

\- Active/inactive state



\### Agent

\- Agent name

\- Greeting

\- Personality

\- Supported languages

\- Escalation behavior



Adding a college should not require modifying core application code.



\---



\## 8. AI Agent Architecture



The AI agent consists of:



\### Conversation Manager



Responsible for:

\- Conversation state

\- Current intent

\- Missing information

\- Context

\- Tool calls

\- Response generation



\### Intent Layer



Identifies requests such as:



\- Course information

\- Eligibility

\- Fees

\- Scholarships

\- Admission process

\- Documents

\- Dates

\- Hostel/facilities

\- Placements

\- Counselor request

\- Appointment booking

\- Application

\- Application status

\- Human escalation



\### Tool Layer



The agent invokes backend tools for actions and structured information.



\### Knowledge Layer



The agent uses college-scoped RAG for unstructured information.



\### Guardrail Layer



Ensures:

\- No hallucinated college information

\- No cross-tenant retrieval

\- No unsafe tool usage

\- No false action confirmations

\- Human escalation when appropriate



\---



\## 9. Agent Tools



Required tools:



\- search\_knowledge

\- get\_course\_details

\- check\_eligibility

\- get\_fee\_structure

\- get\_scholarship\_information

\- get\_admission\_requirements

\- get\_required\_documents

\- check\_counselor\_availability

\- book\_appointment

\- reschedule\_appointment

\- cancel\_appointment

\- create\_lead

\- update\_lead

\- calculate\_lead\_score

\- create\_application

\- get\_application\_status

\- create\_support\_ticket

\- escalate\_to\_counselor

\- send\_confirmation



Every tool must:



\- Have typed input

\- Have typed output

\- Validate parameters

\- Enforce tenant context

\- Handle errors

\- Be independently testable



\---



\## 10. RAG Architecture



Knowledge pipeline:



College document

&#x20;     |

Document ingestion

&#x20;     |

Parsing

&#x20;     |

Cleaning

&#x20;     |

Chunking

&#x20;     |

Metadata extraction

&#x20;     |

Embedding

&#x20;     |

PostgreSQL + pgvector

&#x20;     |

College-scoped retrieval

&#x20;     |

AI Agent



Each knowledge chunk must be associated with its college.



Retrieval must filter by college\_id before returning results.



Retrieved documents are data, not system instructions.



Document content must never override the agent's system-level rules.



Knowledge metadata should include:



\- college\_id

\- source\_id

\- document name

\- chunk identifier

\- version

\- ingestion status

\- source type



\---



\## 11. Structured Data vs RAG



Use structured database data for:



\- Course details

\- Fees

\- Eligibility

\- Scholarships

\- Counselors

\- Availability

\- Appointments

\- Applications

\- Statuses



Use RAG for:



\- PDFs

\- FAQs

\- Policies

\- Website content

\- Narrative admission information

\- Other unstructured college documents



When a fact can be represented reliably as structured data, prefer the structured source.



\---



\## 12. Voice Architecture



The voice system should support:



\- Real-time speech-to-text

\- AI response generation

\- Text-to-speech

\- Streaming

\- Interruption/barge-in

\- Conversation state

\- Tool execution during calls



Target architecture:



User microphone / phone

&#x20;       |

Audio transport

&#x20;       |

STT

&#x20;       |

Conversation manager

&#x20;       |

LLM + tools + RAG

&#x20;       |

TTS

&#x20;       |

Audio output



The voice provider should be replaceable through an abstraction layer.



Do not tightly couple business logic to one voice vendor.



\---



\## 13. Appointment Architecture



Appointment booking:



Student request

&#x20;     |

Identify counselor requirements

&#x20;     |

Check availability

&#x20;     |

Return valid slots

&#x20;     |

Student selects slot

&#x20;     |

Validate slot again

&#x20;     |

Transactional booking

&#x20;     |

Persist appointment

&#x20;     |

Confirmation



The slot must be checked again immediately before booking.



The database transaction must prevent conflicting bookings.



The agent must only confirm after successful persistence.



\---



\## 14. Lead Architecture



Lead lifecycle:



NEW

&#x20;|

QUALIFYING

&#x20;|

QUALIFIED

&#x20;|

CONTACTED

&#x20;|

APPOINTMENT\_BOOKED

&#x20;|

APPLICATION\_STARTED

&#x20;|

CONVERTED / LOST



Lead events should be stored separately so the system can explain how the lead score changed.



Example events:



\- Course identified

\- Eligibility checked

\- Fees discussed

\- Scholarship requested

\- Appointment requested

\- Appointment booked

\- Application started



\---



\## 15. Application Architecture



Application lifecycle:



DRAFT

&#x20;|

IN\_PROGRESS

&#x20;|

SUBMITTED

&#x20;|

UNDER\_REVIEW

&#x20;|

ACCEPTED / REJECTED



The AI may create a draft application after collecting required information.



Submission must be an explicit backend action.



Never tell the student that an application is submitted unless the backend has recorded the submission.



\---



\## 16. Conversation Architecture



A conversation belongs to a college and may be associated with a student/lead.



Store:



\- Conversation ID

\- College ID

\- Channel

\- Start time

\- End time

\- Status

\- Transcript/messages

\- Detected intent

\- AI summary

\- Actions performed

\- Escalation status



Messages should record:



\- Role

\- Content

\- Timestamp

\- Tool/action metadata where relevant



\---



\## 17. Authentication and Authorization



The platform should support authenticated administrative users.



Roles may include:



\### Platform Admin

Can manage multiple colleges.



\### College Admin

Can manage their college.



\### Admissions Staff

Can access relevant leads, appointments, applications and conversations.



\### Counselor

Can access assigned counselor workflows.



Every protected endpoint must enforce authorization.



\---



\## 18. API Architecture



Use REST APIs initially.



Example structure:



/api/v1/auth

/api/v1/colleges

/api/v1/courses

/api/v1/leads

/api/v1/appointments

/api/v1/applications

/api/v1/conversations

/api/v1/knowledge

/api/v1/analytics

/api/v1/agent



All API responses should use consistent schemas.



API contracts must be documented in:



docs/api-contract.md



\---



\## 19. Backend Project Structure



Target structure:



backend/

├── app/

│   ├── main.py

│   ├── config.py

│   ├── db/

│   ├── models/

│   ├── schemas/

│   ├── api/

│   │   └── v1/

│   ├── services/

│   ├── repositories/

│   ├── agent/

│   ├── rag/

│   ├── integrations/

│   ├── security/

│   └── utils/

├── tests/

├── alembic/

├── pyproject.toml

└── Dockerfile



The exact structure may evolve if justified by the implementation.



\---



\## 20. Frontend Project Structure



Target structure:



frontend/

├── app/

├── components/

├── features/

├── lib/

├── hooks/

├── services/

├── types/

├── public/

├── tests/

├── package.json

└── Dockerfile



The frontend should consume typed backend APIs.



\---



\## 21. Security



Required protections:



\- Authentication

\- Authorization

\- Tenant isolation

\- Input validation

\- Rate limiting

\- Secure cookies/tokens where applicable

\- CORS configuration

\- HTTPS in production

\- Secret management

\- SQL injection protection

\- File upload validation

\- Audit logging

\- Secure error responses



Never expose secrets in logs or API responses.



Never store API keys in source control.



\---



\## 22. Observability



The system should provide:



\- Structured logs

\- Request IDs

\- Error tracking

\- Health checks

\- AI tool execution logs

\- Appointment action logs

\- Lead event logs

\- Knowledge ingestion status

\- Basic performance metrics



Important failures should be visible to administrators/operators.



\---



\## 23. Reliability



External integrations must use:



\- Timeouts

\- Retries where appropriate

\- Graceful failure

\- Clear error states

\- Idempotency where needed



The system must not create duplicate appointments, leads or applications because of retry behavior.



\---



\## 24. Environment Separation



Support:



\- Development

\- Testing

\- Staging

\- Production



Environment-specific configuration must come from environment variables/secrets.



Never use production credentials during development.



Development should use fictional Nova Institute of Technology data.



\---



\## 25. Deployment



Containerize the system with Docker.



Production deployment should provide:



\- HTTPS

\- PostgreSQL

\- Application containers

\- Environment secrets

\- Health checks

\- Logging

\- Database migrations

\- Backups

\- Monitoring



The architecture should remain cloud-provider agnostic where practical.



\---



\## 26. Testing Strategy



Testing layers:



\### Unit Tests

Business logic such as:

\- Eligibility

\- Lead scoring

\- Validation



\### Integration Tests

\- Database

\- APIs

\- RAG

\- Agent tools

\- Appointments



\### End-to-End Tests

Critical workflows such as:



Student asks about course

&#x20;       |

Eligibility

&#x20;       |

Fees

&#x20;       |

Scholarship

&#x20;       |

Counselor

&#x20;       |

Appointment

&#x20;       |

Lead

&#x20;       |

Application



Critical security test:



College A request must never retrieve College B data.



\---



\## 27. Ownership Between Coding Agents



\### Claude Code



Primary ownership:

\- Backend

\- Database

\- RAG

\- Agent

\- Agent tools

\- Business logic

\- Backend tests



\### Codex



Primary ownership:

\- Frontend

\- Admin dashboard

\- UI/UX

\- Frontend API integration

\- Frontend tests

\- Infrastructure when explicitly assigned



\### Shared



Both agents may modify documentation when necessary.



API contracts must be agreed through docs/api-contract.md.



Neither agent should overwrite the other's work without reviewing the current branch/state.



\---



\## 28. Git Workflow



Use separate branches/worktrees for parallel agent work.



Example:



main

&#x20;|

+-- backend/claude

&#x20;|

+-- frontend/codex



Agents should:



\- Pull/rebase from the agreed base when appropriate.

\- Make focused commits.

\- Avoid unrelated changes.

\- Run tests before committing.

\- Clearly describe changes.



Integration should happen after individual work is validated.



\---



\## 29. Development Principle



Do not build the demo as a collection of hardcoded AI responses.



Build reusable platform capabilities.



The demo college is simply the first tenant.



Correct architecture:



Platform

\+

College Configuration

\+

Structured College Data

\+

College Knowledge Base

\+

Agent Configuration

=

College-specific AI Admissions Agent



A new college should be onboardable primarily through configuration and data ingestion rather than source-code changes.

---

## Voice Layer Architecture (Task 011 Addendum)

The voice layer is an adapter around the AI Admissions Agent Core described above, not a second agent. Both entry points converge on the same conversation/agent path:

```text
Web browser microphone          Phone call
        |                            |
Realtime transport (mock/         Telephony provider webhook
 WebRTC/LiveKit-compatible)             |
        |                            |
        +------------ VoiceSession --+
                       |
              Conversation (existing)
                       |
              AgentOrchestrator.handle_message()   <- Task 006, unchanged
                       |
        RAG + agent tools + leads + appointments + applications + escalation
                       |
              TTS (provider-neutral)
                       |
         Student / caller
```

`app/services/voice.py` owns only: session lifecycle, the turn-taking/barge-in state machine, provider selection, and converting the orchestrator's text response into speech. It never duplicates intent detection, tool logic, or business rules - those remain exactly the Task 006-010 implementations, reused unchanged. Provider interfaces live in `app/voice/providers/`; see docs/voice.md section 71 for what is implemented versus provider-dependent, and docs/api-contract.md's Voice APIs section for the request/response contract.

---

## Analytics Architecture (Task 013 Addendum)

Analytics is a read-only aggregation layer over the existing transactional tables - not a separate data store, ETL pipeline, or warehouse:

```text
leads, appointments, applications, conversations,
messages, voice_sessions, support_tickets, unanswered_questions
                       |
        college_id + created_at filter (composite index)
                       |
        SQL COUNT / GROUP BY / AVG (app/analytics/service.py)
                       |
        college-timezone-aware date range (app/analytics/dates.py)
                       |
        GET /api/v1/analytics/overview | /trends
```

Every metric is computed on demand from live rows already written by the leads/appointments/applications/conversations/voice/support subsystems; there is no analytics-specific write path, no background aggregation job, and no cache in front of it (correctness first - add a short tenant- and range-aware cache later only if load testing shows it is warranted). Tenant isolation and RBAC reuse the exact `resolve_tenant_college_id` / `require_permission` mechanisms every other router uses - analytics introduces no new authorization concept. See docs/api-contract.md section 64 for the endpoint contract and metric definitions, including which AI-operations metrics are intentionally reported as unavailable rather than approximated.



