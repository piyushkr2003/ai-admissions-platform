"""Turn-taking / barge-in state machine (docs/voice.md sections 15-17).

Encoding this as an explicit transition table - rather than scattered
`if session.status == ...` checks throughout the event handler - is
what lets barge-in be verified directly: a "speech_started" event while
the machine is in SPEAKING is defined, in one place, to interrupt.
"""
from __future__ import annotations

IDLE = "idle"
LISTENING = "listening"
PROCESSING = "processing"
SPEAKING = "speaking"

VOICE_TURN_STATES = (IDLE, LISTENING, PROCESSING, SPEAKING)

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    IDLE: {LISTENING},
    LISTENING: {PROCESSING, IDLE, LISTENING},
    PROCESSING: {SPEAKING, IDLE},
    SPEAKING: {LISTENING, IDLE, SPEAKING},
}

# Events that, on their own, are defined to interrupt the machine out of
# SPEAKING - i.e. barge-in - rather than being rejected as an invalid
# transition attempt.
BARGE_IN_EVENTS = {"speech_started", "interruption"}


def is_allowed_transition(current: str, new: str) -> bool:
    return new in _ALLOWED_TRANSITIONS.get(current, set())


def is_barge_in(current: str, event_type: str) -> bool:
    """True when this event interrupts audio the agent is currently
    (believed to be) speaking."""
    return current == SPEAKING and event_type in BARGE_IN_EVENTS


def next_state(current: str, event_type: str) -> str | None:
    """Returns the resulting turn_state for a given event, or None if
    the event is not meaningful in the current state (caller should
    leave turn_state unchanged rather than error - not every event
    forces a transition, e.g. a partial_transcript while LISTENING)."""
    mapping = {
        "speech_started": LISTENING,
        "interruption": LISTENING,
        "partial_transcript": LISTENING,
        "final_transcript": PROCESSING,
        "speech_stopped": LISTENING,
        "agent_response_ready": SPEAKING,
        "agent_response_complete": IDLE,
        "client_disconnect": IDLE,
    }
    target = mapping.get(event_type)
    if target is None:
        return None
    if not is_allowed_transition(current, target) and current != target:
        # Barge-in and same-state repeats are allowed by the table above;
        # anything else falling through is a no-op rather than an error,
        # since voice events can arrive slightly out of the "ideal" order
        # (e.g. a stray partial_transcript after processing has begun).
        return None
    return target
