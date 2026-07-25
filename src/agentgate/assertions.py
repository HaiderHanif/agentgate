"""Behavioural assertions over a replayed run.

The guiding rule: assert on what the agent *did*, not on how it phrased things.
Wording drifts constantly and harmlessly; tool order, arguments, cost, and
latency do not.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentgate.trace import Trace

Severity = Literal["error", "warning"]


class Violation(BaseModel):
    """A single behavioural regression."""

    code: str
    message: str
    severity: Severity = "error"
    expected: Any = None
    actual: Any = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"[{self.code}] {self.message}"


def check_tool_sequence(golden: Trace, observed: Trace) -> list[Violation]:
    """The agent must call the same tools in the same order."""
    if golden.tool_sequence == observed.tool_sequence:
        return []
    return [
        Violation(
            code="tool_sequence",
            message="tool call order diverged from the golden trace",
            expected=golden.tool_sequence,
            actual=observed.tool_sequence,
        )
    ]


def check_tool_arguments(
    golden: Trace, observed: Trace, *, ignore: Iterable[str] = ()
) -> list[Violation]:
    """Matching tool calls must be made with matching arguments."""
    ignored = {k.lower() for k in ignore}
    violations: list[Violation] = []
    for expected, actual in zip(golden.tool_calls, observed.tool_calls):
        if expected.name != actual.name:
            continue
        want = {k: v for k, v in expected.arguments.items() if k.lower() not in ignored}
        got = {k: v for k, v in actual.arguments.items() if k.lower() not in ignored}
        if want != got:
            violations.append(
                Violation(
                    code="tool_arguments",
                    message=f"arguments changed for tool {expected.name!r}",
                    expected=want,
                    actual=got,
                )
            )
    return violations


def check_required_tools(observed: Trace, names: Sequence[str]) -> list[Violation]:
    """Certain tools must always be called."""
    called = set(observed.tool_sequence)
    missing = [n for n in names if n not in called]
    if not missing:
        return []
    return [
        Violation(
            code="required_tool_missing",
            message=f"required tools were never called: {', '.join(missing)}",
            expected=list(names),
            actual=observed.tool_sequence,
        )
    ]


def check_forbidden_tools(observed: Trace, names: Sequence[str]) -> list[Violation]:
    """Certain tools must never be called."""
    called = set(observed.tool_sequence)
    hit = [n for n in names if n in called]
    if not hit:
        return []
    return [
        Violation(
            code="forbidden_tool_called",
            message=f"forbidden tools were called: {', '.join(hit)}",
            expected=[],
            actual=hit,
        )
    ]


def check_no_tool_errors(observed: Trace) -> list[Violation]:
    """No tool may fail during the run."""
    failures = observed.failed_tool_calls
    if not failures:
        return []
    return [
        Violation(
            code="tool_error",
            message=f"tool {call.name!r} raised: {call.error}",
            actual=call.error,
        )
        for call in failures
    ]


def check_cost_ceiling(observed: Trace, max_usd: float) -> list[Violation]:
    """A run must stay inside its cost budget."""
    if observed.total_cost_usd <= max_usd:
        return []
    return [
        Violation(
            code="cost_ceiling",
            message=f"run cost ${observed.total_cost_usd:.4f} exceeds ceiling ${max_usd:.4f}",
            expected=max_usd,
            actual=observed.total_cost_usd,
        )
    ]


def check_latency_budget(observed: Trace, max_ms: float) -> list[Violation]:
    """A run must stay inside its latency budget."""
    if observed.total_latency_ms <= max_ms:
        return []
    return [
        Violation(
            code="latency_budget",
            message=f"run took {observed.total_latency_ms:.1f}ms, budget {max_ms:.1f}ms",
            expected=max_ms,
            actual=observed.total_latency_ms,
        )
    ]


def check_step_count(golden: Trace, observed: Trace, tolerance: int = 0) -> list[Violation]:
    """Guard against runaway loops adding steps."""
    delta = len(observed.steps) - len(golden.steps)
    if delta <= tolerance:
        return []
    return [
        Violation(
            code="step_count",
            message=f"run used {delta} more steps than the golden trace (tolerance {tolerance})",
            expected=len(golden.steps),
            actual=len(observed.steps),
        )
    ]


def check_output_similarity(
    golden: Trace, observed: Trace, threshold: float = 0.85, *, severity: Severity = "error"
) -> list[Violation]:
    """Final output may be reworded, but should stay recognisably the same answer."""
    ratio = SequenceMatcher(None, golden.final_output, observed.final_output).ratio()
    if ratio >= threshold:
        return []
    return [
        Violation(
            code="output_similarity",
            message=f"final output similarity {ratio:.2f} below threshold {threshold:.2f}",
            severity=severity,
            expected=golden.final_output,
            actual=observed.final_output,
        )
    ]


class Policy(BaseModel):
    """A reusable bundle of behavioural checks.

    Every check runs, so a single replay reports every regression at once rather
    than making you fix them one at a time.
    """

    tool_sequence: bool = True
    tool_arguments: bool = True
    no_tool_errors: bool = True
    ignore_arguments: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_extra_steps: int | None = None
    output_similarity: float | None = 0.85
    output_similarity_severity: Severity = "error"

    def evaluate(self, golden: Trace, observed: Trace) -> list[Violation]:
        """Run every enabled check and return all violations."""
        violations: list[Violation] = []
        if self.tool_sequence:
            violations += check_tool_sequence(golden, observed)
        if self.tool_arguments:
            violations += check_tool_arguments(golden, observed, ignore=self.ignore_arguments)
        if self.no_tool_errors:
            violations += check_no_tool_errors(observed)
        if self.required_tools:
            violations += check_required_tools(observed, self.required_tools)
        if self.forbidden_tools:
            violations += check_forbidden_tools(observed, self.forbidden_tools)
        if self.max_cost_usd is not None:
            violations += check_cost_ceiling(observed, self.max_cost_usd)
        if self.max_latency_ms is not None:
            violations += check_latency_budget(observed, self.max_latency_ms)
        if self.max_extra_steps is not None:
            violations += check_step_count(golden, observed, self.max_extra_steps)
        if self.output_similarity is not None:
            violations += check_output_similarity(
                golden,
                observed,
                self.output_similarity,
                severity=self.output_similarity_severity,
            )
        return violations


def has_errors(violations: Sequence[Violation]) -> bool:
    """True when at least one violation is fatal (as opposed to a warning)."""
    return any(v.is_error for v in violations)
