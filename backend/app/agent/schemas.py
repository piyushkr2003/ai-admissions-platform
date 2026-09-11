"""Shared agent-tool result contract (docs/agent-tools.md section 9,
docs/api-contract.md section 37): every tool returns the same envelope
shape so the orchestrator can handle success/failure uniformly."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError:
    code: str
    message: str


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None

    @staticmethod
    def ok(data: dict[str, Any]) -> "ToolResult":
        return ToolResult(success=True, data=data, error=None)

    @staticmethod
    def fail(code: str, message: str) -> "ToolResult":
        return ToolResult(success=False, data=None, error=ToolError(code=code, message=message))


@dataclass
class ToolCallRecord:
    """Auditable record of one tool invocation within a turn (docs/agent-tools.md section 57)."""

    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
