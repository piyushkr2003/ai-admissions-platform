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

---

# 71. Task 011 Implementation Status (Addendum)

This section records what Task 011 actually built against the design above, so the gap between architectural intent and running code is explicit rather than assumed.

## 71.1 What is implemented

- Provider-neutral interfaces in `app/voice/providers/base.py`: `STTProvider`, `TTSProvider`, `RealtimeTransportProvider`, `TelephonyProvider`, plus deterministic mock implementations (`app/voice/providers/mock.py`) selected by default via `app/voice/providers/factory.py`.
- A channel-neutral `VoiceSession` model (`app/models/voice.py`) and service (`app/services/voice.py`) covering session creation, the turn-taking/barge-in state machine (`app/voice/state_machine.py`), event handling, idempotent phone-call creation, session termination, and audit logging.
- A REST event contract (`app/voice/router.py`) for both channels - see the Voice APIs section of `docs/api-contract.md`.
- Full integration with the existing Task 006 `AgentOrchestrator`: a `final_transcript` event calls `handle_message()` on the session's own `Conversation` exactly as the text chat endpoint does. No second reasoning system exists. Tool execution, RAG, leads, appointments, applications, and escalation all run through the same orchestrator and the same tools as Tasks 006-010.
- College-level voice configuration on `agent_configs` (`voice_phone_number`, `voice_settings` JSON: web/phone enabled flags, default/fallback language, voice_id, greeting override, session timeout, max duration, recording/transcript policy).
- Structured logging with session/college/conversation correlation for session creation, agent latency, TTS latency, interruptions, and session end.

## 71.2 What is provider-dependent / not implemented

- No real WebRTC/LiveKit media transport carries actual audio frames. `RealtimeTransportProvider` issues a real, short-lived session credential; the media path itself is a real provider's job once one is configured.
- No real STT/TTS vendor is integrated. `STTProvider.recognize()` takes raw audio bytes; the phone webhook path exercises this contract with the mock decoding UTF-8 text (deterministic for tests). A production deployment implements this interface against a real vendor SDK without changing `VoiceSessionService`.
- No real telephony vendor (Twilio, Exotel, etc.) is wired up. `SharedSecretTelephonyProvider` demonstrates the generic HMAC-webhook-signature pattern most vendors use; a vendor-specific adapter replaces it behind the same `TelephonyProvider` interface.
- Latency figures reported in API responses and logs (`agent_latency_ms`, `tts_latency_ms`) are genuinely measured wall-clock time for the mock providers' work, not a claim about a real provider's performance.

## 71.3 Configuration

See `docs/development.md` for the full environment variable list and local development instructions.

---

# 72. Task 015 Implementation Status (Addendum)

Task 015 adds a real `RealtimeTransportProvider` adapter for web voice - LiveKit - behind the exact same interface Task 011 defined, plus a browser client that actually opens a LiveKit room and captures the microphone. Nothing about `AgentOrchestrator`, `VoiceSessionService`, the event contract, or the turn-taking state machine changed: this is strictly a new adapter selected by configuration (docs/voice.md section 4, "provider adapters").

## 72.1 What is implemented

