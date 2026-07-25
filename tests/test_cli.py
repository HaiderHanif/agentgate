"""CLI tests.

Each test runs in an isolated temporary project so that entrypoint resolution
and configuration discovery are exercised for real, not mocked.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentgate.cli import EXIT_OK, EXIT_USAGE, EXIT_VIOLATIONS, app
from agentgate.recorder import record_run
from agentgate.trace import save_trace

runner = CliRunner()

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
def project(tmp_path, monkeypatch):
    """An isolated project directory containing a recordable agent module."""
    (tmp_path / "demo_agent.py").write_text(AGENT_MODULE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == EXIT_OK
    assert "agentgate" in result.stdout


def test_init_creates_trace_dir(project) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == EXIT_OK
    assert (project / "traces").is_dir()
    assert "tool.agentgate" in result.stdout


def test_record_then_list_then_show(project) -> None:
    recorded = runner.invoke(
        app,
        [
            "record",
            "demo_agent:handle_refund",
            "--model",
            "demo_agent:model_fn",
            "--tools",
            "demo_agent:TOOLS",
            "--name",
            "refund",
            "--dir",
            "traces",
        ],
    )
    assert recorded.exit_code == EXIT_OK
    assert (project / "traces" / "refund.json").is_file()

    listed = runner.invoke(app, ["list", "--dir", "traces"])
    assert listed.exit_code == EXIT_OK
    assert "refund" in listed.stdout

    shown = runner.invoke(app, ["show", "traces/refund.json"])
    assert shown.exit_code == EXIT_OK
    assert "issue_refund" in shown.stdout


def test_verify_passes_for_unchanged_agent(project) -> None:
    runner.invoke(
        app,
        [
            "record",
            "demo_agent:handle_refund",
            "--model",
            "demo_agent:model_fn",
            "--tools",
            "demo_agent:TOOLS",
            "--name",
            "refund",
            "--dir",
            "traces",
        ],
    )
    result = runner.invoke(app, ["verify", "demo_agent:handle_refund", "traces/refund.json"])

    assert result.exit_code == EXIT_OK
    assert "PASS" in result.stdout


def test_verify_fails_for_regressed_agent(project) -> None:
    runner.invoke(
        app,
        [
            "record",
            "demo_agent:handle_refund",
            "--model",
            "demo_agent:model_fn",
            "--tools",
            "demo_agent:TOOLS",
            "--name",
            "refund",
            "--dir",
            "traces",
        ],
    )
    result = runner.invoke(app, ["verify", "demo_agent:regressed", "traces/refund.json"])

    assert result.exit_code == EXIT_VIOLATIONS
    assert "tool_sequence" in result.stdout


def test_verify_json_report_is_written(project) -> None:
    runner.invoke(
        app,
        [
            "record",
            "demo_agent:handle_refund",
            "--model",
            "demo_agent:model_fn",
            "--tools",
            "demo_agent:TOOLS",
            "--name",
            "refund",
            "--dir",
            "traces",
        ],
    )
    result = runner.invoke(
        app,
        [
            "verify",
            "demo_agent:regressed",
            "traces/refund.json",
            "--format",
            "json",
            "--report",
            "out/report.json",
        ],
    )

    assert result.exit_code == EXIT_VIOLATIONS
    payload = json.loads((project / "out" / "report.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False


def test_verify_rejects_unknown_agent(project) -> None:
    trace = record_run(
        "empty",
        lambda ctx: "",
        lambda prompt: "",
        {},
    )
    save_trace(trace, project / "traces" / "empty.json")

    result = runner.invoke(app, ["verify", "demo_agent:nope", "traces/empty.json"])
    assert result.exit_code == EXIT_USAGE


def test_list_without_traces_dir(project) -> None:
    result = runner.invoke(app, ["list", "--dir", "nowhere"])
    assert result.exit_code == EXIT_USAGE
