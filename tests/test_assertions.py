from __future__ import annotations

import pytest

from agentgate.assertions import (
    Policy,
    check_cost_ceiling,
    check_forbidden_tools,
    check_latency_budget,
    check_no_tool_errors,
    check_output_similarity,
    check_required_tools,
    check_step_count,
    check_tool_arguments,
    check_tool_sequence,
    has_errors,
)
from agentgate.recorder import record_run
from agentgate.replay import replay_run
from agentgate.trace import ModelCall, ToolCall, Trace


@pytest.fixture
def golden(agent, model_fn, tools):
    return record_run("refund", agent, model_fn, tools)


def test_matching_run_has_no_violations(golden, agent) -> None:
    observed = replay_run(golden, agent)
    assert Policy().evaluate(golden, observed) == []


def test_reordered_tools_are_caught(golden, regressed_agent) -> None:
    observed = replay_run(golden, regressed_agent)
    violations = check_tool_sequence(golden, observed)

    assert [v.code for v in violations] == ["tool_sequence"]
    assert violations[0].expected == ["lookup_order", "issue_refund", "send_email"]


def test_changed_arguments_are_caught() -> None:
    golden = Trace(name="t", steps=[ToolCall(index=0, name="pay", arguments={"amount": 10})])
    observed = Trace(name="t", steps=[ToolCall(index=0, name="pay", arguments={"amount": 999})])

    assert [v.code for v in check_tool_arguments(golden, observed)] == ["tool_arguments"]
    assert check_tool_arguments(golden, observed, ignore=["amount"]) == []


def test_required_and_forbidden_tools() -> None:
    observed = Trace(name="t", steps=[ToolCall(index=0, name="send_email")])

    assert check_required_tools(observed, ["issue_refund"])[0].code == "required_tool_missing"
    assert check_required_tools(observed, ["send_email"]) == []
    assert check_forbidden_tools(observed, ["send_email"])[0].code == "forbidden_tool_called"
    assert check_forbidden_tools(observed, ["drop_database"]) == []


def test_tool_errors_are_caught() -> None:
    observed = Trace(name="t", steps=[ToolCall(index=0, name="pay", error="TimeoutError: gateway")])
    assert check_no_tool_errors(observed)[0].code == "tool_error"


def test_cost_and_latency_budgets() -> None:
    observed = Trace(
        name="t",
        steps=[ModelCall(index=0, cost_usd=0.20, latency_ms=4000)],
    )
    assert check_cost_ceiling(observed, 0.05)[0].code == "cost_ceiling"
    assert check_cost_ceiling(observed, 1.00) == []
    assert check_latency_budget(observed, 1000)[0].code == "latency_budget"
    assert check_latency_budget(observed, 9000) == []


def test_step_count_tolerance() -> None:
    golden = Trace(name="t", steps=[ToolCall(index=0, name="a")])
    observed = Trace(
        name="t",
        steps=[ToolCall(index=i, name="a") for i in range(5)],
    )
    assert check_step_count(golden, observed)[0].code == "step_count"
    assert check_step_count(golden, observed, tolerance=10) == []


def test_output_similarity_tolerates_rewording() -> None:
    golden = Trace(name="t", final_output="Refunded $49.99 for order A-1042.")
    reworded = Trace(name="t", final_output="Refunded $49.99 for order A-1042!")
    unrelated = Trace(name="t", final_output="I could not help with that request.")

    assert check_output_similarity(golden, reworded) == []
    assert check_output_similarity(golden, unrelated)[0].code == "output_similarity"


def test_similarity_can_be_downgraded_to_a_warning() -> None:
    golden = Trace(name="t", final_output="one thing")
    observed = Trace(name="t", final_output="something entirely different")

    violations = check_output_similarity(golden, observed, severity="warning")
    assert not has_errors(violations)


def test_policy_reports_every_violation_at_once(golden, regressed_agent) -> None:
    observed = replay_run(golden, regressed_agent)
    policy = Policy(required_tools=["audit_log"], forbidden_tools=["send_email"], max_cost_usd=0.0)

    codes = {v.code for v in policy.evaluate(golden, observed)}
    assert {"tool_sequence", "required_tool_missing", "forbidden_tool_called"} <= codes


def test_policy_checks_can_be_switched_off(golden, regressed_agent) -> None:
    observed = replay_run(golden, regressed_agent)
    relaxed = Policy(tool_sequence=False, output_similarity=None)
    assert relaxed.evaluate(golden, observed) == []
