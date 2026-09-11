\# AI Admissions Platform — Product Requirements



\## 1. Product Overview



The AI Admissions Platform is a reusable, production-grade AI voice admissions system for colleges and educational institutions.



The company should be able to deploy the same software for multiple colleges.



The core platform remains the same. Each college provides its own configuration, structured data, knowledge documents, counselors, courses, fees, admission rules, and branding.



Example:



College A

College B

College C



All use the same platform but receive college-specific AI responses and actions.



Development must initially use fictional/sample data.



Demo college:



Nova Institute of Technology



This is fictional demo data and must not be presented as a real institution.



\---



\## 2. Primary Users



\### Prospective Students



Students can use the AI agent to:

\- Ask admission questions

\- Explore courses

\- Check basic eligibility

\- Understand fees

\- Ask about scholarships

\- Understand admission procedures

\- Learn required documents

\- Ask about admission deadlines

\- Ask about hostel and facilities

\- Ask about placements

\- Speak to a counselor

\- Book a counselor appointment

\- Start an application

\- Check application status



\### Parents



Parents can ask the same admission-related questions and request counselor assistance.



\### College Admissions Staff



Admissions staff use the admin dashboard to:

\- View leads

\- View conversations

\- View appointments

\- View applications

\- Review AI-generated summaries

\- Review lead scores

\- Handle escalations

\- Manage college information

\- Manage knowledge sources



\### Platform Administrators



Platform administrators manage multiple colleges and their configurations.



\---



\## 3. Product Scope



The platform focuses on PRE-ADMISSION and ADMISSION workflows.



\### Included



\- College information

\- Courses/programs

\- Eligibility

\- Fees

\- Scholarships

\- Admission process

\- Required documents

\- Important dates

\- Hostel/facilities information for prospective students

\- Placement information

\- FAQs

\- Lead capture

\- Lead qualification

\- Lead scoring

\- Counselor appointment booking

\- Appointment rescheduling

\- Appointment cancellation

\- Application assistance

\- Draft application creation

\- Application status

\- Support tickets

\- Human escalation

\- Voice conversations

\- Conversation history

\- Analytics



\### Explicitly Excluded



Do not build post-admission student-service functionality such as:



\- Orientation

\- Hostel check-in

\- Campus navigation

\- Academic calendar

\- Exam information

\- Department contacts

\- Transport services

\- General student services



\---



\## 4. Voice Agent



The platform provides a natural conversational AI voice agent.



The user should be able to speak naturally rather than selecting predefined menus.



The agent should:

\- Understand natural language

\- Handle follow-up questions

\- Maintain conversation context

\- Ask clarifying questions

\- Retrieve verified college information

\- Perform supported actions

\- Confirm actions

\- Escalate when necessary



The system should support:



\- English

\- Hindi

\- Hinglish



The architecture should allow additional regional languages later without redesigning the core system.



\---



\## 5. Example Conversation



Example:



Student:

"I want to know about B.Tech CSE."



Agent:

"Sure. I can help with that. May I know your Class 12 percentage?"



Student:

"I got 78 percent."



Agent:

"Based on the configured admission criteria, you are eligible for the B.Tech CSE program."



The agent can then explain:

\- Course details

\- Eligibility

\- Fees

\- Scholarships

\- Admission process

\- Required documents



Student:

"Can I talk to a counselor?"



Agent:

"Yes. I can check the available counselor appointments for you."



The backend checks actual availability.



Student selects a slot.



The backend creates the appointment.



Only after successful persistence should the agent confirm the booking.



The system should also create or update the student's lead.



\---



\## 6. AI Capabilities



The agent should be capable of:



\### Information Retrieval



Answer verified questions about:

\- College

\- Courses

\- Fees

\- Eligibility

\- Scholarships

\- Admission

\- Documents

\- Deadlines

\- Hostel/facilities

\- Placements

\- FAQs



\### Qualification



The agent should identify useful admission information such as:

\- Name

\- Course interest

\- Academic qualification

\- Marks

\- Entrance exam information

\- Scholarship interest

\- Hostel interest

\- Location

\- Admission intent



The agent should not unnecessarily interrogate the student.



Only collect information relevant to the current conversation or required workflow.



\### Recommendations



The agent may recommend relevant next steps based on verified college configuration.



Examples:

\- Explore a course

\- Check eligibility

\- Review scholarship options

\- Speak to counselor

\- Book appointment

\- Start application



The agent must not invent recommendations unsupported by college data.



\---



\## 7. Eligibility



Eligibility should be based on configurable college rules.



