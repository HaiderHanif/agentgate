from __future__ import annotations

from agentgate.trace import ModelCall, ToolCall, Trace, load_trace, save_trace


def build_trace() -> Trace:
    return Trace(
        name="sample",
        agent="demo",
        steps=[
            ModelCall(index=0, model="test", response_text="call lookup", cost_usd=0.001),
            ToolCall(index=1, name="lookup_order", arguments={"order_id": "A-1"}, result={"ok": True}),
        ],
        final_output="done",
    )


def test_tool_sequence_and_totals() -> None:
    trace = build_trace()
    assert trace.tool_sequence == ["lookup_order"]
    assert trace.total_cost_usd == 0.001
    assert len(trace.model_calls) == 1


def test_round_trip(tmp_path) -> None:
    path = save_trace(build_trace(), tmp_path / "sample.json")
    reloaded = load_trace(path)
    assert reloaded.name == "sample"
    assert reloaded.tool_sequence == ["lookup_order"]
    assert isinstance(reloaded.steps[1], ToolCall)
