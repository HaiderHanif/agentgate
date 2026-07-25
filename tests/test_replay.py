from __future__ import annotations

from typing import Any

import pytest

from agentgate.exceptions import ReplayError
from agentgate.recorder import record_run
from agentgate.replay import replay_run


def test_replay_reproduces_the_run(agent, model_fn, tools) -> None:
    golden = record_run("refund", agent, model_fn, tools)
    observed = replay_run(golden, agent)

    assert observed.tool_sequence == golden.tool_sequence
    assert observed.final_output == golden.final_output


def test_replay_is_free_and_deterministic(agent, model_fn, tools) -> None:
    calls = {"n": 0}

    def counting_model(prompt: str) -> str:
        calls["n"] += 1
        return "never reached"

    golden = record_run("refund", agent, model_fn, tools)
    first = replay_run(golden, agent)
    second = replay_run(golden, agent)

    assert calls["n"] == 0
    assert first.tool_sequence == second.tool_sequence
    assert first.total_latency_ms == 0.0


def test_unknown_tool_arguments_are_a_finding(agent, model_fn, tools) -> None:
    golden = record_run("refund", agent, model_fn, tools)

    def changed_agent(ctx: Any) -> str:
        ctx.tool("lookup_order", order_id="DIFFERENT")
        return ""

    with pytest.raises(ReplayError, match="no recorded result"):
        replay_run(golden, changed_agent)


def test_non_strict_mode_matches_by_tool_name(agent, model_fn, tools) -> None:
    golden = record_run("refund", agent, model_fn, tools)

    def changed_agent(ctx: Any) -> str:
        order = ctx.tool("lookup_order", order_id="DIFFERENT")
        return str(order["amount"])

    observed = replay_run(golden, changed_agent, strict=False)
    assert observed.tool_sequence == ["lookup_order"]


def test_extra_model_calls_are_a_finding(agent, model_fn, tools) -> None:
    golden = record_run("refund", agent, model_fn, tools)

    def chatty_agent(ctx: Any) -> str:
        ctx.model("one")
        ctx.model("two")
        return ""

    with pytest.raises(ReplayError, match="more model calls"):
        replay_run(golden, chatty_agent)


def test_reordering_replays_but_diverges(agent, regressed_agent, model_fn, tools) -> None:
    """The regression is legal to replay - which is exactly why it needs asserting."""
    golden = record_run("refund", agent, model_fn, tools)
    observed = replay_run(golden, regressed_agent)

    assert observed.tool_sequence == ["lookup_order", "send_email", "issue_refund"]
    assert observed.tool_sequence != golden.tool_sequence
