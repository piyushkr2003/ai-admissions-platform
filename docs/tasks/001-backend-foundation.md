\# Task 001 — Backend Foundation



\## Objective



Create the initial production-ready FastAPI backend foundation for the AI Voice Admissions Platform.



This task establishes the backend structure only.



Do not implement the complete product in this task.



\---



\# Read First



Before making changes, read:



\- AGENTS.md

\- CLAUDE.md

\- docs/product-requirements.md

\- docs/architecture.md

\- docs/database.md

\- docs/api-contract.md

\- docs/development.md



\---



\# Scope



Implement:



1\. Python backend project structure

2\. FastAPI application

3\. configuration management

4\. environment handling

5\. health endpoints

6\. API versioning foundation

7\. structured error handling

8\. request/correlation ID middleware

9\. database connection foundation

10\. SQLAlchemy/Alembic foundation

11\. pytest configuration

12\. basic backend tests

13\. Docker support for backend

14\. developer documentation updates if required



\---



\# Technology



Use:



\- Python

\- FastAPI

\- Pydantic

\- SQLAlchemy

\- Alembic

\- PostgreSQL

\- pytest



Use current stable versions compatible with the project's Python version.



Do not add unnecessary dependencies.



\---



\# Expected Structure



Create a clean structure similar to:



```text

backend/

├── app/

│   ├── \_\_init\_\_.py

│   ├── main.py

│   ├── core/

│   ├── db/

│   ├── api/

│   │   └── v1/

│   ├── models/

│   ├── schemas/

│   ├── services/

│   └── middleware/

├── tests/

├── alembic/

├── alembic.ini

├── pyproject.toml

├── Dockerfile

└── README.md



Adjust the structure if the architecture documentation requires a better organization.



Application



Create the FastAPI application with:



GET /health

GET /ready



Health should confirm that the application process is running.



Readiness should verify required dependencies where appropriate.



Do not make readiness unnecessarily expensive.



API Versioning



Create the foundation for:



/api/v1



Do not implement all business endpoints yet.



Create a simple versioned router structure that future tasks can extend.



Configuration



Create strongly typed application settings.



Configuration should support:



environment

database URL

API configuration

CORS configuration

logging configuration



Prepare the structure for future:



LLM credentials

STT credentials

TTS credentials

voice provider credentials

storage credentials



Do not require those providers to work in this task.



Environment



Create/update:



.env.example



Do not commit real secrets.



The application must fail clearly when required production configuration is missing.



Development defaults may be provided where safe.



Database



Set up:



SQLAlchemy

PostgreSQL connection

session management

Alembic



The database layer must be designed so future models can enforce:



college\_id



for tenant isolation.



Do not implement all database models in this task.



Transactions



Provide a clean database session/transaction pattern that future services can reuse.



Avoid global unmanaged database sessions.



Error Handling



Create a consistent API error response structure according to:



docs/api-contract.md



Handle common cases such as:



validation errors

unauthorized errors

forbidden errors

not found

conflict

internal server errors



Do not expose internal stack traces in production responses.



Request IDs



Implement request/correlation ID handling.



Every request should have a traceable ID.



The ID should be:



accepted from a trusted request header when appropriate

generated when missing

returned in the response

available to structured logging



Do not trust arbitrary user-provided IDs for security decisions.



Logging



Create structured logging foundations.



At minimum log:



timestamp

level

request\_id

method

path

status

duration



Do not log:



passwords

API keys

database credentials

authorization tokens

unnecessary personal information

CORS



Create configurable CORS settings.



Do not use unrestricted CORS in production by default.



Development may have controlled local origins.



Testing



Create tests for:



FastAPI application starts.

/health returns success.

/ready behaves correctly.

API version router loads.

Request ID is generated.

Existing request ID is propagated safely.

Validation errors follow the API error format.

Configuration loads correctly.

Database configuration is validated.



Tests must be deterministic.



Docker



Create a backend Dockerfile suitable for production.



Requirements:



no development secrets baked into image

non-root runtime where practical

predictable startup

environment-driven configuration

health-check compatibility



Do not add production deployment infrastructure yet.



Docker Compose



If required for local development, integrate the backend with the repository's existing docker-compose architecture.



Do not unnecessarily redesign the existing repository.



PostgreSQL should be available for local development.



Security Requirements



Verify:



no secrets committed

no credentials hardcoded

production CORS is restricted

error responses do not leak internals

database credentials come from environment

tenant context can be introduced cleanly later

Non-Goals



Do NOT implement:



college CRUD

courses

eligibility

scholarships

leads

appointments

applications

RAG

voice

dashboard

authentication UI

AI agent



Those belong to later tasks.



Definition of Done



This task is complete only when:



\[ ] Backend structure exists

\[ ] FastAPI starts successfully

\[ ] /health works

\[ ] /ready works

\[ ] /api/v1 foundation exists

\[ ] Configuration is typed

\[ ] .env.example exists

\[ ] PostgreSQL connection foundation exists

\[ ] Alembic is configured

\[ ] Error handling is structured

\[ ] Request IDs work

\[ ] Logging foundation exists

\[ ] CORS is configurable

\[ ] pytest works

\[ ] Backend tests pass

\[ ] Dockerfile works

\[ ] No secrets are committed

\[ ] Code follows repository instructions

Required Agent Report



When finished, report:



Files created/modified.

Architecture decisions.

Commands run.

Tests run.

Test results.

Any unresolved issues.

Any assumptions made.



Do not modify unrelated files.



Do not implement future tasks.





