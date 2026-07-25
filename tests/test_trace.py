from __future__ import annotations

import pytest

from agentgate.exceptions import TraceFormatError
from agentgate.trace import (
    SCHEMA_VERSION,
    ModelCall,
    ToolCall,
    Trace,
    digest,
    load_trace,
    reindex,
    save_trace,
)


def test_digest_ignores_key_order() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_digest_detects_value_change() -> None:
    assert digest({"a": 1}) != digest({"a": 2})


def test_trace_aggregates() -> None:
    trace = Trace(
        name="t",
        steps=[
            ToolCall(index=0, name="lookup", arguments={"id": 1}, latency_ms=10),
            ModelCall(index=1, cost_usd=0.002, input_tokens=100, output_tokens=25, latency_ms=90),
            ToolCall(index=2, name="refund", latency_ms=5),
        ],
    )
    assert trace.tool_sequence == ["lookup", "refund"]
    assert trace.total_cost_usd == 0.002
    assert trace.total_tokens == 125
    assert trace.total_latency_ms == 105
    assert trace.summary()["tool_calls"] == 2


def test_failed_tool_calls() -> None:
    trace = Trace(name="t", steps=[ToolCall(index=0, name="pay", error="ValueError: nope")])
    assert len(trace.failed_tool_calls) == 1


def test_reindex_renumbers() -> None:
    steps = [ToolCall(index=9, name="a"), ToolCall(index=4, name="b")]
    assert [s.index for s in reindex(steps)] == [0, 1]


def test_round_trip(tmp_path) -> None:
    trace = Trace(
        name="round",
        agent="demo",
        steps=[ToolCall(index=0, name="lookup", arguments={"id": "A-1"}, result={"ok": True})],
        final_output="done",
    )
    path = save_trace(trace, tmp_path / "round.json")
    loaded = load_trace(path)

    assert loaded.name == "round"
    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.tool_calls[0].arguments == {"id": "A-1"}
    assert loaded.final_output == "done"


def test_load_rejects_malformed(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(TraceFormatError):
        load_trace(path)


def test_load_rejects_unknown_schema(tmp_path) -> None:
    path = tmp_path / "future.json"
    path.write_text('{"schema_version": "99.0", "name": "x"}', encoding="utf-8")
    with pytest.raises(TraceFormatError, match="schema version"):
        load_trace(path)


def test_load_missing_file(tmp_path) -> None:
    with pytest.raises(TraceFormatError):
        load_trace(tmp_path / "nope.json")
