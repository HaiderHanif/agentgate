from __future__ import annotations

import json

from agentgate.assertions import Policy, Violation
from agentgate.recorder import record_run
from agentgate.replay import replay_run
from agentgate.reporting import (
    _sequence_diff,
    github_annotations,
    render_json,
    render_markdown,
    render_report,
    render_text,
)


def _pair(agent, regressed_agent, model_fn, tools):
    golden = record_run("refund", agent, model_fn, tools)
    observed = replay_run(golden, regressed_agent)
    return golden, observed, Policy().evaluate(golden, observed)


def test_sequence_diff_classifies_rows() -> None:
    rows = _sequence_diff(["a", "b"], ["a", "c", "d"])
    assert [status for status, _ in rows] == ["ok", "changed", "added"]

    rows = _sequence_diff(["a", "b"], ["a"])
    assert [status for status, _ in rows] == ["ok", "missing"]


def test_passing_report(agent, model_fn, tools) -> None:
    golden = record_run("refund", agent, model_fn, tools)
    observed = replay_run(golden, agent)
    report = render_text(golden, observed, [])

    assert "PASS" in report
    assert "3 tool calls matched" in report


def test_failing_report_shows_the_path(agent, regressed_agent, model_fn, tools) -> None:
    golden, observed, violations = _pair(agent, regressed_agent, model_fn, tools)
    report = render_text(golden, observed, violations)

    assert "FAIL" in report
    assert "tool_sequence" in report
    assert "issue_refund -> send_email" in report


def test_warnings_do_not_read_as_failures() -> None:
    from agentgate.trace import Trace

    warning = Violation(code="output_similarity", message="drifted", severity="warning")
    report = render_text(Trace(name="t"), Trace(name="t"), [warning])
    assert "WARN" in report


def test_markdown_report(agent, regressed_agent, model_fn, tools) -> None:
    golden, observed, violations = _pair(agent, regressed_agent, model_fn, tools)
    report = render_markdown(golden, observed, violations)

    assert report.startswith("### agentgate")
    assert "| step | status | tool |" in report


def test_json_report_is_machine_readable(agent, regressed_agent, model_fn, tools) -> None:
    golden, observed, violations = _pair(agent, regressed_agent, model_fn, tools)
    payload = json.loads(render_json(golden, observed, violations))

    assert payload["passed"] is False
    assert payload["golden"]["tool_sequence"][1] == "issue_refund"
    assert any(v["code"] == "tool_sequence" for v in payload["violations"])


def test_github_annotations() -> None:
    lines = github_annotations(
        [
            Violation(code="tool_sequence", message="diverged"),
            Violation(code="output_similarity", message="drifted", severity="warning"),
        ],
        file="traces/refund.json",
    ).splitlines()

    assert lines[0].startswith("::error file=traces/refund.json::")
    assert lines[1].startswith("::warning file=traces/refund.json::")


def test_unknown_format_is_rejected(agent, model_fn, tools) -> None:
    import pytest

    golden = record_run("refund", agent, model_fn, tools)
    with pytest.raises(ValueError, match="unknown report format"):
        render_report(golden, golden, [], "yaml")
