\# Voice Architecture

\## AI Voice Admissions Platform



\*\*Version:\*\* 1.0  

\*\*Status:\*\* Production Design Contract



\---



\# 1. Purpose



This document defines the real-time voice architecture for the AI Voice Admissions Platform.



The voice system allows prospective students and parents to communicate naturally with the college AI admissions agent using speech.



The system must support:



\- browser-based voice

\- phone-based voice architecture

\- real-time speech recognition

\- AI responses

\- natural text-to-speech

\- interruption/barge-in

\- multilingual conversations

\- conversation persistence

\- tool execution

\- human escalation

\- failure recovery

\- production monitoring



\---



\# 2. Voice Architecture



The core flow is:



```text

Student / Parent

&#x20;      ↓

Microphone / Phone

&#x20;      ↓

Real-Time Audio Transport

&#x20;      ↓

Speech-to-Text

&#x20;      ↓

Conversation Manager

&#x20;      ↓

AI Agent

&#x20;      ↓

Agent Tools

&#x20;      ↓

Verified Backend Result

&#x20;      ↓

AI Response

&#x20;      ↓

Text-to-Speech

&#x20;      ↓

Audio Transport

&#x20;      ↓

Student / Parent

3\. Supported Channels



The platform should support:



Web Voice



Student uses a microphone through the college website.



Browser

&#x20;  ↓

WebRTC / Real-Time Transport

&#x20;  ↓

Voice Backend

Phone



Student calls a college admissions number.



Phone

&#x20;  ↓

Telephony Provider

&#x20;  ↓

Voice Backend

&#x20;  ↓

AI Agent



The internal agent architecture should remain the same regardless of channel.



4\. Provider-Agnostic Architecture



The product must not hardcode the entire platform around one voice provider.



The architecture should use provider adapters.



Conceptually:



&#x20;                Voice Interface

&#x20;                      │

&#x20;         ┌────────────┴────────────┐

&#x20;         │                         │

&#x20;    Web Adapter              Phone Adapter

&#x20;         │                         │

&#x20;         └────────────┬────────────┘

&#x20;                      ↓

&#x20;               Voice Session

&#x20;                      ↓

&#x20;                AI Agent Core



This allows future provider changes without rewriting the agent/business logic.



5\. Core Components



The voice system consists of:



Audio transport

Voice session manager

Speech-to-text

Conversation manager

AI agent

Tool execution layer

Text-to-speech

Session persistence

Observability

Human escalation

6\. Voice Session



Every voice interaction creates a voice session.



A session should contain:



session\_id

college\_id

conversation\_id

channel

language

status

started\_at

ended\_at

duration

termination\_reason

provider

provider\_session\_id



The college\_id must come from trusted tenant context.



7\. Voice Session Lifecycle



Possible states:



created

connecting

active

ending

completed

failed



Example:



created

&#x20;  ↓

connecting

&#x20;  ↓

active

&#x20;  ↓

ending

&#x20;  ↓

completed



Failure:



connecting

&#x20;  ↓

failed

8\. Session Creation



API:



POST /api/v1/voice/sessions



Request:



{

&#x20; "channel": "web\_voice",

&#x20; "language": "en"

}



Response:



{

&#x20; "data": {

&#x20;   "session\_id": "voice\_123",

&#x20;   "conversation\_id": "conv\_123",

&#x20;   "connection\_token": "..."

&#x20; }

}



Provider credentials should be short-lived and scoped to the session.



Never expose permanent provider credentials to the browser.



9\. Audio Transport



For browser voice, use a real-time audio transport such as:



WebRTC

LiveKit-compatible transport

equivalent secure real-time transport



Requirements:



encrypted transport

low latency

interruption support

connection recovery

session authentication

microphone permission handling



The implementation should remain abstract enough to support provider replacement.



10\. Browser Voice Flow

Browser

&#x20;  ↓

Request microphone permission

&#x20;  ↓

Create authenticated voice session

&#x20;  ↓

Connect real-time audio

&#x20;  ↓

Stream microphone audio

&#x20;  ↓

STT

&#x20;  ↓

AI Agent

&#x20;  ↓

TTS

&#x20;  ↓

Stream audio back



The browser must never contain:



LLM API keys

STT provider secrets

TTS provider secrets

database credentials

11\. Phone Voice Flow

Student Phone

&#x20;     ↓

Telephony Provider

&#x20;     ↓

Inbound Call

&#x20;     ↓

College Voice Number

&#x20;     ↓

Voice Session

&#x20;     ↓

STT

&#x20;     ↓

AI Agent

&#x20;     ↓

TTS

&#x20;     ↓

Telephony Provider

&#x20;     ↓

Student



The same agent tools and college configuration should be used.



12\. Speech-to-Text



The STT layer converts speech into text.



Requirements:



streaming transcription

partial transcripts

final transcripts

punctuation where useful

multilingual support

Indian English support

Hindi support

Hinglish support

reasonable noise tolerance



The STT provider should be abstracted behind an internal interface.



13\. STT Events



The voice system may receive:



speech\_started

partial\_transcript

final\_transcript

speech\_stopped



Example:



{

&#x20; "type": "final\_transcript",

&#x20; "session\_id": "voice\_123",

&#x20; "text": "What is the fee for B.Tech CSE?"

}

14\. Partial Transcripts



Partial transcripts may be used for responsiveness but should not automatically trigger irreversible actions.



For example:



Do not book an appointment based on an incomplete partial transcript.



Wait for a sufficiently reliable final user utterance.



15\. Speech Detection



The system should detect when the user starts and stops speaking.



Possible mechanisms:



provider VAD

server-side VAD

client-side VAD where appropriate



The selected implementation must support natural turn-taking.



16\. Turn-Taking



The voice agent should avoid:



talking over the user

excessive silence

waiting unnecessarily

responding before the user finishes



Recommended sequence:



User starts speaking

&#x20;      ↓

Agent stops/pauses output if necessary

&#x20;      ↓

User finishes

&#x20;      ↓

Transcript finalized

&#x20;      ↓

Agent processes

&#x20;      ↓

Response generated

&#x20;      ↓

TTS begins

17\. Barge-In



Barge-in is mandatory for a natural voice experience.



If the agent is speaking and the student says:



"Wait, no..."



the system should:



detect user speech

stop or interrupt current TTS

preserve the conversation state

process the new utterance

respond to the new intent

18\. TTS



The text-to-speech layer converts agent responses into natural speech.



Requirements:



low latency

natural prosody

interruption support

English

Hindi

Hinglish

configurable voice

stable pronunciation of names and numbers



The TTS provider should be replaceable.



19\. Voice Personality



Voice personality is controlled by college agent configuration.



Configurable attributes may include:



agent name

tone

speaking speed

greeting

language preference

formality

conversational style



Example:



friendly

professional

helpful

concise



Personality configuration must not override platform safety rules.



20\. Voice Response Length



Voice responses should generally be shorter than text responses.



Prefer:



"Yes, B.Tech CSE is available. Would you like to know the eligibility requirements?"



over a long paragraph.



For complex information, break the response into conversational pieces.



21\. Number Pronunciation



Important numbers must be spoken clearly.



Examples:



₹1,50,000

78%

2026-27

3:00 PM



The system should avoid ambiguous spoken representations.



22\. Dates and Times



Dates and times must be converted into natural speech.



For example:



Internal:



2026-09-20T15:00:00+05:30



Voice:



"Sunday, September 20th at 3 PM."



The exact wording can vary by language.



23\. Language Detection



The agent should determine the user's preferred language.



Supported initial languages:



English

Hindi

Hinglish



Example:



User:



"Sir CSE ka fee kitna hai?"



Agent may respond in natural Hinglish if supported by the college configuration.



24\. Language Switching



If the user changes language:



English

&#x20;  ↓

Hindi



the agent may switch naturally.



Do not switch repeatedly without reason.



College configuration determines which languages are enabled.



25\. Conversation Context



Voice sessions are linked to conversations.



Voice Session

&#x20;     ↓

Conversation

&#x20;     ↓

Messages

&#x20;     ↓

Tool Calls

&#x20;     ↓

Results



Relevant context should remain available throughout the session.



26\. Conversation Memory



The agent may remember information provided during the current conversation.



Examples:



name

course interest

qualification

percentage

entrance score

scholarship interest

hostel interest

appointment preference



Do not repeatedly ask for information already known.



27\. Persistent Student Context



If the student has an authenticated profile, permitted information may be associated with their profile.



If the interaction is anonymous, create a temporary session identity where appropriate.



The system must not merge two students merely because their names are similar.



28\. Voice Agent State



The agent should maintain state such as:



current\_intent

current\_course

student\_information

lead\_id

appointment\_context

application\_id

last\_tool\_result

language

escalation\_status



State should be stored server-side where persistence is required.



Do not rely exclusively on browser memory.



29\. Intent Categories



Initial intent categories:



greeting

course\_information

eligibility

fees

scholarship

admission\_process

documents

admission\_dates

hostel

facilities

placements

counselor

appointment

application

application\_status

support

escalation

unknown



The taxonomy can expand later.



30\. Voice Intent Example



User:



"I want to know if I can get into CSE."



Agent identifies:



intent = eligibility

course = B.Tech CSE



Then asks for missing eligibility information and calls the eligibility tool.



31\. Tool Execution in Voice



The voice layer must support:



Speech

&#x20;↓

Intent

&#x20;↓

Tool Selection

&#x20;↓

Tool Execution

&#x20;↓

Result

&#x20;↓

Natural Response

&#x20;↓

TTS



The user should not hear internal tool names.



32\. Long Tool Calls



If a tool takes noticeable time, the agent may provide a short conversational acknowledgement.



Example:



"Sure, let me check the available counselor slots."



Then execute the tool.



Avoid unnecessary filler.



33\. Tool Failure During Voice



If booking fails:



Do not say:



"Your appointment is booked."



Instead:



"That slot isn't available anymore. I can check another time for you."



34\. RAG During Voice



RAG may be used when the student asks an unstructured college-specific question.



Example:



"What facilities are available on campus?"



Flow:



Speech

&#x20;↓

STT

&#x20;↓

Intent

&#x20;↓

search\_knowledge()

&#x20;↓

Relevant Evidence

&#x20;↓

LLM

&#x20;↓

TTS

35\. Structured Data During Voice



For transactional facts:



"What is the CSE fee?"

&#x20;       ↓

get\_fee\_structure()



"Am I eligible?"

&#x20;       ↓

check\_eligibility()



"Can I meet a counselor tomorrow?"

&#x20;       ↓

check\_counselor\_availability()



Structured tools are preferred over RAG when authoritative structured data exists.



36\. Voice Error Recovery



Possible failures:



microphone permission denied

network interruption

STT failure

TTS failure

LLM timeout

tool failure

session timeout

provider outage



The system should recover gracefully where possible.



37\. Microphone Permission Failure



If browser microphone access is denied:



Display:



"Microphone access is required to use voice assistance."



Offer an alternative:



text chat if available

phone number

contact/counselor option

38\. Network Interruption



If connection is temporarily lost:



detect disconnection

attempt controlled reconnect

preserve session state

restore conversation if possible



If reconnection fails:



Inform the user and provide an alternative.



39\. STT Failure



If speech cannot be understood:



The agent should ask:



"Sorry, I didn't catch that. Could you please repeat it?"



Do not invent a transcript.



40\. TTS Failure



If TTS fails:



log failure

attempt safe retry if appropriate

fall back to text where possible

preserve conversation state



Do not lose the user's request.



41\. LLM Timeout



If the model does not respond within the configured timeout:



The system should:



record the failure

avoid repeated uncontrolled retries

provide a fallback response

offer human assistance if necessary

42\. Session Timeout



Inactive sessions should eventually expire.



The timeout should be configurable.



Before termination where appropriate:



"Are you still there?"



If no response:



End the session gracefully.



43\. Maximum Session Duration



A maximum session duration may be configured to prevent:



runaway sessions

unexpected infrastructure costs

abuse



The user should be informed naturally if the session must end.



44\. Voice Security



All voice sessions must use:



authenticated session creation

encrypted transport

short-lived credentials

tenant validation

authorization

rate limiting

abuse protection



Permanent provider credentials must never be exposed to clients.



45\. Voice Abuse Protection



Protect against:



automated call flooding

excessive session creation

repeated malicious prompts

abusive API usage

cost attacks



Possible controls:



IP rate limits

session limits

phone-number limits

concurrency limits

usage quotas

abuse detection



Limits must be configurable.



46\. Phone Caller Identification



Where available, phone interactions may associate a caller's phone number with a lead/student.



However:



A phone number alone must not be treated as sufficient proof of identity for sensitive operations.



Additional verification may be required before accessing or modifying protected application information.



47\. Sensitive Operations



Sensitive operations include:



accessing private application status

changing application information

cancelling appointments

accessing private student data



The system must apply appropriate authentication/verification.



48\. Human Escalation



The agent should support escalation when:



user requests a counselor

verified information is unavailable

issue is complex

admission decision requires human judgment

important tool fails

student disputes information



Possible escalation states:



requested

queued

assigned

connected

completed

failed

49\. Live Transfer vs Callback



The platform should distinguish:



Live Transfer



The user is transferred to a counselor during the active call.



Callback



The system creates a counselor follow-up request.



Appointment



The user schedules a future counseling meeting.



These are different workflows.



50\. Voice Transcript



Every completed session should generate a transcript where permitted.



Transcript records may include:



speaker

text

timestamp

message\_id

confidence



Example:



Student:

"What is the fee for CSE?"



Agent:

"The current tuition fee is..."

51\. Transcript Privacy



Transcripts may contain personal information.



Access must be role-controlled.



College staff should only access conversations belonging to their college.



Do not expose transcripts publicly.



52\. Call Recording



If call/audio recording is enabled:



obtain required consent where applicable

define retention policy

restrict access

encrypt stored recordings

audit access

allow deletion according to policy



Recording should not be assumed to be enabled by default.



53\. Voice Analytics



Track:



total sessions

completed sessions

failed sessions

average duration

interruption rate

STT latency

TTS latency

tool latency

agent response latency

escalation rate

resolution rate

appointment conversion

application conversion

54\. Voice Quality Metrics



Important metrics:



Time to First Response



Time from completed user utterance to beginning of agent response.



End-to-End Turn Latency



Time from user finishing speech to agent audio response.



STT Latency



Speech-to-transcript latency.



Tool Latency



Time required to execute an agent tool.



TTS Latency



Time until speech begins.



These should be monitored separately.



55\. Initial Performance Targets



Initial production targets should be validated through testing.



Target:



responsive conversational turn-taking

low perceived latency

fast tool execution

minimal dead air

reliable interruption

stable sessions under expected concurrency



Exact SLA values should be finalized after provider and infrastructure benchmarking.



56\. Concurrency



The voice system must support multiple simultaneous conversations.



Concurrency limits should be configurable by:



platform

college

provider

environment



Example:



Platform limit = 100 sessions

College A = 20

College B = 15



These are configuration examples, not fixed production limits.



57\. Cost Controls



Voice systems can generate significant model/STT/TTS costs.



Track usage:



session duration

STT duration

TTS duration

model usage

tool calls

provider usage



College-level usage should be measurable.



Future billing can be based on usage if required.



58\. Observability



Every voice session should have a traceable identifier.



Example:



request\_id

session\_id

conversation\_id

college\_id



These IDs should connect:



Voice

&#x20;↓

STT

&#x20;↓

Agent

&#x20;↓

Tool

&#x20;↓

Database

&#x20;↓

Appointment / Lead / Application

59\. Voice Logs



Logs should include:



session ID

conversation ID

college ID

provider

event type

latency

success/failure

error code



Avoid logging raw audio or unnecessary personal information unless explicitly required.



60\. Voice Provider Abstraction



Use internal interfaces such as:



SpeechToTextProvider

TextToSpeechProvider

RealtimeTransportProvider

TelephonyProvider



Provider-specific implementations sit behind these interfaces.



Example:



Voice Core

&#x20;  ↓

STT Interface

&#x20;  ↓

Provider Adapter



This allows providers to be replaced later.



61\. Development Environment



Local development should support a test voice mode.



The developer should be able to:



start backend

start frontend

connect microphone

start test conversation

inspect transcript

inspect tool calls

inspect errors



No production credentials should be committed.



62\. Testing Strategy



Voice testing must include:



Functional

microphone connection

STT

TTS

conversation

tool execution

appointment booking

application creation

Interruption

user interrupts agent

agent stops speaking

conversation continues correctly

Failure

STT failure

TTS failure

LLM timeout

tool failure

network failure

Security

tenant isolation

unauthorized session access

credential exposure

malicious prompts

Load

concurrent sessions

provider limits

backend capacity

database performance

63\. Voice Test Scenarios



Minimum test scenarios:



Student asks about course.

Student asks about eligibility.

Student asks about fees.

Student asks about scholarship.

Student asks for documents.

Student asks for counselor.

Student books appointment.

Student reschedules appointment.

Student cancels appointment.

Student starts application.

Student checks application status.

Student asks unknown question.

Student switches language.

Student interrupts agent.

Booking slot becomes unavailable.

Network connection drops.

STT misunderstands speech.

TTS fails.

User requests human escalation.

Cross-tenant access attempt.

64\. Example Complete Voice Interaction

Student:

"Hi, I want to know about B.Tech CSE."



&#x20;       ↓ STT



Agent:

"Sure. I can help with that. What would you like to know?"



Student:

"Am I eligible?"



&#x20;       ↓

Agent asks for percentage/stream.



Student:

"78 percent science."



&#x20;       ↓

check\_eligibility()



Backend:

eligible



Agent:

"Based on the configured eligibility criteria, you meet the basic eligibility requirements."



Student:

"What is the fee?"



&#x20;       ↓

get\_fee\_structure()



Agent:

"The current tuition fee is ₹1,50,000 for the 2026-27 academic year."



Student:

"Can I talk to a counselor?"



&#x20;       ↓

check\_counselor\_availability()



Agent:

"I have a 3 PM slot available tomorrow. Would you like me to book it?"



Student:

"Yes."



&#x20;       ↓

book\_appointment()



Backend:

success



Agent:

"Your counseling appointment is confirmed for tomorrow at 3 PM."



&#x20;       ↓

create/update lead

calculate lead score

65\. Phone Example

Student calls college number

&#x20;       ↓

Greeting

&#x20;       ↓

Language selection/detection

&#x20;       ↓

AI admissions conversation

&#x20;       ↓

Course discussion

&#x20;       ↓

Eligibility

&#x20;       ↓

Fees

&#x20;       ↓

Counselor availability

&#x20;       ↓

Appointment

&#x20;       ↓

Lead creation

&#x20;       ↓

Call summary



The phone workflow should use the same core agent and backend tools as web voice.



66\. Greeting



The greeting should be configurable by college.



Example:



"Hello! Welcome to Nova Institute of Technology admissions. I'm your virtual admissions assistant. How can I help you today?"



The agent should not claim to be human.



67\. Agent Identity



The agent should identify itself as an AI/virtual admissions assistant when appropriate.



It must not deceive users into believing they are speaking to a human counselor.



68\. No False Action Claims



Critical rule:



If backend says success = false

&#x20;       ↓

Agent cannot say success.



Examples:



Booking failed:



Wrong:



"Your appointment is confirmed."



Correct:



"I couldn't complete that booking. Let me check another available time."



Application creation failed:



Wrong:



"Your application has been created."



Correct:



"I wasn't able to start the application right now. I can try again or connect you with admissions staff."



69\. Graceful Ending



When the user finishes:



"Thanks for contacting admissions. If you need anything else about the application process, I'm here to help."



If an appointment was created:



"Your counseling appointment is confirmed. You'll receive the confirmation through the configured channel."



70\. Final Voice Principle



The voice system should feel like a natural conversation, but underneath it must remain a deterministic, secure software system.



The architecture is:



Natural Voice

&#x20;     ↓

Reliable Transcription

&#x20;     ↓

AI Conversation

&#x20;     ↓

Verified Tools

&#x20;     ↓

Backend Source of Truth

&#x20;     ↓

Natural Voice Response



The product must optimize simultaneously for:



Naturalness

\+

Accuracy

\+

Low Latency

\+

Reliability

\+

Security

\+

Tenant Isolation

\+

Real Actions



The AI may sound human-like.



The underlying system must remain predictable, observable, secure, and verifiable.

