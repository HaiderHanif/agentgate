"""Declarative constraints: the answer to "exact trace matching is too brittle".

Exact sequence matching asks "did the agent do the identical thing?". That is
often stricter than the truth. Three checks that reordered inventory lookups is
fine, but refunding before verifying is not - and only constraints can express
that difference.

Use these instead of, or alongside, whole-sequence comparison.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentgate.trace import Trace
from agentgate.violations import Severity, Violation

# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


class Ordering(BaseModel):
    """`first` must happen before `second`, whenever both happen.

    This is the constraint that actually matters in the refund example. It holds
    regardless of what else the agent does around it, so refactors that add,
    remove, or reorder unrelated steps do not fail the build.
    """

    first: str
    second: str
    severity: Severity = "error"

    def check(self, observed: Trace) -> list[Violation]:
        sequence = observed.tool_sequence
        if self.first not in sequence or self.second not in sequence:
            return []
        if sequence.index(self.first) < sequence.index(self.second):
            return []
        return [
            Violation(
                code="ordering",
                message=f"{self.first!r} must be called before {self.second!r}",
                severity=self.severity,
                expected=f"{self.first} -> {self.second}",
                actual=" -> ".join(sequence),
            )
        ]


class UnorderedGroup(BaseModel):
    """These tools must all be called, in any order.

    For genuinely order-independent work - checking inventory, payment, and
    shipping - where insisting on one order would block valid refactors.
    """

    tools: list[str]
    severity: Severity = "error"

    def check(self, observed: Trace) -> list[Violation]:
        called = set(observed.tool_sequence)
        missing = [t for t in self.tools if t not in called]
        if not missing:
            return []
        return [
            Violation(
                code="unordered_group",
                message=f"expected all of {self.tools} to be called; missing {missing}",
                severity=self.severity,
                expected=self.tools,
                actual=observed.tool_sequence,
            )
        ]


# --------------------------------------------------------------------------- #
# Argument values
# --------------------------------------------------------------------------- #


def _dig(value: Any, path: str) -> tuple[bool, Any]:
    """Follow a dotted path. Returns (found, value)."""
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


class ArgumentConstraint(BaseModel):
    """A bound on the value an agent passes to a tool.

    This closes the "right tool, catastrophic argument" gap: the agent correctly
    calls `issue_refund`, but for $10,000 instead of $49.99. Sequence checks pass.
    This does not.

        ArgumentConstraint(tool="issue_refund", path="amount", less_or_equal=500)
    """

    tool: str
    path: str
    required: bool = True
    equals: Any = None
    not_equals: Any = None
    less_than: float | None = None
    less_or_equal: float | None = None
    greater_than: float | None = None
    greater_or_equal: float | None = None
    one_of: list[Any] | None = None
    matches: str | None = None
    max_length: int | None = None
    severity: Severity = "error"

    def _violation(self, message: str, expected: Any, actual: Any) -> Violation:
        return Violation(
            code="argument_constraint",
            message=f"{self.tool}.{self.path}: {message}",
            severity=self.severity,
            expected=expected,
            actual=actual,
        )

    def _check_value(self, value: Any) -> list[Violation]:
        found: list[Violation] = []

        if self.equals is not None and value != self.equals:
            found.append(self._violation("expected an exact value", self.equals, value))
        if self.not_equals is not None and value == self.not_equals:
            found.append(self._violation("value is explicitly disallowed", f"not {self.not_equals}", value))
        if self.one_of is not None and value not in self.one_of:
            found.append(self._violation("value outside the allowed set", self.one_of, value))
        if self.matches is not None and not re.search(self.matches, str(value)):
            found.append(self._violation("value does not match pattern", self.matches, value))
        if self.max_length is not None and len(str(value)) > self.max_length:
            found.append(self._violation("value is too long", self.max_length, len(str(value))))

        numeric_checks = (
            (self.less_than, lambda v, b: v < b, "must be less than"),
            (self.less_or_equal, lambda v, b: v <= b, "must be at most"),
            (self.greater_than, lambda v, b: v > b, "must be greater than"),
            (self.greater_or_equal, lambda v, b: v >= b, "must be at least"),
        )
        for bound, predicate, label in numeric_checks:
            if bound is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                found.append(self._violation("expected a number", f"{label} {bound}", value))
            elif not predicate(float(value), bound):
                found.append(self._violation(f"{label} {bound}", bound, value))
        return found

    def check(self, observed: Trace) -> list[Violation]:
        violations: list[Violation] = []
        for call in observed.tool_calls:
            if call.name != self.tool:
                continue
            found, value = _dig(call.arguments, self.path)
            if not found:
                if self.required:
                    violations.append(
                        self._violation("argument is missing", self.path, call.arguments)
                    )
                continue
            violations += self._check_value(value)
        return violations


# --------------------------------------------------------------------------- #
# Output content
# --------------------------------------------------------------------------- #

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\+?\d{1,3}[ -]?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{16,}\b"),
}


class OutputPolicy(BaseModel):
    """Content rules for what the agent actually says.

    Behavioural checks answer "did it do the right thing?". They do not answer
    "did it say something harmful, non-compliant, or untrue while doing it?".
    An agent can call every tool in the correct order and still promise a
    customer a $10,000 goodwill bonus, or leak a card number, or drop a legally
    required disclosure.

    That is a different question, and it needs a different check.

        OutputPolicy(
            must_contain=["reference number"],
            must_not_contain=["guaranteed", "goodwill bonus"],
            forbid_pii=["credit_card", "ssn"],
        )
    """

    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    must_match: list[str] = Field(default_factory=list)
    must_not_match: list[str] = Field(default_factory=list)
    forbid_pii: list[str] = Field(default_factory=list)
    max_length: int | None = None
    case_sensitive: bool = False
    applies_to: Literal["final", "all"] = "final"
    severity: Severity = "error"

    def _targets(self, observed: Trace) -> list[tuple[str, str]]:
        if self.applies_to == "final":
            return [("final_output", observed.final_output)]
        targets = [("final_output", observed.final_output)]
        targets += [(f"model[{c.index}]", c.response_text) for c in observed.model_calls]
        return targets

    def _violation(self, code_detail: str, location: str, expected: Any, actual: Any) -> Violation:
        return Violation(
            code="output_policy",
            message=f"{location}: {code_detail}",
            severity=self.severity,
            expected=expected,
            actual=actual,
        )

    def check(self, observed: Trace) -> list[Violation]:
        violations: list[Violation] = []
        flags = 0 if self.case_sensitive else re.IGNORECASE

        for location, text in self._targets(observed):
            haystack = text if self.case_sensitive else text.lower()

            for phrase in self.must_contain:
                needle = phrase if self.case_sensitive else phrase.lower()
                if needle not in haystack:
                    violations.append(
                        self._violation(f"required phrase {phrase!r} is missing", location, phrase, None)
                    )

            for phrase in self.must_not_contain:
                needle = phrase if self.case_sensitive else phrase.lower()
                if needle in haystack:
                    violations.append(
                        self._violation(f"forbidden phrase {phrase!r} is present", location, None, phrase)
                    )

            for pattern in self.must_match:
                if not re.search(pattern, text, flags):
                    violations.append(
                        self._violation(f"required pattern {pattern!r} did not match", location, pattern, None)
                    )

            for pattern in self.must_not_match:
                match = re.search(pattern, text, flags)
                if match:
                    violations.append(
                        self._violation(
                            f"forbidden pattern {pattern!r} matched", location, None, match.group(0)
                        )
                    )

            for kind in self.forbid_pii:
                pattern = PII_PATTERNS.get(kind)
                if pattern is None:
                    continue
                match = pattern.search(text)
                if match:
                    violations.append(
                        self._violation(
                            f"possible {kind} disclosed in output", location, None, match.group(0)
                        )
                    )

            if self.max_length is not None and len(text) > self.max_length:
                violations.append(
                    self._violation("output is longer than allowed", location, self.max_length, len(text))
                )

        return violations
