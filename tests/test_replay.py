from __future__ import annotations

import pytest

from agentgate.recorder import record_run
from agentgate.replay import ReplayError, replay_run


def model_fn(prompt: str) -> str:
    return "refund it"


TOOLS = {
    "lookup_order": lambda order_id: {"id": order_id, "amount": 40},
    "issue_refund": lambda order_id, amount: {"refunded": amount},
    "send_email": lambda to: {"sent": to},
}


def good_agent(ctx) -> str:
    ctx.model("what should I do?")
    order = ctx.tool("lookup_order", order_id="A-1")
    ctx.tool("issue_refund", order_id="A-1", amount=order["amount"])
    ctx.tool("send_email", to="customer@example.com")
    return "Refund issued and customer notified."


def test_replay_is_deterministic_and_free() -> None:
    golden = record_run("refund_flow", good_agent, model_fn, TOOLS)
    observed = replay_run(golden, good_agent)
    assert observed.tool_sequence == golden.tool_sequence
    assert observed.total_latency_ms == 0.0


def test_unknown_tool_arguments_raise() -> None:
    golden = record_run("refund_flow", good_agent, model_fn, TOOLS)

    def drifted_agent(ctx) -> str:
        ctx.model("what should I do?")
        ctx.tool("lookup_order", order_id="DIFFERENT")
        return "done"

    with pytest.raises(ReplayError):
        replay_run(golden, drifted_agent)
