"""The gate itself. Three lines of test for a whole class of silent failure."""

from __future__ import annotations

import pytest

from agentgate import Policy
from agentgate.pytest_plugin import GoldenTraceMismatch
from examples.refund_agent.agent import LIVE, handle_refund, handle_refund_regressed

POLICY = Policy(
    required_tools=["issue_refund"],
    max_cost_usd=0.01,
    output_similarity=0.85,
)


def test_refund_flow_is_unchanged(agentgate):
    """Passes: the agent takes exactly the decision path that was recorded."""
    agentgate.trace_dir = agentgate.trace_dir  # honours --agentgate-dir
    agentgate.assert_matches(handle_refund, "refund_flow", POLICY, live=LIVE)


def test_reordering_is_caught(agentgate):
    """Fails loudly: the customer would be emailed before the money moved."""
    if agentgate.update:
        pytest.skip("nothing to assert while re-recording")

    with pytest.raises(GoldenTraceMismatch) as excinfo:
        agentgate.assert_matches(handle_refund_regressed, "refund_flow", POLICY)

    assert "tool_sequence" in str(excinfo.value)
