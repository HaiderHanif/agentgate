"""Trace signing, so a golden trace cannot be quietly rewritten.

A golden trace is a security control: it defines what "correct" means. An
attacker who can edit one can make broken behaviour look approved and the CI
check becomes cover rather than protection.

Signing does not replace code review and CODEOWNERS on the trace directory - it
makes tampering detectable when those fail.

    export AGENTGATE_SIGNING_KEY=...
    agentgate sign traces/refund_flow.json
    agentgate verify app:agent traces/refund_flow.json --require-signature
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

from agentgate.exceptions import AgentGateError
from agentgate.trace import Trace

SIGNING_KEY_ENV = "AGENTGATE_SIGNING_KEY"
FINGERPRINT_FIELD = "fingerprint"
SIGNATURE_FIELD = "signature"


class IntegrityError(AgentGateError):
    """A trace failed its integrity check."""


def fingerprint(trace: Trace) -> str:
    """Content hash of everything that defines behaviour.

    Deliberately excludes `created_at` and `metadata`, so re-signing or adding a
    note does not change the fingerprint. Steps and final output do.
    """
    payload = {
        "schema_version": trace.schema_version,
        "name": trace.name,
        "agent": trace.agent,
        "steps": [step.model_dump(mode="json") for step in trace.steps],
        "final_output": trace.final_output,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_key(key: str | None = None) -> str:
    """Return the signing key, falling back to the environment."""
    resolved = key or os.environ.get(SIGNING_KEY_ENV)
    if not resolved:
        raise IntegrityError(
            f"no signing key; pass one explicitly or set {SIGNING_KEY_ENV}"
        )
    return resolved


def sign_trace(trace: Trace, key: str | None = None) -> Trace:
    """Return a copy of `trace` carrying a fingerprint and HMAC signature."""
    resolved = resolve_key(key)
    digest_value = fingerprint(trace)
    signature = hmac.new(
        resolved.encode("utf-8"), digest_value.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    metadata = {
        **trace.metadata,
        FINGERPRINT_FIELD: digest_value,
        SIGNATURE_FIELD: signature,
    }
    return trace.model_copy(update={"metadata": metadata})


def is_signed(trace: Trace) -> bool:
    return SIGNATURE_FIELD in trace.metadata


def verify_trace(trace: Trace, key: str | None = None) -> None:
    """Raise :class:`IntegrityError` unless the trace is intact and correctly signed."""
    if not is_signed(trace):
        raise IntegrityError(f"trace {trace.name!r} is not signed")

    resolved = resolve_key(key)
    current = fingerprint(trace)
    recorded = str(trace.metadata.get(FINGERPRINT_FIELD, ""))

    if not hmac.compare_digest(current, recorded):
        raise IntegrityError(
            f"trace {trace.name!r} was modified after signing "
            f"(fingerprint {recorded[:12]} -> {current[:12]})"
        )

    expected = hmac.new(
        resolved.encode("utf-8"), current.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, str(trace.metadata.get(SIGNATURE_FIELD, ""))):
        raise IntegrityError(
            f"signature on trace {trace.name!r} is invalid for the supplied key"
        )
