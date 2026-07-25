from __future__ import annotations

from agentgate.assertions import Policy, check_forbidden_tools, check_tool_sequence
from agentgate.recorder import record_run
from agentgate.replay import replay_run
from agentgate.trace import Trace


def model_fn(prompt: str) -> str:
    return "proceed"


TOOLS = {
    "lookup_order": lambda order_id: {"id": order_id, "amount": 40},
    "issue_refund": lambda order_id, amount: {"refunded": amount},
    "send_email": lambda to: {"sent": to},
}


def correct_agent(ctx) -> str:
    ctx.model("plan")
    order = ctx.tool("lookup_order", order_id="A-1")
    ctx.tool("issue_refund", order_id="A-1", amount=order["amount"])
    ctx.tool("send_email", to="customer@example.com")
    return "Refund issued and customer notified."


def regressed_agent(ctx) -> str:
    """Emails the customer *before* the refund actually happens."""
    ctx.model("plan")
    order = ctx.tool("lookup_order", order_id="A-1")
    ctx.tool("send_email", to="customer@example.com")
    ctx.tool("issue_refund", order_id="A-1", amount=order["amount"])
    return "Refund issued and customer notified."


def golden() -> Trace:
    return record_run("refund_flow", correct_agent, model_fn, TOOLS)


def test_clean_run_has_no_violations() -> None:
    reference = golden()
    observed = replay_run(reference, correct_agent)
    assert Policy().evaluate(reference, observed) == []


def test_reordered_tools_are_caught() -> None:
    reference = golden()
    observed = replay_run(reference, regressed_agent)
    violations = check_tool_sequence(reference, observed)
    assert len(violations) == 1
    assert violations[0].code == "tool_sequence"


def test_forbidden_tool_detection() -> None:
    reference = golden()
    observed = replay_run(reference, correct_agent)
    violations = check_forbidden_tools(observed, ["send_email"])
    assert violations and violations[0].code == "forbidden_tool_called"


def test_cost_ceiling_and_similarity() -> None:
    reference = golden()
    observed = replay_run(reference, correct_agent)
    policy = Policy(max_cost_usd=0.0, output_similarity=1.0)
    assert policy.evaluate(reference, observed) == []
