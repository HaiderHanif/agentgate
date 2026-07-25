from __future__ import annotations

from agentgate.redaction import REDACTED, redact_trace, redact_value
from agentgate.trace import ModelCall, ToolCall, Trace, load_trace, save_trace


def test_redacts_nested_keys() -> None:
    payload = {
        "user": {"name": "Ada", "api_key": "sk-live-123"},
        "items": [{"password": "hunter2", "qty": 3}],
    }
    cleaned = redact_value(payload, ["api_key", "password"])

    assert cleaned["user"]["name"] == "Ada"
    assert cleaned["user"]["api_key"] == REDACTED
    assert cleaned["items"][0]["password"] == REDACTED
    assert cleaned["items"][0]["qty"] == 3


def test_matches_substrings() -> None:
    cleaned = redact_value({"stripe_secret_key": "x"}, ["secret"])
    assert cleaned["stripe_secret_key"] == REDACTED


def test_redacts_tool_arguments_and_results() -> None:
    trace = Trace(
        name="t",
        steps=[
            ToolCall(index=0, name="charge", arguments={"token": "tok_1"}, result={"secret": "s"}),
            ModelCall(index=1, response_text="kept"),
        ],
    )
    cleaned = redact_trace(trace)

    assert cleaned.tool_calls[0].arguments["token"] == REDACTED
    assert cleaned.tool_calls[0].result["secret"] == REDACTED
    assert cleaned.model_calls[0].response_text == "kept"


def test_save_redacts_by_default(tmp_path) -> None:
    trace = Trace(name="t", steps=[ToolCall(index=0, name="c", arguments={"api_key": "sk-1"})])
    path = save_trace(trace, tmp_path / "t.json")

    assert "sk-1" not in path.read_text(encoding="utf-8")
    assert load_trace(path).tool_calls[0].arguments["api_key"] == REDACTED


def test_redaction_can_be_disabled(tmp_path) -> None:
    trace = Trace(name="t", steps=[ToolCall(index=0, name="c", arguments={"api_key": "sk-1"})])
    path = save_trace(trace, tmp_path / "t.json", redact=[])
    assert "sk-1" in path.read_text(encoding="utf-8")
