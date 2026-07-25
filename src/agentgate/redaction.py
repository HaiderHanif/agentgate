"""Redaction of sensitive values before traces are written to disk.

Golden traces are committed to source control, so they must never carry
credentials or personal data. Redaction runs on the way *out* - the live run
still receives real values.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from agentgate.trace import ModelCall, ToolCall, Trace

REDACTED = "<redacted>"

DEFAULT_REDACT_KEYS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "client_secret",
    "credit_card",
    "card_number",
    "cvv",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "session_token",
    "ssn",
    "token",
)


def _matches(key: str, needles: Sequence[str]) -> bool:
    lowered = key.lower()
    return any(needle in lowered for needle in needles)


def redact_value(value: Any, keys: Sequence[str]) -> Any:
    """Recursively redact any mapping entry whose key looks sensitive."""
    if isinstance(value, dict):
        return {
            k: REDACTED if _matches(str(k), keys) else redact_value(v, keys)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, keys) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, keys) for item in value)
    return value


def redact_trace(trace: Trace, keys: Iterable[str] | None = None) -> Trace:
    """Return a copy of `trace` with sensitive tool arguments and results masked.

    Model prompts are never stored verbatim (only their digest), so model steps
    need no redaction beyond their response text, which is left intact - it is
    the agent's own output and is required for replay.
    """
    needles = [k.lower() for k in (keys if keys is not None else DEFAULT_REDACT_KEYS)]
    steps: list[ModelCall | ToolCall] = []
    for step in trace.steps:
        if isinstance(step, ToolCall):
            steps.append(
                step.model_copy(
                    update={
                        "arguments": redact_value(step.arguments, needles),
                        "result": redact_value(step.result, needles),
                    }
                )
            )
        else:
            steps.append(step)
    return trace.model_copy(update={"steps": steps})
