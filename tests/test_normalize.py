from __future__ import annotations

from agentgate.normalize import Normalizer


def test_uuids_are_stabilised() -> None:
    left = Normalizer().text("req 3f2504e0-4f89-11d3-9a0c-0305e82c3301 ok")
    right = Normalizer().text("req 6ba7b810-9dad-11d1-80b4-00c04fd430c8 ok")
    assert left == right == "req <uuid> ok"


def test_timestamps_are_stabilised() -> None:
    assert Normalizer().text("at 2026-07-25T09:00:00Z") == "at <timestamp>"


def test_signed_url_parameters_are_stripped() -> None:
    url = "https://cdn.example.com/f.pdf?expires=1790000000&signature=abc123"
    normalized = Normalizer().text(url)

    assert "abc123" not in normalized
    assert "redacted-signature" in normalized


def test_custom_patterns() -> None:
    normalizer = Normalizer(custom={"order": r"ORD-\d+"})
    assert normalizer.text("see ORD-99123") == "see <order>"


def test_rules_are_opt_out() -> None:
    kept = Normalizer(uuids=False).text("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    assert kept.startswith("3f2504e0")


def test_nested_structures() -> None:
    payload = {"ids": [{"trace": "3f2504e0-4f89-11d3-9a0c-0305e82c3301"}], "n": 3}
    assert Normalizer().value(payload) == {"ids": [{"trace": "<uuid>"}], "n": 3}


def test_normalized_arguments_stop_false_positives() -> None:
    from agentgate.assertions import check_tool_arguments
    from agentgate.trace import ToolCall, Trace

    def trace(request_id: str) -> Trace:
        return Trace(
            name="t",
            steps=[
                ToolCall(index=0, name="charge", arguments={"ref": f"req-{request_id}"})
            ],
        )

    golden = trace("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    observed = trace("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    assert check_tool_arguments(golden, observed)  # noisy without normalisation
    assert check_tool_arguments(golden, observed, normalizer=Normalizer()) == []
