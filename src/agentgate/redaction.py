"""Redaction of sensitive values before traces are written to disk.

Golden traces are committed to source control, so they must never carry
credentials or personal data. Redaction runs on the way *out* - the live run
still receives real values.

Two mechanisms, because one is not enough:

1. **By key** - any mapping entry whose key looks sensitive (`api_key`,
   `password`). Precise, and the right tool for structured arguments.
2. **By value** - patterns that match a secret wherever it appears in free
   text. Necessary because the likeliest place for a card number to leak is the
   sentence the agent wrote, or an exception message, neither of which has a key.

Tool *arguments* are redacted by key only. Rewriting free text inside arguments
would change what the agent is recorded as having asked for, and replay matches
on arguments.

This is a best-effort control that reduces the blast radius of a mistake. It is
not a compliance boundary. Do not record traces against production data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
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

# Deliberately conservative. Email addresses and phone numbers are excluded:
# they are frequently load-bearing in a trace, and masking them by default would
# break more runs than it protects. Use OutputPolicy(forbid_pii=...) to *detect*
# those instead of silently rewriting them.
SENSITIVE_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{16,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    "private_key": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
}


def _matches(key: str, needles: Sequence[str]) -> bool:
    lowered = key.lower()
    return any(needle in lowered for needle in needles)


def resolve_keys(keys: Iterable[str] | None) -> list[str]:
    """Combine caller-supplied keys with the secure defaults.

    Custom keys **augment** the defaults rather than replacing them. Replacement
    was the earlier behaviour and it was a trap: adding `customer_email` to the
    list silently stopped masking `password`, `token` and `api_key`. Widening a
    redaction list should never narrow it.

    Disabling redaction is still possible, but it has to be deliberate - pass an
    empty sequence, which callers handle before reaching here.
    """
    if keys is None:
        return [k.lower() for k in DEFAULT_REDACT_KEYS]
    return sorted({k.lower() for k in DEFAULT_REDACT_KEYS} | {k.lower() for k in keys})


def redact_text(text: str, patterns: Mapping[str, re.Pattern[str]] | None = None) -> str:
    """Mask secrets that appear inside free text."""
    active = SENSITIVE_VALUE_PATTERNS if patterns is None else patterns
    result = text
    for kind, pattern in active.items():
        result = pattern.sub(f"<redacted:{kind}>", result)
    return result


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


def redact_strings(value: Any) -> Any:
    """Recursively apply value-pattern redaction to every string in a structure."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_strings(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_strings(item) for item in value)
    return value


def redact_trace(trace: Trace, keys: Iterable[str] | None = None) -> Trace:
    """Return a copy of `trace` with sensitive values masked.

    Covered: tool arguments (by key), tool results, tool error messages, model
    response text, the final output, and trace metadata.

    Exception text earns particular attention. It is free-form, rarely reviewed,
    and routinely contains an authorization header, a URL with a token in the
    query string, a response body, or a customer record.

    Passing an explicit empty sequence disables redaction entirely, which is
    occasionally right for a trace that never leaves the machine.
    """
    if keys is not None and not list(keys):
        return trace

    needles = resolve_keys(keys)
    steps: list[ModelCall | ToolCall] = []
    for step in trace.steps:
        if isinstance(step, ToolCall):
            steps.append(
                step.model_copy(
                    update={
                        "arguments": redact_value(step.arguments, needles),
                        "result": redact_strings(redact_value(step.result, needles)),
                        "error": redact_text(step.error) if step.error else step.error,
                    }
                )
            )
        else:
            steps.append(
                step.model_copy(update={"response_text": redact_text(step.response_text)})
            )
    return trace.model_copy(
        update={
            "steps": steps,
            "final_output": redact_text(trace.final_output),
            "metadata": redact_strings(redact_value(trace.metadata, needles)),
        }
    )
