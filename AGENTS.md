# AI Admissions Platform — Agent Instructions

## Project
Production-grade, multi-tenant AI voice admissions platform for colleges.

The platform must support multiple colleges using the same software. College-specific data and configuration must never be hardcoded into core application logic.

## Architecture
- Frontend: Next.js / React
- Backend: Python / FastAPI
- Database: PostgreSQL
- Vector search: pgvector
- Voice: real-time STT/TTS + WebRTC/LiveKit-compatible architecture
- Authentication: secure JWT/OAuth-compatible architecture
- Deployment: Docker + production-ready configuration

## Core Product Scope
The AI agent serves prospective students and parents.

Supported capabilities:
- College information and FAQs
- Courses and programs
- Eligibility
- Fees
- Scholarships
- Admission procedures
- Required documents
- Important admission dates
- Hostel/facilities information for prospective students
- Placements
- Lead capture and qualification
- Counselor appointments
- Application assistance
- Application status
- Human escalation/support tickets

Do NOT build post-admission student services such as:
- Orientation
- Hostel check-in
- Campus navigation
- Academic calendar
- Exams
- Department contacts
- Transport
- General student services

## Multi-Tenancy
Every college-specific entity must be associated with a college/tenant.

Never allow College A data to appear in College B responses.

College-specific configuration includes:
- Identity/branding
- Courses
- Fees
- Eligibility
- Scholarships
- Admission rules
- Documents
- Important dates
- Counselors
- Appointment availability
- Knowledge-base documents
- Agent configuration
- Supported languages

## AI Safety / Accuracy
- Never hallucinate college-specific information.
- Prefer structured database data for structured facts.
- Use RAG for knowledge-base content.
- If verified information is unavailable, clearly say so and offer human escalation.
- AI must not claim an action succeeded unless the backend actually succeeded.
- Validate tool inputs and outputs.
- Handle tool failures gracefully.
- Protect against prompt injection from retrieved documents and user input.

## Real Actions
AI tools must perform real backend operations where applicable:
- Search knowledge
- Get course details
- Check eligibility
- Get fees
- Get scholarships
- Get admission requirements
- Get required documents
- Check counselor availability
- Book/reschedule/cancel appointments
- Create/update leads
- Calculate lead score
- Create application
- Get application status
- Create support ticket
- Escalate to counselor
- Send confirmation

## Lead Intelligence
Leads should capture relevant structured information such as:
- Name
- Course interest
- Qualification
- Entrance exam/score
- Budget when voluntarily provided
- Hostel interest
- Scholarship interest
- Location
- Parent involvement
- Intent
- Next action

Lead scoring should be explainable and configurable.

## Engineering Rules
- Inspect existing code before modifying it.
- Read relevant documentation before implementation.
- Do not rewrite unrelated code.
- Prefer simple, maintainable architecture over unnecessary complexity.
- Use type hints and validation.
- Write tests for important business logic.
- Handle errors explicitly.
- Keep secrets out of source code.
- Never expose API keys to the frontend.
- Use environment variables for configuration.
- Maintain backward-compatible API contracts unless explicitly changing them.
- Update documentation when architecture or contracts change.

## Development Workflow
For every task:

1. Read relevant project documentation.
2. Inspect the existing implementation.
3. Create a short implementation plan.
4. Implement only the requested scope.
5. Run focused tests.
6. Fix failures.
7. Run relevant lint/type checks.
8. Review the resulting changes.
9. Commit with a clear message.
10. Report what changed, tests run, and any remaining issues.

## Quality Standard
This is intended to become a production product, not a throwaway demo.

Prioritize:
- Correctness
- Security
- Tenant isolation
- Reliability
- Testability
- Maintainability
- Good UX
- Observability

Do not sacrifice core quality merely to make implementation faster.