- `app/voice/providers/livekit.py`: `LiveKitTransportProvider`, selected via `VOICE_TRANSPORT_PROVIDER=livekit`. `create_session()` mints a real, spec-compliant LiveKit access token (HS256 JWT with `sub`/`iss`/`nbf`/`exp` claims and a `video` grants object - `roomJoin`, `room`, `canPublish`, `canSubscribe`, `canPublishData`) using PyJWT directly, matching what LiveKit's own server SDKs produce byte-for-byte. `LIVEKIT_API_SECRET` signs the token and is never returned, logged, or reachable from the frontend.
- Tenant isolation is enforced in the room name itself: every room is `college-{college_id}-voice-{session_id}`, so a token can never be replayed to join a different tenant's room even if a session id were guessed.
- `app/voice/providers/factory.py::get_transport_provider()` fails closed with `ResourceUnavailableError` (HTTP 503) if `livekit` is selected without all three of `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` - it never silently falls back to the mock transport. `Settings.validate_for_production()` additionally fails application startup outright under the same condition when `APP_ENV=production`, so a misconfigured production deployment never even starts serving traffic.
- `POST /api/v1/voice/sessions` now returns `provider` (`"mock"` or `"livekit"`) and `server_url` (the LiveKit endpoint the client connects to; `null` for mock) alongside the existing `connection_token`. The frontend uses `provider` - never an assumption - to label a session MOCK or LIVE.
- Frontend: `frontend/features/voice/voice-console.tsx`, a staff-facing (RBAC-gated, `voice_sessions:write`) test console at `/dashboard/voice/console`, per docs/voice.md section 61's requirement for a local/test voice mode. It requests microphone permission, connects to the LiveKit room with the `livekit-client` browser SDK when `provider === "livekit"`, and drives the existing REST event contract (`POST /voice/sessions/{id}/events`) for transcript submission and playback exactly as the mock/phone channels already do - see 72.2 for why STT/TTS were not re-architected around LiveKit's own media pipeline.
- Frontend connection-state handling: microphone-permission denial, LiveKit `disconnected`/`reconnecting`/`reconnected` room events, session-creation failure, and idle/max-duration termination messages returned by the backend are all surfaced distinctly rather than a single generic error.
- Barge-in: submitting a new transcript while the agent's audio is still playing stops local playback immediately and sends an `interruption` event first, so the existing server-side TTS-cancel/turn-state barge-in logic (docs/voice.md section 17) is triggered from the LiveKit client exactly as it already is from the mock/phone test harness.

## 72.2 What remains provider-dependent / not implemented

- **(Resolved in Task 016.)** No LiveKit Agents worker joined the room as of Task 015 - see section 73 below for the realtime voice worker that now does.
- **No telephony/SIP integration was added or changed.** `TelephonyProvider` and the phone voice flow are exactly as Task 011 left them; Task 015 is web-voice-only.
- `LiveKitTransportProvider.close_session()` is intentionally best-effort logging only, not a real LiveKit room-deletion API call (mirrors `TTSProvider.cancel()`'s existing "must never raise" contract) - an empty LiveKit room closes on its own via the server's configured `empty_timeout`. Real room administration (via the `livekit-api` RoomServiceClient) can be added later without changing this interface.
- A genuine LiveKit smoke test (dialing a real `LIVEKIT_URL` with real credentials) was **not** performed in this environment because no real LiveKit project credentials were available. Only local, network-free tests (JWT construction/verification, tenant-scoped room naming, provider selection, fail-closed behavior) were run - see `tests/test_voice_livekit.py`.

## 72.3 Configuration

```text
VOICE_TRANSPORT_PROVIDER=mock   # or "livekit"
LIVEKIT_URL=                    # e.g. wss://your-project.livekit.cloud - required if livekit selected
LIVEKIT_API_KEY=                # required if livekit selected
LIVEKIT_API_SECRET=             # required if livekit selected - server-side only, never sent to the browser
LIVEKIT_TOKEN_TTL_SECONDS=600
```

---

# 73. Task 016 Implementation Status (Addendum) - Realtime Voice Agent Worker + LLM

Task 016 closes the gap Task 015 documented above: a real process now joins the LiveKit room as the agent, performs speech recognition on the student's audio, drives the AI admissions agent, and publishes synthesized speech back - a genuine two-way realtime conversation, not just a transport connection.

## 73.1 Architecture

```text
Student microphone
      |
LiveKit room (real WebRTC, Task 015)
      |
app/voice/worker/room_client.py         <- thin livekit.rtc wrapper (normalizes
      |                                     raw room events; not itself unit-tested,
      |                                     no real LiveKit server is reachable here)
app/voice/worker/session_worker.py      <- RealtimeVoiceWorker: buffers audio using
      |                                     LiveKit's own active_speakers_changed
      |                                     signal as VAD, then:
      |
STTProvider.recognize()                 <- same interface/mocks as Task 011
      |
VoiceSessionService.record_event()      <- the EXACT method app/voice/router.py's
      |                                     POST /voice/sessions/{id}/events already
      |                                     calls - no second admissions brain
      |
AgentOrchestrator.handle_message()      <- unchanged since Task 006; all typed tools,
      |                                     RAG, lead/appointment/application/
      |                                     escalation logic, Conversation/Message
      |                                     persistence
      |
TTSProvider.synthesize()                <- same interface/mocks as Task 011
      |
room_client.publish_audio()             <- raw PCM16 frames -> LiveKit AudioSource
      |
LiveKit room -> student hears the agent
```

`app/voice/worker/dispatcher.py` (`WorkerDispatcher`) polls for `VoiceSession` rows using the `livekit` transport and runs one `RealtimeVoiceWorker` per session as an asyncio task - deliberately not LiveKit Agents' own job-dispatch protocol (docs/development.md section 5: don't add infrastructure with nothing to test it against here). `app/voice/worker/run.py` is the CLI entrypoint (`python -m app.voice.worker.run`).

