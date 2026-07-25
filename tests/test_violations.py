"""Coverage for the violation model.

Small module, disproportionate blast radius. Every check in the library reports
through `Violation`, and `has_errors()` alone decides whether a run fails. A
defect here would let every gate pass silently while the test suite stayed
green, which is exactly the failure mode this project argues against - so it
gets tested directly rather than incidentally.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentgate.violations import Violation, has_errors


def test_defaults_to_fatal() -> None:
    """Silence should never be the default for a finding."""
    violation = Violation(code="tool_sequence", message="diverged")

    assert violation.severity == "error"
    assert violation.is_error is True
    assert violation.expected is None
    assert violation.actual is None


def test_warning_is_not_an_error() -> None:
    violation = Violation(code="output_similarity", message="reworded", severity="warning")

    assert violation.is_error is False


def test_expected_and_actual_accept_arbitrary_shapes() -> None:
    violation = Violation(
        code="tool_arguments",
        message="changed",
        expected={"amount": 49.99},
        actual=["lookup_order", "issue_refund"],
    )

    assert violation.expected == {"amount": 49.99}
    assert violation.actual == ["lookup_order", "issue_refund"]


def test_unknown_severity_is_rejected() -> None:
    """A typo must not quietly downgrade a blocking check."""
    with pytest.raises(ValidationError):
        Violation(code="c", message="m", severity="critical")  # type: ignore[arg-type]


def test_str_is_readable() -> None:
    assert str(Violation(code="ordering", message="refund before lookup")) == (
        "[ordering] refund before lookup"
    )


# --------------------------------------------------------------------------- #
# has_errors - the function that decides whether CI fails
# --------------------------------------------------------------------------- #


def test_no_violations_is_a_pass() -> None:
    assert has_errors([]) is False


def test_warnings_alone_do_not_fail_a_run() -> None:
    warnings = [
        Violation(code="a", message="m", severity="warning"),
        Violation(code="b", message="m", severity="warning"),
    ]

    assert has_errors(warnings) is False


def test_a_single_error_among_warnings_fails_the_run() -> None:
    mixed = [
        Violation(code="a", message="m", severity="warning"),
        Violation(code="b", message="m", severity="error"),
        Violation(code="c", message="m", severity="warning"),
    ]

    assert has_errors(mixed) is True


def test_accepts_any_sequence_not_only_a_list() -> None:
    errors = (Violation(code="a", message="m"),)

    assert has_errors(errors) is True