Rules may include:

\- Minimum percentage

\- Required subjects

\- Entrance examination requirements

\- Minimum entrance score

\- Course-specific requirements

\- Category-specific rules where configured



Eligibility logic belongs in backend business logic/configuration, not only inside the LLM prompt.



The AI agent should call an eligibility tool when a structured eligibility check is required.



The agent must clearly distinguish:

\- Eligible

\- Not eligible

\- Cannot determine



If eligibility cannot be verified, escalate or provide the appropriate next step rather than guessing.



\---



\## 8. Fees



Fees should come from structured college data.



The platform should support:

\- Tuition fees

\- Annual/semester fees

\- Hostel fees where applicable

\- Other configured admission-related charges



The agent must not invent fee amounts.



If a fee is unavailable or outdated, the agent should say that verified information is unavailable and offer counselor escalation.



\---



\## 9. Scholarships



Scholarship information should be configurable per college.



Possible fields:

\- Scholarship name

\- Eligibility

\- Amount/percentage

\- Required documents

\- Application process

\- Deadline



The agent must only present configured scholarship information.



\---



\## 10. Admission Process



The college can configure its admission workflow.



Example:



1\. Select program

2\. Check eligibility

3\. Submit application

4\. Upload required documents

5\. Pay application fee

6\. Complete required examination/interview

7\. Receive admission decision



The actual steps must be configurable per college.



\---



\## 11. Required Documents



The platform should maintain course/admission-specific document checklists.



Examples:

\- Class 10 marksheet

\- Class 12 marksheet

\- Entrance examination scorecard

\- Government identification

\- Passport photographs

\- Transfer certificate

\- Other configured documents



The agent can explain which documents are required.



\---



\## 12. Important Dates



The system should support configurable admission dates such as:

\- Application opening

\- Application deadline

\- Entrance examination

\- Counseling dates

\- Admission decision dates

\- Fee payment deadlines



Dates must come from verified college configuration.



The agent must never invent deadlines.



\---



\## 13. Counselor Appointments



The system should support:



\- Counselor availability

\- Available time slots

\- Appointment booking

\- Appointment rescheduling

\- Appointment cancellation

\- Appointment confirmation



Appointment data must be persisted.



The system must handle booking conflicts and race conditions.



The AI agent must not claim a booking succeeded unless the backend confirms success.



\---



\## 14. Lead Management



A lead represents a prospective student or parent with admission intent.



A lead may contain:



\- Name

\- Contact information

\- Course interest

\- Academic qualification

\- Entrance exam information

\- Budget when voluntarily provided

\- Hostel interest

\- Scholarship interest

\- Location

\- Parent involvement

\- Intent

\- Next action

\- Lead status

\- Lead score



Lead statuses:



\- NEW

\- QUALIFYING

\- QUALIFIED

\- CONTACTED

\- APPOINTMENT\_BOOKED

\- APPLICATION\_STARTED

\- CONVERTED

\- LOST



\---



\## 15. Lead Scoring



Lead scoring should be explainable.



Example scoring model:



\- Course identified: +20

\- Eligibility confirmed: +20

\- Fees discussed: +10

\- Scholarship interest: +10

\- Counselor appointment requested: +20

\- Application started: +30



The score should be configurable in the future.



Lead categories:



\- COLD

\- WARM

\- HOT



A lead should not become HOT simply because the AI guesses that the student is interested.



Scores should be based on observable actions or configured signals.



\---



\## 16. Application Assistance



The agent should support an "Apply with me" workflow.



Example:



Student:

"I want to apply."



Agent:

"I can help you start the application. I'll ask for the required details one by one."



The system collects required information and creates a draft application.



The application should have a clear status.



Example statuses:



\- DRAFT

\- IN\_PROGRESS

\- SUBMITTED

\- UNDER\_REVIEW

\- ACCEPTED

\- REJECTED



The agent must never claim that an application has been submitted unless the backend actually records the submission.



\---



\## 17. Human Escalation



The AI should know when it cannot safely answer.



Escalation should occur when:

\- Verified information is unavailable

\- The user asks for information outside the supported scope

\- A complex admission case requires human judgment

\- A backend action repeatedly fails

\- The user explicitly requests a human counselor

\- The situation requires college staff intervention



Possible escalation actions:



\- Create support ticket

\- Request counselor callback

\- Book counselor appointment

\- Mark conversation for human review



The AI should be transparent when escalating.



\---



\## 18. Knowledge Base



Each college has its own knowledge base.



Sources may include:

