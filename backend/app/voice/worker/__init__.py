"""The realtime voice agent worker (Task 016).

A separate process (see app/voice/worker/run.py) that joins a LiveKit
room as the agent participant, performs speech recognition on the
student's published audio, drives the existing AgentOrchestrator through
VoiceSessionService (identical to the mock/phone channels - no second
admissions brain lives here), and publishes synthesized speech back into
the room. See docs/voice.md section 73 for the full design.
"""
