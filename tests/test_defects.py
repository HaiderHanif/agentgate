"""Regression tests for defects found in the full-module audit.

Each test here corresponds to a bug that shipped. Several of them describe
checks that reported success while being incapable of failing, which is the
failure mode this project exists to argue against - so they are worth keeping
named and visible rather than folded into the general suites.
"""

from __future__ import annotations

import datetime as dt
import random
import time
from typing import Any

import pytest
from pydantic import ValidationError

from agentgate.assertions import Policy, check_pricing_coverage
from agentgate.constraints import ArgumentConstraint, OutputPolicy
from agentgate.determinism import deterministic
from agentgate.normalize import Normalizer
from agentgate.redaction import REDACTED, redact_trace
from agentgate.replay import replay_run
from agentgate.trace import ModelCall, ToolCall, Trace


# --------------------------------------------------------------------------- #
# Checks that could not fire
# --------------------------------------------------------------------------- #


def test_unknown_pii_kind_is_rejected() -> None:
    """A hyphen instead of an underscore used to disable the check silently."""
    with pytest.raises(ValidationError):
        OutputPolicy(forbid_pii=["credit-card"])


def test_known_pii_kinds_are_still_accepted() -> None:
    policy = OutputPolicy(forbid_pii=["credit_card", "ssn"])
    assert policy.forbid_pii == ["credit_card", "ssn"]


def test_bad_output_regex_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        OutputPolicy(must_match=["(unclosed"])
    with pytest.raises(ValidationError):
        OutputPolicy(must_not_match=["(unclosed"])


def test_bad_argument_regex_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        ArgumentConstraint(tool="t", path="p", matches="(unclosed")


def test_bad_normalizer_regex_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        Normalizer(custom={"order": "(unclosed"})


def test_unpriced_model_makes_a_cost_ceiling_meaningless() -> None:
    trace = Trace(
        name="t",
        steps=[
            ModelCall(index=0, model="internal-llm", input_tokens=100_000, output_tokens=50_000)
        ],
    )
    findings = check_pricing_coverage(trace)

    assert findings[0].code == "cost_unpriced"
    assert findings[0].severity == "warning"
    assert "internal-llm" in str(findings[0].actual)


def test_pricing_coverage_is_reported_only_when_a_ceiling_exists() -> None:
    trace = Trace(
        name="t",
        steps=[ModelCall(index=0, model="internal-llm", input_tokens=10, output_tokens=10)],
    )
    base = {"tool_sequence": False, "tool_arguments": False, "output_similarity": None}

    assert Policy(**base).evaluate(trace, trace) == []
    gated = Policy(**base, max_cost_usd=1.0).evaluate(trace, trace)
    assert [v.code for v in gated] == ["cost_unpriced"]


# --------------------------------------------------------------------------- #
# Privacy
# --------------------------------------------------------------------------- #


def test_final_output_is_redacted() -> None:
    """The agent's own sentence is where a card number actually leaks."""
    trace = Trace(name="t", final_output="Refunded card 4111111111111111 today.")
    assert "4111111111111111" not in redact_trace(trace).final_output


def test_model_response_text_is_redacted() -> None:
    trace = Trace(name="t", steps=[ModelCall(index=0, response_text="SSN 123-45-6789 verified")])
    assert "123-45-6789" not in redact_trace(trace).model_calls[0].response_text


def test_tool_results_are_redacted_by_value_not_only_by_key() -> None:
    trace = Trace(
        name="t",
        steps=[ToolCall(index=0, name="lookup", result={"note": "ssn 123-45-6789"})],
    )
    assert "123-45-6789" not in str(redact_trace(trace).tool_calls[0].result)


def test_explicit_empty_key_list_disables_redaction_entirely() -> None:
    trace = Trace(name="t", final_output="SSN 123-45-6789")
    assert redact_trace(trace, []).final_output == "SSN 123-45-6789"


def test_redacted_arguments_remain_replayable() -> None:
    """Privacy and testability used to be in direct conflict here.

    The golden trace on disk holds `<redacted>`; the live agent passes the real
    key. Before the fix the digests never matched and strict replay was
    impossible for any flow that touched a credential.
    """
    golden = Trace(
        name="t",
        steps=[
            ToolCall(
                index=0,
                name="charge",
                arguments={"api_key": "sk-live-realvalue", "amount": 10},
                result={"ok": True},
            )
        ],
    )
    saved = redact_trace(golden)
    assert saved.tool_calls[0].arguments["api_key"] == REDACTED

    def agent(ctx: Any) -> str:
        return str(ctx.tool("charge", api_key="sk-live-realvalue", amount=10))

    observed = replay_run(saved, agent)
    assert observed.tool_sequence == ["charge"]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_elapsed_clocks_advance_so_timeout_loops_terminate() -> None:
    """A frozen monotonic clock turns any timeout loop into an infinite one."""
    with deterministic():
        start = time.monotonic()
        iterations = 0
        while time.monotonic() - start < 0.05:
            iterations += 1
            assert iterations < 100_000, "monotonic clock is not advancing"

    assert iterations > 0


def test_elapsed_clocks_are_still_reproducible() -> None:
    def run() -> list[float]:
        with deterministic():
            return [time.monotonic() for _ in range(5)]

    assert run() == run()


def test_wall_clock_stays_frozen() -> None:
    with deterministic(frozen_time="2026-07-25T09:00:00Z"):
        assert time.time() == time.time()


def test_datetime_now_is_frozen() -> None:
    """datetime.now() is the most common clock in agent code, and was untouched."""
    with deterministic(frozen_time="2026-07-25T09:00:00Z"):
        first = dt.datetime.now()
        second = dt.datetime.now()

    assert first == second
    assert (first.year, first.month, first.day) == (2026, 7, 25)


def test_datetime_patch_is_unwound() -> None:
    original = dt.datetime
    with deterministic():
        assert dt.datetime is not original
    assert dt.datetime is original


def test_random_state_is_restored_even_if_the_body_raises() -> None:
    random.seed(4321)
    before = random.random()

    random.seed(4321)
    with pytest.raises(RuntimeError):
        with deterministic(seed=11):
            raise RuntimeError("boom")

    assert random.random() == before


# --------------------------------------------------------------------------- #
# False positives
# --------------------------------------------------------------------------- #


def test_normalizer_applies_to_output_similarity() -> None:
    """A timestamp in the final sentence used to fail the build on its own."""
    golden = Trace(name="t", final_output="Refund RF-1 completed at 2026-07-25T09:00:00Z")
    observed = Trace(name="t", final_output="Refund RF-1 completed at 2026-07-26T11:30:00Z")
    base = {"tool_sequence": False, "tool_arguments": False, "output_similarity": 0.99}

    assert [v.code for v in Policy(**base).evaluate(golden, observed)] == ["output_similarity"]
    assert Policy(**base, normalize=Normalizer()).evaluate(golden, observed) == []
