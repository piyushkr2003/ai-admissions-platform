"""Twilio phone-voice adapter (minimum viable integration for a live demo).

Two distinct pieces, both behind the existing provider-abstraction
pattern (docs/voice.md section 60) - neither touches the browser voice
flow (LiveKit/mock transports), Groq, or AgentOrchestrator:

1. `generate_twiml()` - the XML Twilio's inbound-call webhook expects
   back, telling it to open a bidirectional Media Stream to our
   WebSocket endpoint (app/voice/twilio_stream.py).
2. `verify_twilio_signature()` - real Twilio request-signature
   validation (HMAC-SHA1 over the request URL + sorted form params,
   using TWILIO_AUTH_TOKEN), per Twilio's documented algorithm
   (https://www.twilio.com/docs/usage/security#validating-requests).
   This needs the full request URL, which `TelephonyProvider.verify_webhook()`
   (headers + raw_body only) has no way to supply - see
   `TwilioTelephonyProvider.verify_webhook`'s docstring for why that
   narrower method is best-effort here rather than the primary check
   (used directly by the TwiML route instead, which has the real URL).

`TwilioTelephonyProvider` still implements the shared `TelephonyProvider`
interface (parse_inbound_payload -> InboundCallEvent) so it fits the same
adapter pattern `SharedSecretTelephonyProvider` (app/voice/providers/mock.py)
already uses and can be selected via `get_telephony_provider()` - but the
new TwiML + Media Streams flow (app/voice/router.py's
/twilio/incoming + /twilio/stream) is what a real Twilio call actually
drives; the generic JSON telephony webhook this interface was designed
around is not Twilio's real wire format (form-encoded webhooks, XML
responses, no JSON audio_base64 events).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from xml.sax.saxutils import escape

from app.voice.providers.base import InboundCallEvent, TelephonyProvider

logger = logging.getLogger("app.voice.twilio")


def generate_twiml(stream_url: str) -> str:
    """The exact TwiML Twilio's inbound-call webhook must return to open
    a bidirectional Media Stream to `stream_url` (a `wss://` URL) for the
    duration of the call. `<Connect><Stream>` (rather than `<Start><Stream>`)
    is used deliberately: it makes the stream the primary call leg, so the
    call ends when the stream closes - the right behavior for a fully
    AI-driven call with no separate <Dial>/<Gather> verb alongside it."""
    safe_url = escape(stream_url, {'"': "&quot;"})
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f'<Stream url="{safe_url}"/>'
        "</Connect>"
        "</Response>"
    )


def compute_twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's documented request-signature algorithm: HMAC-SHA1(auth_token,
    url + "".join(sorted_key + value for each POST param)), base64-encoded.
    `params` must be the form-decoded POST body (empty for a GET/no-body
    validation)."""
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_twilio_signature(*, auth_token: str, url: str, params: dict[str, str], signature: str | None) -> bool:
    if not auth_token or not signature:
        # Never pretend an unconfigured or signature-less request is authenticated.
        return False
    expected = compute_twilio_signature(auth_token, url, params)
    return hmac.compare_digest(expected, signature)


class TwilioTelephonyProvider(TelephonyProvider):
    name = "twilio"

    def __init__(self, auth_token: str):
        self._auth_token = auth_token

    def verify_webhook(self, *, headers: dict, raw_body: bytes) -> bool:
        # Twilio's real signature scheme needs the exact request URL and
        # the form-decoded params, neither of which this interface method
        # receives (see module docstring) - the actual inbound-call route
        # (app/voice/router.py) calls verify_twilio_signature() directly,
        # where it has both. This override exists only so
        # TwilioTelephonyProvider satisfies the shared TelephonyProvider
        # contract for factory registration; it intentionally fails
        # closed (never authenticates) rather than approximate a weaker
        # check that could be mistaken for the real one.
        logger.warning(
            "voice.twilio_verify_webhook_generic_path_unsupported "
            "reason=use_verify_twilio_signature_with_the_real_request_url_instead"
        )
        return False

    def parse_inbound_payload(self, payload: dict) -> InboundCallEvent:
        # Twilio's own webhook fields (CallSid/From/To), for callers that
        # go through the generic telephony event shape rather than the
        # Media Streams WebSocket directly.
        return InboundCallEvent(
            call_id=str(payload.get("CallSid") or payload.get("call_id") or ""),
            from_number=payload.get("From") or payload.get("from_number"),
            to_number=payload.get("To") or payload.get("to_number"),
            event_type=str(payload.get("event_type") or "call_started"),
            text=payload.get("text"),
            audio_base64=payload.get("audio_base64"),
            language=payload.get("language"),
        )
