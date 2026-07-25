"""The example, wired into pytest exactly as a real project would do it."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentgate import Policy, load_trace, replay_run
from examples.refund_agent.agent import refund_agent, regressed_refund_agent

GOLDEN = Path(__file__).parent / "traces" / "refund_flow.json"

POLICY = Policy(
    required_tools=["lookup_order", "issue_refund"],
    forbidden_tools=["delete_customer"],
    max_cost_usd=0.05,
)


def test_correct_agent_matches_golden_trace() -> None:
    golden = load_trace(GOLDEN)
    observed = replay_run(golden, refund_agent)
    assert POLICY.evaluate(golden, observed) == []


def test_regressed_agent_is_rejected() -> None:
    golden = load_trace(GOLDEN)
    observed = replay_run(golden, regressed_refund_agent)
    violations = POLICY.evaluate(golden, observed)
    assert any(v.code == "tool_sequence" for v in violations)


@pytest.mark.golden("refund_flow")
def test_via_plugin(agentgate) -> None:
    agentgate.trace_dir = GOLDEN.parent
    agentgate.assert_matches(refund_agent, "refund_flow", POLICY)
