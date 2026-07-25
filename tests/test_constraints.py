from __future__ import annotations

from agentgate.constraints import (
    ArgumentConstraint,
    Ordering,
    OutputPolicy,
    UnorderedGroup,
)
from agentgate.trace import ModelCall, ToolCall, Trace


def _trace(names: list[str], **kwargs) -> Trace:
    steps = [ToolCall(index=i, name=n) for i, n in enumerate(names)]
    return Trace(name="t", steps=steps, **kwargs)


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def test_ordering_passes_when_respected() -> None:
    rule = Ordering(first="issue_refund", second="send_email")
    assert rule.check(_trace(["lookup", "issue_refund", "send_email"])) == []


def test_ordering_fails_when_reversed() -> None:
    rule = Ordering(first="issue_refund", second="send_email")
    violations = rule.check(_trace(["send_email", "issue_refund"]))

    assert violations[0].code == "ordering"
    assert "before" in violations[0].message


def test_ordering_survives_unrelated_refactors() -> None:
    """Adding, removing, and reordering other tools must not fire the rule."""
    rule = Ordering(first="issue_refund", second="send_email")
    reshuffled = _trace(["audit", "lookup", "issue_refund", "metrics", "send_email"])
    assert rule.check(reshuffled) == []


def test_ordering_is_silent_when_a_tool_is_absent() -> None:
    rule = Ordering(first="issue_refund", second="send_email")
    assert rule.check(_trace(["lookup", "send_email"])) == []


def test_unordered_group_accepts_any_order() -> None:
    group = UnorderedGroup(tools=["check_inventory", "check_payment", "check_shipping"])

    assert group.check(_trace(["check_shipping", "check_inventory", "check_payment"])) == []
    assert group.check(_trace(["check_inventory"]))[0].code == "unordered_group"


# --------------------------------------------------------------------------- #
# Argument constraints
# --------------------------------------------------------------------------- #


def _refund(amount: float) -> Trace:
    return Trace(
        name="t",
        steps=[ToolCall(index=0, name="issue_refund", arguments={"amount": amount})],
    )


def test_amount_ceiling_catches_the_catastrophic_argument() -> None:
    """Correct tool, correct order, ruinous value. Sequence checks miss this."""
    constraint = ArgumentConstraint(tool="issue_refund", path="amount", less_or_equal=500)

    assert constraint.check(_refund(49.99)) == []
    violations = constraint.check(_refund(10_000))
    assert violations[0].code == "argument_constraint"
    assert violations[0].actual == 10_000


def test_nested_paths() -> None:
    trace = Trace(
        name="t",
        steps=[
            ToolCall(
                index=0,
                name="charge",
                arguments={"payload": {"total": {"cents": 4999}}},
            )
        ],
    )
    constraint = ArgumentConstraint(tool="charge", path="payload.total.cents", less_than=10_000)
    assert constraint.check(trace) == []


def test_missing_argument_is_reported_only_when_required() -> None:
    present = ArgumentConstraint(tool="issue_refund", path="currency")
    optional = ArgumentConstraint(tool="issue_refund", path="currency", required=False)

    assert present.check(_refund(10))[0].code == "argument_constraint"
    assert optional.check(_refund(10)) == []


def test_one_of_and_matches() -> None:
    trace = Trace(
        name="t",
        steps=[
            ToolCall(
                index=0,
                name="issue_refund",
                arguments={"currency": "XBT", "order_id": "bad-id"},
            )
        ],
    )
    currency = ArgumentConstraint(tool="issue_refund", path="currency", one_of=["USD", "EUR"])
    order = ArgumentConstraint(tool="issue_refund", path="order_id", matches=r"^A-\d+$")

    assert currency.check(trace)[0].actual == "XBT"
    assert order.check(trace)[0].actual == "bad-id"


def test_non_numeric_value_against_a_numeric_bound() -> None:
    trace = Trace(
        name="t",
        steps=[ToolCall(index=0, name="issue_refund", arguments={"amount": "lots"})],
    )
    constraint = ArgumentConstraint(tool="issue_refund", path="amount", less_than=500)
    assert "expected a number" in constraint.check(trace)[0].message


def test_constraint_applies_to_every_matching_call() -> None:
    trace = Trace(
        name="t",
        steps=[
            ToolCall(index=0, name="issue_refund", arguments={"amount": 10}),
            ToolCall(index=1, name="issue_refund", arguments={"amount": 9999}),
        ],
    )
    constraint = ArgumentConstraint(tool="issue_refund", path="amount", less_or_equal=500)
    assert len(constraint.check(trace)) == 1


# --------------------------------------------------------------------------- #
# Output policy
# --------------------------------------------------------------------------- #


def _said(text: str) -> Trace:
    return Trace(name="t", final_output=text)


def test_forbidden_phrase_catches_the_overpromise() -> None:
    """Every tool call correct; the sentence is still a liability."""
    policy = OutputPolicy(must_not_contain=["goodwill bonus", "guaranteed"])
    trace = _said("Refunded $49.99. You will also get $10,000 as a goodwill bonus.")

    violations = policy.check(trace)
    assert violations[0].code == "output_policy"
    assert "goodwill bonus" in violations[0].message


def test_required_disclosure() -> None:
    policy = OutputPolicy(must_contain=["reference number"])

    assert policy.check(_said("Done. Your reference number is RF-77120.")) == []
    assert policy.check(_said("Done."))[0].expected == "reference number"


def test_case_insensitive_by_default() -> None:
    policy = OutputPolicy(must_not_contain=["GUARANTEED"])
    assert policy.check(_said("This is guaranteed."))


def test_pii_leak_detection() -> None:
    policy = OutputPolicy(forbid_pii=["credit_card", "ssn", "email"])

    assert policy.check(_said("Card 4111 1111 1111 1111 refunded."))
    assert policy.check(_said("SSN 123-45-6789 on file."))
    assert policy.check(_said("We emailed customer@example.com."))
    assert policy.check(_said("Refund complete.")) == []


def test_regex_rules_and_length() -> None:
    policy = OutputPolicy(
        must_match=[r"\$\d+\.\d{2}"],
        must_not_match=[r"\b\d{16}\b"],
        max_length=40,
    )
    codes = {v.message for v in policy.check(_said("Refunded some amount, eventually, at length."))}
    assert any("required pattern" in m for m in codes)
    assert any("longer than allowed" in m for m in codes)


def test_policy_can_inspect_every_model_message() -> None:
    trace = Trace(
        name="t",
        steps=[ModelCall(index=0, response_text="I will wire you $10,000.")],
        final_output="Refund complete.",
    )
    final_only = OutputPolicy(must_not_contain=["$10,000"])
    everything = OutputPolicy(must_not_contain=["$10,000"], applies_to="all")

    assert final_only.check(trace) == []
    assert everything.check(trace)


def test_output_policy_can_warn_instead_of_failing() -> None:
    policy = OutputPolicy(must_not_contain=["sorry"], severity="warning")
    assert policy.check(_said("Sorry about that."))[0].severity == "warning"