\- PDF documents

\- Website content

\- Excel files

\- CSV files

\- FAQs

\- Course catalogues

\- Fee documents

\- Scholarship documents

\- Admission policies

\- Important-date documents



Knowledge retrieval must always be scoped to the current college.



College A must never retrieve College B's documents.



\---



\## 19. Admin Dashboard



The dashboard should provide:



\### Overview



\- Total calls

\- Total conversations

\- New leads

\- Hot leads

\- Appointments

\- Applications

\- Escalations



\### Leads



\- Lead list

\- Lead details

\- Lead score

\- Lead status

\- Course interest

\- Conversation summary

\- Next action



\### Appointments



\- Upcoming appointments

\- Completed appointments

\- Cancelled appointments

\- Rescheduled appointments



\### Applications



\- Draft applications

\- Applications in progress

\- Submitted applications

\- Application statuses



\### Conversations



\- Conversation history

\- Transcript

\- AI summary

\- Intent

\- Actions taken

\- Escalations



\### Knowledge Base



\- Upload documents

\- View sources

\- Ingestion status

\- Remove/replace sources

\- Knowledge search/testing



\### Analytics



Track:

\- Call volume

\- Conversation volume

\- Lead conversion

\- Appointment conversion

\- Application conversion

\- Escalation rate

\- AI resolution rate

\- Average conversation duration

\- Query categories

\- Peak interaction periods



\---



\## 20. Multi-College Architecture



The platform must support multiple tenants.



Every college-specific entity must belong to a college.



Examples:



College

Course

Lead

Counselor

Appointment

Application

Conversation

Knowledge Source

Knowledge Chunk

Agent Configuration



All relevant records must contain a college/tenant relationship.



Tenant isolation is a critical security requirement.



\---



\## 21. College Configuration



A college configuration should include:



\### Identity

\- College name

\- Logo

\- Description

\- Contact information

\- Website

\- Location

\- Branding



\### Admissions

\- Admission process

\- Important dates

\- Documents

\- Eligibility rules



\### Courses

\- Program name

\- Degree

\- Duration

\- Eligibility

\- Fees

\- Seats where applicable



\### Scholarships

\- Scholarship details

\- Eligibility

\- Amount

\- Documents

\- Deadlines



\### Counselors

\- Counselor details

\- Availability

\- Contact preferences



\### Agent

\- Agent name

\- Personality

\- Greeting

\- Supported languages

\- Escalation rules



\---



\## 22. Demo College



Use fictional:



Nova Institute of Technology



Sample programs:



\- B.Tech Computer Science and Engineering

\- B.Tech Artificial Intelligence and Machine Learning

\- Bachelor of Computer Applications

\- Master of Business Administration

\- Master of Computer Applications



All fees, eligibility rules, scholarships, dates, counselor information and other institutional information must be explicitly marked as fictional demo data.



\---



\## 23. Product Principle



The platform should NOT be built as a collection of hardcoded responses for Nova Institute of Technology.



Instead:



Core platform logic

\+

College configuration

\+

College structured data

\+

College knowledge base

\+

Agent configuration



should produce the final college-specific AI admissions agent.



Adding a new college should primarily require configuration and data ingestion rather than rewriting application code.



\---



\## 24. Quality Requirements



The system must be production-oriented.



Important requirements include:



\- Tenant isolation

\- Authentication

\- Authorization

\- Secure secrets management

\- Input validation

\- API security

\- Error handling

\- Logging

\- Monitoring

\- Health checks

\- Database migrations

\- Backups

\- Automated tests

\- Rate limiting

\- Retry handling

\- Voice interruption handling

\- Booking conflict handling

\- AI hallucination prevention

\- Prompt injection protection



The system should fail safely when information or integrations are unavailable.



\---



\## 25. Success Criteria



A successful demo should demonstrate the complete admission journey:



1\. Student starts a voice conversation.

2\. Student asks about B.Tech CSE.

3\. Agent retrieves course information.

4\. Agent asks relevant qualification questions.

5\. Backend checks eligibility.

6\. Agent explains verified fees.

7\. Agent explains available scholarship information.

8\. Student asks for a counselor.

9\. Backend checks real counselor availability.

10\. Student selects a slot.

11\. Backend creates the appointment.

12\. Lead is created or updated.

13\. Lead score is calculated.

14\. Agent provides required document information.

15\. Student asks to apply.

16\. Backend creates a draft application.

17\. Admin dashboard immediately shows the lead, appointment and application.



The demo should prove that the AI agent can both answer questions and perform real actions.



