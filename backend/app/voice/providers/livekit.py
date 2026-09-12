"""Real LiveKit realtime transport adapter (docs/voice.md section 60, Task 015).

Generates spec-compliant LiveKit access tokens (https://docs.livekit.io/home/get-started/authentication/)
directly with PyJWT - already a backend dependency for the platform's own
JWT auth (app/auth) - rather than adding the `livekit-api`/`livekit-agents`
SDKs and their aiohttp/protobuf dependency tree merely to mint a JWT
(docs/development.md section 55: avoid a new dependency when an existing
one already does the job). The token shape below (HS256, `sub`/`iss`/
`nbf`/`exp` claims plus a `video` grants object with lowerCamelCase keys)
is byte-for-byte what LiveKit's own server SDKs produce.

LIVEKIT_API_SECRET signs tokens here, server-side, and is never returned
to a caller or logged. The browser only ever receives the short-lived
signed token plus LIVEKIT_URL (a server address, not a credential).
"""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.voice.providers.base import RealtimeTransportProvider, TransportCredentials

logger = logging.getLogger("app.voice.livekit")


def room_name_for(*, college_id: str, session_id: str) -> str:
    """College id is embedded in the room name itself so a token can
    never be replayed to join a room belonging to a different tenant's
    session, even if the raw session_id were guessed. Public because the
    realtime worker (app/voice/worker/) needs to derive the exact same
    room name to join the session's room as a second (agent) participant."""
    return f"college-{college_id}-voice-{session_id}"


# Backward-compatible alias (Task 015 named this privately; kept so any
# existing import site/tests keep working unchanged).
_room_name = room_name_for


def mint_access_token(
    *, api_key: str, api_secret: str, identity: str, room: str, ttl_seconds: int,
    can_publish: bool = True, can_subscribe: bool = True,
) -> tuple[str, datetime]:
    """Builds one spec-compliant LiveKit access token. Public so both the
    student's browser credential (LiveKitTransportProvider below) and the
    worker's own server-identity credential (app/voice/worker/) share
    exactly one JWT-construction implementation."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    claims = {
        "sub": identity,
        "iss": api_key,
        "jti": uuid.uuid4().hex,
        "nbf": calendar.timegm(now.utctimetuple()),
        "exp": calendar.timegm(expires_at.utctimetuple()),
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": True,
        },
    }
    token = jwt.encode(claims, api_secret, algorithm="HS256")
    return token, expires_at


_build_access_token = mint_access_token


class LiveKitTransportProvider(RealtimeTransportProvider):
    """Web voice realtime transport backed by a real LiveKit server/cloud
    project. Only issues the room-join credential; the media path itself
    (actual WebRTC audio frames) is the browser LiveKit client's and the
    LiveKit server's job once connected - see docs/voice.md section 71
    for what remains provider-dependent."""

    name = "livekit"

    def __init__(self, *, url: str, api_key: str, api_secret: str, ttl_seconds: int):
        if not (url and api_key and api_secret):
            raise ValueError("LiveKitTransportProvider requires url, api_key, and api_secret.")
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._ttl_seconds = ttl_seconds

    def create_session(self, *, session_id: str, college_id: str, metadata: dict) -> TransportCredentials:
        room = room_name_for(college_id=college_id, session_id=session_id)
        identity = f"student-{session_id}"
        token, expires_at = mint_access_token(
            api_key=self._api_key, api_secret=self._api_secret,
            identity=identity, room=room, ttl_seconds=self._ttl_seconds,
        )
        logger.info("voice.livekit_token_issued session_id=%s college_id=%s room=%s", session_id, college_id, room)
        return TransportCredentials(
            provider_session_id=room,
            connection_token=token,
            expires_at=expires_at,
            ice_servers=[],
            server_url=self._url,
        )

    def close_session(self, provider_session_id: str) -> None:
        """Best-effort only (mirrors TTSProvider.cancel's contract) - room
        deletion is not implemented here since it would require the
        `livekit-api` RoomServiceClient; an empty LiveKit room closes on
        its own via the server's configured empty_timeout, so leaving it
        to expire naturally is a safe default rather than a gap masked
        by a fake success."""
        logger.info("voice.livekit_session_close_requested provider_session_id=%s", provider_session_id)
