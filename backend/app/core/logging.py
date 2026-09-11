"""Structured logging configuration.

Logs are emitted as single-line key=value structured records so they remain
greppable in local development and parseable by log aggregators in
production. Secrets (passwords, tokens, API keys) must never be passed to
these loggers.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="ts=%(asctime)s level=%(levelname)s request_id=%(request_id)s "
        "logger=%(name)s msg=%(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root.handlers.clear()
    root.addHandler(handler)


def sanitize_for_log(data: dict) -> dict:
    """Redact known-sensitive keys before logging a dict of context data."""
    return {
        key: ("***" if key.lower() in _SENSITIVE_KEYS else value)
        for key, value in data.items()
    }