## 73.2 Providers

- **STT/TTS/RealtimeTransport**: unchanged interfaces from Task 011/015 (`app/voice/providers/base.py`). `MockTTSProvider` now also returns real (synthetic, non-speech) PCM16 WAV `audio_bytes` - not just a duration estimate - so the worker's publish-into-LiveKit code path is exercised by tests without a paid vendor.
- **LLM** (`app/agent/providers/`): `LLMProvider`/`MockLLMProvider` already existed from Task 006, unused until now. Task 016 adds `AnthropicLLMProvider` (`app/agent/providers/anthropic.py`, selected via `AGENT_LLM_PROVIDER=anthropic` + `LLM_API_KEY`) and `app/agent/providers/factory.py::get_llm_provider()`, mirroring every other provider factory's fail-closed pattern. Implemented with `urllib.request` (already using PyJWT-not-livekit-api's reasoning from Task 015) rather than the `anthropic` SDK - one bounded JSON POST doesn't need it. A follow-up adds `GeminiLLMProvider` (`app/agent/providers/gemini.py`, selected via `AGENT_LLM_PROVIDER=gemini` + `GOOGLE_API_KEY`) behind the identical `LLMProvider` interface and the same factory fail-closed pattern, calling the Gemini `generateContent` REST endpoint with `urllib.request` rather than the `google-genai` SDK, for the same reason. Both real adapters are interchangeable from `AgentOrchestrator`'s point of view - only the factory selection differs.

## 73.3 Where the LLM is (and is not) used

**The LLM is never the source of truth for admissions facts.** `AgentOrchestrator` is unchanged for every intent that has a tool/template answer - fees, eligibility, scholarships, dates, documents, counselor availability, appointments, applications all come from tools/`prompts.py` exactly as before, regardless of which LLM provider is configured (see `tests/test_orchestrator_llm_fallback.py::test_llm_is_never_invoked_for_a_grounded_fee_question`, which configures a "lying" fake LLM and proves it is never even called for a fee question).

The LLM is consulted in exactly one place: `AgentOrchestrator._open_ended_reply()`, reached only when the deterministic intent detector matched nothing at all (genuinely open-ended input). With the default `AGENT_LLM_PROVIDER=mock`, this returns the pre-Task-016 static `prompts.unknown_fallback()` text verbatim - zero behavior change for every existing test. With a real provider configured, it asks the LLM to naturally acknowledge the input and steer toward a supported topic, under a system prompt (`prompts.open_ended_system_prompt`) that explicitly forbids stating any fact, number, date, or claiming an action succeeded. Any LLM failure/timeout falls back to the static template - the LLM can never block or break a turn.

Safety refusals (`out_of_scope`, `cross_tenant_refusal`, `injection_refusal`) are never routed through the LLM - they stay fully static regardless of configuration.

## 73.4 Turn-taking / VAD / barge-in

VAD is LiveKit's own `active_speakers_changed` room signal (translated into `on_speaking_started`/`on_speaking_stopped` by `room_client.py`), not a hand-rolled ML model - the transport server already computes this. Barge-in: a `speaking_started` callback while `VoiceSession.turn_state == SPEAKING` (checked via the existing `state_machine.is_barge_in()` from Task 011, not re-implemented) immediately signals the in-flight `publish_audio` loop to stop via an `asyncio.Event`, awaits it, then records an `interruption` event through the same `VoiceSessionService` used everywhere else - the state machine, TTS-cancel call, and audit logging are all the existing Task 011 code, unchanged.

