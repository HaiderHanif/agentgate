"""Coverage for the trace data model.

Every other module depends on this one. Three areas earn direct tests rather
than incidental ones:

* `digest()` - decides whether replay finds a recorded tool call at all. If it
  were sensitive to key order, strict replay would fail at random.
* The aggregate properties - every cost and latency assertion reads them.
* `load_trace()` rejection paths - a trace that cannot be trusted must not be
  loaded quietly.
"""

from __future__ import annotations

import json

import pytest

from agentgate.exceptions import TraceFormatError
from agentgate.trace import (
    SCHEMA_VERSION,
    ModelCall,
    ModelResult,
    ToolCall,
    Trace,
    digest,
    load_trace,
    reindex,
    save_trace,
)


# --------------------------------------------------------------------------- #
# digest
# --------------------------------------------------------------------------- #


def test_digest_ignores_key_order() -> None:
    """Replay looks calls up by argument digest, so insertion order must not matter."""
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_digest_distinguishes_values() -> None:
    assert digest({"amount": 49.99}) != digest({"amount": 10_000})


def test_digest_is_short_and_stable() -> None:
    first = digest({"order_id": "A-1042"})

    assert len(first) == 12
    assert first == digest({"order_id": "A-1042"})


def test_digest_survives_unserialisable_values() -> None:
    """An object with no JSON form must not crash a recording."""
    assert len(digest({"when": object()})) == 12


# --------------------------------------------------------------------------- #
# Model result
# --------------------------------------------------------------------------- #


def test_model_result_defaults_are_cost_free() -> None:
    result = ModelResult(text="hello")

    assert (result.model, result.input_tokens, result.output_tokens) == ("unknown", 0, 0)
    assert result.cost_usd is None


# --------------------------------------------------------------------------- #
# Aggregates
# --------------------------------------------------------------------------- #


def _mixed_trace() -> Trace:
    return Trace(
        name="refund",
        agent="examples:handle_refund",
        steps=[
            ToolCall(index=0, name="lookup_order", arguments={"id": "A-1"}, latency_ms=12.5),
            ModelCall(
                index=1,
                model="gpt-4o-mini",
                input_tokens=400,
                output_tokens=40,
                cost_usd=0.0001,
                latency_ms=300.25,
            ),
            ToolCall(index=2, name="issue_refund", latency_ms=7.25),
            ToolCall(index=3, name="send_email", error="SMTP timeout"),
        ],
        final_output="Refunded.",
    )


def test_steps_split_by_kind() -> None:
    trace = _mixed_trace()

    assert len(trace.tool_calls) == 3
    assert len(trace.model_calls) == 1


def test_tool_sequence_is_the_decision_path() -> None:
    assert _mixed_trace().tool_sequence == ["lookup_order", "issue_refund", "send_email"]


def test_failed_tool_calls_are_isolated() -> None:
    failed = _mixed_trace().failed_tool_calls

    assert [call.name for call in failed] == ["send_email"]


def test_cost_and_token_totals_come_from_model_calls_only() -> None:
    trace = _mixed_trace()

    assert trace.total_cost_usd == 0.0001
    assert trace.total_tokens == 440


def test_latency_total_includes_every_step() -> None:
    assert _mixed_trace().total_latency_ms == 320.0


def test_an_empty_trace_aggregates_to_zero() -> None:
    empty = Trace(name="empty")

    assert (empty.total_cost_usd, empty.total_tokens, empty.total_latency_ms) == (0, 0, 0)
    assert empty.tool_sequence == []


def test_summary_is_machine_readable() -> None:
    summary = _mixed_trace().summary()

    assert summary["name"] == "refund"
    assert summary["steps"] == 4
    assert summary["tool_calls"] == 3
    assert summary["model_calls"] == 1
    assert summary["tool_sequence"] == ["lookup_order", "issue_refund", "send_email"]
    assert summary["total_tokens"] == 440


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def test_json_is_diff_friendly() -> None:
    """Traces are reviewed in pull requests, so formatting is a feature."""
    payload = _mixed_trace().to_json()

    assert payload.endswith("\n")
    assert json.loads(payload)["schema_version"] == SCHEMA_VERSION


def test_reindex_renumbers_to_position() -> None:
    steps = [
        ToolCall(index=99, name="a"),
        ToolCall(index=7, name="b"),
        ModelCall(index=3),
    ]

    assert [step.index for step in reindex(steps)] == [0, 1, 2]


def test_reindex_does_not_mutate_the_input() -> None:
    original = ToolCall(index=99, name="a")
    reindex([original])

    assert original.index == 99


def test_round_trip_preserves_step_types() -> None:
    path = save_trace(_mixed_trace(), "nested/dir/trace.json", redact=[])
    loaded = load_trace(path)

    assert isinstance(loaded.steps[0], ToolCall)
    assert isinstance(loaded.steps[1], ModelCall)
    assert loaded.tool_sequence == ["lookup_order", "issue_refund", "send_email"]
    assert loaded.final_output == "Refunded."


def test_save_creates_missing_directories(tmp_path) -> None:
    target = tmp_path / "a" / "b" / "c.json"
    written = save_trace(Trace(name="t"), target)

    assert written.exists()


# --------------------------------------------------------------------------- #
# Rejection paths
# --------------------------------------------------------------------------- #


def test_missing_file_is_reported_clearly(tmp_path) -> None:
    with pytest.raises(TraceFormatError, match="could not read"):
        load_trace(tmp_path / "absent.json")


def test_invalid_json_is_rejected(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(TraceFormatError, match="malformed trace"):
        load_trace(path)


def test_structurally_wrong_trace_is_rejected(tmp_path) -> None:
    """Valid JSON, wrong shape - a missing required field must not load as empty."""
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"steps": []}), encoding="utf-8")

    with pytest.raises(TraceFormatError, match="malformed trace"):
        load_trace(path)


def test_unknown_schema_version_is_refused(tmp_path) -> None:
    """Reading a future format with today's semantics would silently misinterpret it."""
    path = tmp_path / "future.json"
    payload = json.loads(Trace(name="t").to_json())
    payload["schema_version"] = "9.9"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TraceFormatError, match="schema version"):
        load_trace(path)
