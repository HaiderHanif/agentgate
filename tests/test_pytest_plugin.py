"""Tests for the pytest plugin, run through pytest's own `pytester` fixture."""

from __future__ import annotations

import pytest

AGENT_MODULE = '''
from agentgate.trace import ModelResult

ORDER = {"id": "A-1042", "amount": 49.99, "email": "customer@example.com"}


def model_fn(prompt):
    return ModelResult(text="Approved.", model="gpt-4o-mini", input_tokens=10, output_tokens=5)


TOOLS = {
    "lookup_order": lambda order_id: {**ORDER, "id": order_id},
    "issue_refund": lambda order_id, amount: {"refund_id": "RF-1"},
    "send_email": lambda to: {"delivered": True},
}


def handle_refund(ctx):
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model("refund?")
    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
    ctx.tool("send_email", to=order["email"])
    return "Refunded. " + decision


def regressed(ctx):
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model("refund?")
    ctx.tool("send_email", to=order["email"])
    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
    return "Refunded. " + decision
'''


@pytest.fixture
def project(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makepyfile(demo_agent=AGENT_MODULE)
    pytester.makefile(".toml", pyproject='[tool.agentgate]\ntrace_dir = "traces"\n')
    return pytester


def test_missing_trace_skips_with_guidance(project: pytest.Pytester) -> None:
    project.makepyfile(
        test_gate="""
        from demo_agent import handle_refund

        def test_refund(agentgate):
            agentgate.assert_matches(handle_refund, "refund")
        """
    )
    result = project.runpytest("-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*no golden trace*"])


def test_update_records_then_test_passes(project: pytest.Pytester) -> None:
    project.makepyfile(
        test_gate="""
        from agentgate.pytest_plugin import LiveSpec
        from demo_agent import TOOLS, handle_refund, model_fn

        LIVE = LiveSpec(model_fn=model_fn, tools=TOOLS)

        def test_refund(agentgate):
            agentgate.assert_matches(handle_refund, "refund", live=LIVE)
        """
    )
    recorded = project.runpytest("--agentgate-update")
    recorded.assert_outcomes(passed=1)
    assert (project.path / "traces" / "refund.json").is_file()

    replayed = project.runpytest()
    replayed.assert_outcomes(passed=1)


def test_regression_fails_the_build(project: pytest.Pytester) -> None:
    project.makepyfile(
        test_gate="""
        from agentgate.pytest_plugin import LiveSpec
        from demo_agent import TOOLS, handle_refund, model_fn

        LIVE = LiveSpec(model_fn=model_fn, tools=TOOLS)

        def test_refund(agentgate):
            agentgate.assert_matches(handle_refund, "refund", live=LIVE)
        """
    )
    project.runpytest("--agentgate-update").assert_outcomes(passed=1)

    project.makepyfile(
        test_gate="""
        from demo_agent import regressed

        def test_refund(agentgate):
            agentgate.assert_matches(regressed, "refund")
        """
    )
    failed = project.runpytest()
    failed.assert_outcomes(failed=1)
    failed.stdout.fnmatch_lines(["*tool_sequence*"])


def test_trace_dir_option_overrides_config(project: pytest.Pytester) -> None:
    project.makepyfile(
        test_gate="""
        from agentgate.pytest_plugin import LiveSpec
        from demo_agent import TOOLS, handle_refund, model_fn

        LIVE = LiveSpec(model_fn=model_fn, tools=TOOLS)

        def test_refund(agentgate):
            agentgate.assert_matches(handle_refund, "refund", live=LIVE)
        """
    )
    project.runpytest("--agentgate-update", "--agentgate-dir", "custom").assert_outcomes(passed=1)
    assert (project.path / "custom" / "refund.json").is_file()


def test_update_without_live_spec_skips(project: pytest.Pytester) -> None:
    project.makepyfile(
        test_gate="""
        from demo_agent import handle_refund

        def test_refund(agentgate):
            agentgate.assert_matches(handle_refund, "refund")
        """
    )
    result = project.runpytest("--agentgate-update", "-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*no LiveSpec*"])
