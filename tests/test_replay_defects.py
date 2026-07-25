"""Regression tests for the six false-green paths in the replay engine.

Every test here corresponds to a defect that was reproduced against a release
build. All six shared one shape: the run completed, the policy passed, and the
reported result was wrong. That is the only bug class that genuinely matters in
a regression gate, because nobody investigates a green build.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentgate.exceptions import ReplayError
from agentgate.replay import ReplayContext, ReplayedToolError, replay_run
from agentgate.trace import ModelCall, ToolCall, Trace


# --------------------------------------------------------------------------- #
# Ordering of repeated calls
# --------------------------------------------------------------------------- #


def test_repeated_identical_calls_replay_in_recorded_order() -> None:
    """A polling loop was untestable: both calls returned the final result."""
    golden = Trace(
        name="poll",
        steps=[
            ToolCall(index=0, name="poll", arguments={"id": 1}, result="pending"),
            ToolCall(index=1, name="poll", arguments={"id": 1}, result="complete"),
        ],
    )

    def agent(ctx: Any) -> str:
        return f"{ctx.tool('poll', id=1)},{ctx.tool('poll', id=1)}"

    assert replay_run(golden, agent).final_output == "pending,complete"


def test_exhausting_recorded_occurrences_is_a_divergence() -> None:
    golden = Trace(
        name="poll",
        steps=[ToolCall(index=0, name="poll", arguments={"id": 1}, result="pending")],
    )

    def greedy(ctx: Any) -> str:
        ctx.tool("poll", id=1)
        ctx.tool("poll", id=1)
        return ""

    with pytest.raises(ReplayError, match="no recorded result"):
        replay_run(golden, greedy)


# --------------------------------------------------------------------------- #
# Recorded failures
# --------------------------------------------------------------------------- #


def _failing_trace() -> Trace:
    return Trace(
        name="flaky",
        steps=[
            ToolCall(
                index=0,
                name="charge",
                arguments={},
                result=None,
                error="TimeoutError: upstream timed out",
            )
        ],
    )


def test_recorded_failure_is_raised_not_returned() -> None:
    """A recorded outage used to replay as a clean success returning None."""
    context = ReplayContext(_failing_trace())

    with pytest.raises(ReplayedToolError, match="upstream timed out"):
        context.tool("charge")


def test_recorded_failure_appears_in_the_observed_trace() -> None:
    context = ReplayContext(_failing_trace())

    with pytest.raises(ReplayedToolError):
        context.tool("charge")

    failed = context.observed.failed_tool_calls
    assert len(failed) == 1
    assert failed[0].error == "TimeoutError: upstream timed out"


def test_an_agent_may_handle_a_recorded_failure() -> None:
    """Error-handling paths become testable, which was the point."""

    def resilient(ctx: Any) -> str:
        try:
            ctx.tool("charge")
        except ReplayedToolError:
            return "fell back"
        return "charged"

    assert replay_run(_failing_trace(), resilient).final_output == "fell back"


# --------------------------------------------------------------------------- #
# Completeness
# --------------------------------------------------------------------------- #


def _two_model_trace() -> Trace:
    return Trace(
        name="think",
        steps=[
            ModelCall(index=0, response_text="first"),
            ModelCall(index=1, response_text="second"),
        ],
    )


def test_skipping_recorded_model_calls_fails_strict_replay() -> None:
    """A two-model golden trace used to pass with zero model calls."""

    def lazy(ctx: Any) -> str:
        return "done"

    with pytest.raises(ReplayError, match="did not make"):
        replay_run(_two_model_trace(), lazy)


def test_skipping_recorded_tool_calls_fails_strict_replay() -> None:
    golden = Trace(
        name="refund",
        steps=[
            ToolCall(index=0, name="lookup", result={}),
            ToolCall(index=1, name="issue_refund", result={}),
        ],
    )

    def partial(ctx: Any) -> str:
        ctx.tool("lookup")
        return "stopped early"

    with pytest.raises(ReplayError, match="issue_refund"):
        replay_run(golden, partial)


def test_non_strict_replay_still_allows_partial_paths() -> None:
    """Non-strict mode exists to explore refactors; failing there breaks it."""

    def lazy(ctx: Any) -> str:
        return "done"

    observed = replay_run(_two_model_trace(), lazy, strict=False)
    assert observed.final_output == "done"


def test_consuming_every_step_passes() -> None:
    def thorough(ctx: Any) -> str:
        return ctx.model("a") + ctx.model("b")

    assert replay_run(_two_model_trace(), thorough).final_output == "firstsecond"


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #


def test_agent_mutation_cannot_rewrite_the_golden_trace() -> None:
    """Agent code editing a nested result used to change the expectation itself."""
    golden = Trace(
        name="t",
        steps=[ToolCall(index=0, name="lookup", result={"nested": {"n": 1}})],
    )

    def vandal(ctx: Any) -> str:
        payload = ctx.tool("lookup")
        payload["nested"]["n"] = 99
        return "done"

    replay_run(golden, vandal)

    assert golden.tool_calls[0].result == {"nested": {"n": 1}}


def test_extra_tool_stubs_are_also_isolated() -> None:
    stub = {"count": 1}
    golden = Trace(name="t", steps=[ToolCall(index=0, name="lookup", result={})])

    def agent(ctx: Any) -> str:
        ctx.tool("lookup")
        ctx.tool("audit")["count"] = 99
        return "done"

    replay_run(golden, agent, extra_tools={"audit": stub})

    assert stub == {"count": 1}


# --------------------------------------------------------------------------- #
# Diagnostics must not leak
# --------------------------------------------------------------------------- #


def test_divergence_message_redacts_credentials() -> None:
    """A strict miss printed live arguments straight into the CI log."""
    golden = Trace(name="t", steps=[ToolCall(index=0, name="charge", result={})])

    def agent(ctx: Any) -> str:
        ctx.tool("charge", api_key="sk-live-supersecretvalue", password="hunter2")
        return ""

    with pytest.raises(ReplayError) as caught:
        replay_run(golden, agent)

    message = str(caught.value)
    assert "sk-live-supersecretvalue" not in message
    assert "hunter2" not in message
    assert "charge" in message