## 73.5 Conversation memory

Unchanged from Task 006: `AgentState` persists on `Conversation.state` between turns. The worker doesn't add or need any new memory mechanism - `tests/test_voice_worker.py::test_conversation_memory_does_not_re_ask_for_known_course` drives "I want B.Tech CSE." then "I scored 82% in Class 12." through the worker and confirms the second turn doesn't re-ask for the course.

## 73.6 Tenant isolation

The LiveKit room name (`college-{college_id}-voice-{session_id}`, from Task 015's `room_name_for`) already prevents cross-tenant room collisions. The worker additionally only ever operates within the `CollegeContext` resolved from the `VoiceSession.college_id` it was dispatched for - the exact same tenant-scoping object every other channel uses, so RAG/tools/leads/appointments/applications are scoped identically. `tests/test_voice_worker.py` covers: two colleges' sessions mint tokens for different rooms, and a Nova session cannot retrieve a document ingested only for Aurora.

## 73.7 What was NOT live-tested (no real credentials/infrastructure available)

- No real LiveKit server was dialed. `app/voice/worker/room_client.py` (the `livekit.rtc` wrapper) is exercised only implicitly through `RealtimeVoiceWorker`'s tests, which substitute an in-memory `FakeRoomClient` - see `tests/test_voice_worker.py`'s module docstring.
- No real STT/TTS vendor was called - `MockSTTProvider`/`MockTTSProvider` throughout, as in every prior voice task.
- No real Anthropic API call was made - `tests/test_llm_provider.py` monkeypatches `urllib.request.urlopen` to verify request construction and response parsing without network access.
- Given the above, end-to-end audio quality, real-world STT accuracy, LiveKit reconnect timing, and Anthropic response latency/quality are unverified in this environment. The turn-taking, tenant isolation, tool-invocation, and fallback *logic* are verified against the real database and the real `AgentOrchestrator`.

## 73.8 Known limitations

- One dispatcher process, in-memory claim tracking (documented scope boundary, section above) - a multi-instance deployment needs a DB-level claim column, not a different `RealtimeVoiceWorker`.
- `VoiceSessionService` calls run synchronously on the worker's own asyncio task rather than via `asyncio.to_thread` - fine for one session per worker instance; a design serving many sessions per process should offload this.
- STT still processes a whole buffered utterance at once (`STTProvider.recognize`), not a true streaming/partial-transcript STT vendor integration - consistent with the interface Task 011 defined.

---

# 74. Task 017 Implementation Status (Addendum) - Real Gemini STT + TTS

Task 016 (section 73.7) left both `STTProvider` and `TTSProvider` unimplemented against a real vendor - only `MockSTTProvider`/`MockTTSProvider` existed. Task 017 adds real adapters for both, backed by the Gemini API, behind the exact same interfaces (`app/voice/providers/base.py`) every other provider already uses. Nothing about `VoiceSessionService`, `AgentOrchestrator`, `RealtimeVoiceWorker`, the LiveKit transport, tool contracts, RAG, leads, appointments, or applications changed - this is strictly two new adapters selected by configuration, per section 4's "provider-agnostic architecture" and section 60's "Voice Provider Abstraction".

## 74.1 What is implemented

- `app/voice/providers/gemini.py`: `GeminiSTTProvider` and `GeminiTTSProvider`, both calling the Gemini `generateContent` REST endpoint directly with `urllib` (no new SDK dependency), mirroring `app/agent/providers/gemini.py`'s existing LLM adapter exactly - `GOOGLE_API_KEY` is sent only in the `x-goog-api-key` header, never the URL, and is never logged.
- **STT**: `GeminiSTTProvider.recognize(audio_bytes, language=...)` wraps raw PCM16 audio (the shape `RealtimeVoiceWorker` buffers, and what the phone webhook's `audio_base64` decodes to) into a self-describing WAV container (reusing `app/voice/worker/pcm.py::pcm16_to_wav_bytes` - already-tested, no reimplementation) before sending it as Gemini `inlineData`, unless the input is already WAV-encoded (a `RIFF` header), in which case it is passed through unchanged. A language hint (`en`/`hi`/`hinglish`) is appended to the transcription prompt when known, but Gemini is instructed to transcribe verbatim in whatever language/mix was actually spoken - it never translates.
- **TTS**: `GeminiTTSProvider.synthesize(text, voice_id=...)` requests `responseModalities: ["AUDIO"]` with a configurable `voiceConfig.prebuiltVoiceConfig.voiceName`, decodes the returned base64 raw PCM16 audio, and wraps it into a WAV buffer at whatever sample rate Gemini's response `mimeType` declares (`audio/L16;codec=pcm;rate=...`) - so `TTSResult.audio_bytes` satisfies the exact same "valid WAV, 16-bit PCM" contract `MockTTSProvider` already produced, and `app/voice/worker/pcm.py::wav_bytes_to_pcm16` (used by the worker to publish into LiveKit) needs no changes at all.
- **Selection**: reuses the existing `STT_PROVIDER` / `TTS_PROVIDER` settings (Task 011) rather than introducing a second, competing provider-name setting - set either to `gemini` to activate the real adapter. `get_stt_provider()`/`get_tts_provider()` (`app/voice/providers/factory.py`) fail closed with `ResourceUnavailableError` if `gemini` is selected without `GOOGLE_API_KEY` configured, exactly like every other provider in this factory; `Settings.validate_for_production()` additionally fails application startup outright under the same condition when `APP_ENV=production`.
- **Runtime failures** (timeout, network error, HTTP error, malformed response, or a safety-blocked/empty-candidate response) raise `ResourceUnavailableError` - the same abstraction the voice layer already uses for every provider failure (see `app/services/voice.py`'s existing `except ResourceUnavailableError` around `get_tts_provider().synthesize(...)`, and the router/worker's existing handling of STT failures) - no new exception type was introduced. A genuinely empty transcript from a *well-formed* response (Gemini heard silence/no speech) is distinguished from an error: it returns `STTResult(text="")`, which flows into the existing "Sorry, I didn't catch that" path (section 39) rather than raising.
- **Safety**: empty/zero-length audio is never sent to the API - `recognize()` returns an empty result immediately. Raw audio that cannot be wrapped into a valid WAV also fails safe (empty result) rather than crashing a turn. Empty synthesis text is rejected before any request is made.

## 74.2 Configuration

```text
STT_PROVIDER=mock                       # "mock" (default) or "gemini"
TTS_PROVIDER=mock                       # "mock" (default) or "gemini"
GOOGLE_API_KEY=                         # required if either provider above is "gemini" (shared with AGENT_LLM_PROVIDER=gemini)
GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com   # shared with the Gemini LLM provider
GEMINI_STT_MODEL=gemini-3.6-flash        # gemini-2.5-flash was deprecated by Google; confirmed against the real API
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore
GEMINI_VOICE_TIMEOUT_SECONDS=8.0
```

## 74.3 What was NOT live-tested (no real API key available in this environment)

- No real call was made to the Gemini API. `tests/test_voice_gemini.py` monkeypatches `urllib.request.urlopen` throughout - request construction, response parsing, every failure mode, language handling, and a full realtime-worker turn (audio -> STT -> `AgentOrchestrator` -> TTS -> publish) are all verified against a fake network layer.
- `scripts/smoke_test_gemini_voice.py` is a manual, non-pytest script a developer runs locally with a real `GOOGLE_API_KEY` to confirm the adapters work against the live API (synthesizes a sample sentence, then transcribes it back). It prints only non-secret metadata (byte sizes, duration, recognized text) and refuses to run at all without a real key configured - see docs/development.md's Task 017 addendum for usage.
- Real-world transcription accuracy for Hindi/Hinglish code-switched speech, real TTS prosody/latency, and Gemini's actual voice-catalog behavior are therefore unverified in this environment; the request/response contract, error handling, and integration with the existing worker/orchestrator are verified.

