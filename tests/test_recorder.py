from __future__ import annotations

from typing import Any

import pytest

from agentgate.recorder import LiveContext, Recorder, record_run
from agentgate.trace import ModelResult, load_trace


def test_record_run_captures_path(agent, model_fn, tools) -> None:
    trace = record_run("refund", agent, model_fn, tools)

    assert trace.tool_sequence == ["lookup_order", "issue_refund", "send_email"]
    assert len(trace.model_calls) == 1
    assert trace.final_output.startswith("Refunded $49.99")


def test_costs_are_priced_automatically(agent, model_fn, tools) -> None:
    trace = record_run("refund", agent, model_fn, tools)
    # gpt-4o-mini: 120 in @ $0.15/Mtok + 20 out @ $0.60/Mtok
    assert trace.total_cost_usd == pytest.approx(0.000030, abs=1e-9)


def test_explicit_cost_is_respected() -> None:
    recorder = Recorder("t")
    recorder.record_model_call("p", ModelResult(text="x", model="gpt-4o", cost_usd=1.25))
    assert recorder.trace.total_cost_usd == 1.25


def test_plain_string_model_fn_is_supported(tools) -> None:
    def agent(ctx: Any) -> str:
        return ctx.model("hello")

    trace = record_run("plain", agent, lambda prompt: "hi there", tools)
    assert trace.model_calls[0].response_text == "hi there"
    assert trace.total_cost_usd == 0.0


def test_unknown_tool_raises(model_fn, tools) -> None:
    context = LiveContext(model_fn, tools, Recorder("t"))
    with pytest.raises(KeyError, match="unknown tool"):
        context.tool("not_a_tool")


def test_tool_errors_are_recorded_then_raised(model_fn) -> None:
    def explode() -> None:
        raise ValueError("boom")

    recorder = Recorder("t")
    context = LiveContext(model_fn, {"explode": explode}, recorder)

    with pytest.raises(ValueError, match="boom"):
        context.tool("explode")

    assert recorder.trace.failed_tool_calls[0].error == "ValueError: boom"


def test_record_run_writes_to_disk(agent, model_fn, tools, tmp_path) -> None:
    record_run("refund", agent, model_fn, tools, trace_dir=tmp_path)
    assert load_trace(tmp_path / "refund.json").tool_sequence[0] == "lookup_order"
