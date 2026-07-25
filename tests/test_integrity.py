from __future__ import annotations

import pytest

from agentgate.integrity import (
    SIGNING_KEY_ENV,
    IntegrityError,
    fingerprint,
    is_signed,
    sign_trace,
    verify_trace,
)
from agentgate.trace import ToolCall, Trace

KEY = "test-signing-key"


def _trace(amount: float = 49.99) -> Trace:
    return Trace(
        name="refund",
        steps=[ToolCall(index=0, name="issue_refund", arguments={"amount": amount})],
        final_output="done",
    )


def test_signing_round_trip() -> None:
    signed = sign_trace(_trace(), KEY)

    assert is_signed(signed)
    verify_trace(signed, KEY)


def test_unsigned_trace_is_rejected() -> None:
    with pytest.raises(IntegrityError, match="not signed"):
        verify_trace(_trace(), KEY)


def test_tampering_is_detected() -> None:
    """The trace-poisoning attack: rewrite the baseline so bad behaviour passes."""
    signed = sign_trace(_trace(49.99), KEY)
    poisoned = signed.model_copy(
        update={
            "steps": [
                ToolCall(index=0, name="issue_refund", arguments={"amount": 10_000})
            ]
        }
    )

    with pytest.raises(IntegrityError, match="modified after signing"):
        verify_trace(poisoned, KEY)


def test_wrong_key_is_rejected() -> None:
    signed = sign_trace(_trace(), KEY)
    with pytest.raises(IntegrityError, match="invalid"):
        verify_trace(signed, "attacker-key")


def test_forged_signature_is_rejected() -> None:
    signed = sign_trace(_trace(), KEY)
    forged = signed.model_copy(
        update={"metadata": {**signed.metadata, "signature": "0" * 64}}
    )
    with pytest.raises(IntegrityError, match="invalid"):
        verify_trace(forged, KEY)


def test_fingerprint_ignores_incidental_metadata() -> None:
    trace = _trace()
    annotated = trace.model_copy(update={"metadata": {"reviewed_by": "haider"}})
    assert fingerprint(trace) == fingerprint(annotated)


def test_fingerprint_tracks_behaviour() -> None:
    assert fingerprint(_trace(49.99)) != fingerprint(_trace(50.00))


def test_key_falls_back_to_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, KEY)
    verify_trace(sign_trace(_trace()))


def test_missing_key_is_an_error(monkeypatch) -> None:
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    with pytest.raises(IntegrityError, match="no signing key"):
        sign_trace(_trace())
