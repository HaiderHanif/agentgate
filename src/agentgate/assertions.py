"""Behavioural checks and the policy that composes them.

The design question this module answers is *what counts as the same behaviour*.
There is no single correct answer, so agentgate refuses to hard-code one:
every check is individually switchable, individually tunable, and carries a
severity so a team can decide what blocks a merge and what merely gets reported.

Three families of check exist here:

1. **Comparative** - the observed run against the golden trace
   (sequence, arguments, step count, output similarity).
2. **Absolute** - invariants that hold regardless of the golden trace
   (required tools, forbidden tools, budgets, ordering, argument bounds).
3. **Content** - what the agent said, not what it did
   (output policy, injection scanning).

Family 2 matters more than it first appears. Comparative checks inherit whatever
the golden run happened to do, including its mistakes. Absolute constraints are
how you state a requirement that is true independently of any recording.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from agentgate.constraints import (
    ArgumentConstraint,
    Ordering,
    OutputPolicy,
    UnorderedGroup,
)
from agentgate.injection import check_no_injected_content
from agentgate.normalize import Normalizer
from agentgate.trace import Trace
from agentgate.violations import Severity, Violation, has_errors

__all__ = [
    "ArgumentConstraint",
    "Ordering",
    "OutputPolicy",
    "Policy",
    "Severity",
    "UnorderedGroup",
    "Violation",
    "check_cost_ceiling",
    "check_forbidden_tools",
    "check_latency_budget",
    "check_no_injected_content",
    "check_no_tool_errors",
    "check_output_similarity",
    "check_required_tools",
    "check_step_count",
    "check_tool_arguments",
    "check_tool_sequence",
    "has_errors",
]

DEFAULT_SIMILARITY = 0.85


# --------------------------------------------------------------------------- #
# Comparative checks
# --------------------------------------------------------------------------- #


def check_tool_sequence(
    golden: Trace, observed: Trace, *, severity: Severity = "error"
) -> list[Violation]:
    """The tools called, in the order they were called.

    This is the strictest check in the library and the one that catches the
    reordering class of bug. It is also the one most likely to fire on a valid
    refactor - if that becomes a problem, switch it off and express the real
    requirement with :class:`Ordering` constraints instead.
    """
    expected, actual = golden.tool_sequence, observed.tool_sequence
    if expected == actual:
        return []
    return [
        Violation(
            code="tool_sequence",
            message="tool call order diverged from the golden trace",
            severity=severity,
            expected=expected,
            actual=actual,
        )
    ]


def check_tool_arguments(
    golden: Trace,
    observed: Trace,
    ignore: list[str] | None = None,
    *,
    normalizer: Normalizer | None = None,
    severity: Severity = "error",
) -> list[Violation]:
    """The values passed to each tool, position by position.

    `ignore` drops volatile keys entirely. `normalizer` is the better tool for
    values that must be present but whose content is inherently unstable, such
    as a UUID inside a larger string.
    """
    ignored = {key.lower() for key in (ignore or [])}
    violations: list[Violation] = []

    def prepare(arguments: dict[str, object]) -> dict[str, object]:
        filtered = {k: v for k, v in arguments.items() if k.lower() not in ignored}
        return normalizer.value(filtered) if normalizer else filtered

    for expected_call, actual_call in zip(golden.tool_calls, observed.tool_calls):
        if expected_call.name != actual_call.name:
            continue  # a sequence divergence, already reported by its own check
        expected_args = prepare(expected_call.arguments)
        actual_args = prepare(actual_call.arguments)
        if expected_args != actual_args:
            violations.append(
                Violation(
                    code="tool_arguments",
                    message=f"arguments to {expected_call.name!r} changed",
                    severity=severity,
                    expected=expected_args,
                    actual=actual_args,
                )
            )
    return violations


def check_step_count(
    golden: Trace, observed: Trace, tolerance: int = 0, *, severity: Severity = "error"
) -> list[Violation]:
    """Guard against runaway reasoning loops.

    Only extra steps are reported. Doing the same work in fewer steps is not a
    regression and should not be treated as one.
    """
    budget = len(golden.steps) + tolerance
    if len(observed.steps) <= budget:
        return []
    return [
        Violation(
            code="step_count",
            message=f"run used {len(observed.steps)} steps, budget was {budget}",
            severity=severity,
            expected=budget,
            actual=len(observed.steps),
        )
    ]


def similarity(left: str, right: str) -> float:
    """Character-level similarity in [0, 1]."""
    return SequenceMatcher(None, left, right).ratio()


def check_output_similarity(
    golden: Trace,
    observed: Trace,
    threshold: float = DEFAULT_SIMILARITY,
    *,
    severity: Severity = "error",
) -> list[Violation]:
    """Compare final outputs, tolerating rewording.

    This is a lexical measure, not a semantic one. It reliably catches a wholly
    different answer and reliably ignores punctuation drift. It does **not**
    understand that "refund complete" and "refund initiated" mean different
    things - those are one character apart and will score as near-identical.

    For meaning-sensitive wording, use :class:`OutputPolicy` with explicit
    required and forbidden phrases. That is a real check; this is a smoke alarm.
    """
    score = similarity(golden.final_output, observed.final_output)
    if score >= threshold:
        return []
    return [
        Violation(
            code="output_similarity",
            message=f"final output similarity {score:.2f} is below {threshold:.2f}",
            severity=severity,
            expected=golden.final_output,
            actual=observed.final_output,
        )
    ]


# --------------------------------------------------------------------------- #
# Absolute checks
# --------------------------------------------------------------------------- #


def check_required_tools(
    observed: Trace, required: list[str], *, severity: Severity = "error"
) -> list[Violation]:
    """Tools that must appear, whatever else changes."""
    called = set(observed.tool_sequence)
    return [
        Violation(
            code="required_tool_missing",
            message=f"required tool {name!r} was never called",
            severity=severity,
            expected=name,
            actual=observed.tool_sequence,
        )
        for name in required
        if name not in called
    ]


def check_forbidden_tools(
    observed: Trace, forbidden: list[str], *, severity: Severity = "error"
) -> list[Violation]:
    """Tools that must never appear in this flow."""
    called = set(observed.tool_sequence)
    return [
        Violation(
            code="forbidden_tool_called",
            message=f"forbidden tool {name!r} was called",
            severity=severity,
            expected=None,
            actual=name,
        )
        for name in forbidden
        if name in called
    ]


def check_no_tool_errors(observed: Trace, *, severity: Severity = "error") -> list[Violation]:
    """Any tool that raised during the run."""
    return [
        Violation(
            code="tool_error",
            message=f"tool {call.name!r} failed: {call.error}",
            severity=severity,
            actual=call.error,
        )
        for call in observed.failed_tool_calls
    ]


def check_cost_ceiling(
    observed: Trace, maximum: float, *, severity: Severity = "error"
) -> list[Violation]:
    """Spend ceiling in USD, computed from recorded token counts."""
    total = observed.total_cost_usd
    if total <= maximum:
        return []
    return [
        Violation(
            code="cost_ceiling",
            message=f"run cost ${total:.6f}, ceiling is ${maximum:.6f}",
            severity=severity,
            expected=maximum,
            actual=total,
        )
    ]


def check_latency_budget(
    observed: Trace, maximum_ms: float, *, severity: Severity = "error"
) -> list[Violation]:
    """Latency budget in milliseconds.

    Meaningful for recorded runs. Replayed runs report zero latency by design,
    so this check is inert during replay rather than misleading.
    """
    total = observed.total_latency_ms
    if total <= maximum_ms:
        return []
    return [
        Violation(
            code="latency_budget",
            message=f"run took {total:.0f}ms, budget is {maximum_ms:.0f}ms",
            severity=severity,
            expected=maximum_ms,
            actual=total,
        )
    ]


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #


class Policy(BaseModel):
    """What counts as a regression for one scenario.

    The defaults are strict on structure and forgiving on wording, which is the
    combination that survives contact with a real team: agents rephrase
    constantly and harmlessly, but they should not silently change what they do.

    Every check runs on every evaluation, so a single replay reports every
    finding at once rather than revealing them one failed build at a time.
    """

    # Comparative
    tool_sequence: bool = True
    tool_arguments: bool = True
    ignore_arguments: list[str] = Field(default_factory=list)
    normalize: Normalizer | None = None
    max_extra_steps: int | None = None
    output_similarity: float | None = DEFAULT_SIMILARITY
    output_similarity_severity: Severity = "error"

    # Absolute
    no_tool_errors: bool = True
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    ordering: list[Ordering] = Field(default_factory=list)
    unordered_groups: list[UnorderedGroup] = Field(default_factory=list)
    argument_constraints: list[ArgumentConstraint] = Field(default_factory=list)
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None

    # Content
    output: OutputPolicy | None = None
    detect_injection: bool = False
    injection_severity: Severity = "warning"

    def evaluate(self, golden: Trace, observed: Trace) -> list[Violation]:
        """Run every enabled check and return all findings."""
        violations: list[Violation] = []

        if self.tool_sequence:
            violations += check_tool_sequence(golden, observed)
        if self.tool_arguments:
            violations += check_tool_arguments(
                golden, observed, self.ignore_arguments, normalizer=self.normalize
            )
        if self.max_extra_steps is not None:
            violations += check_step_count(golden, observed, self.max_extra_steps)
        if self.output_similarity is not None:
            violations += check_output_similarity(
                golden,
                observed,
                self.output_similarity,
                severity=self.output_similarity_severity,
            )

        if self.no_tool_errors:
            violations += check_no_tool_errors(observed)
        if self.required_tools:
            violations += check_required_tools(observed, self.required_tools)
        if self.forbidden_tools:
            violations += check_forbidden_tools(observed, self.forbidden_tools)
        for rule in self.ordering:
            violations += rule.check(observed)
        for group in self.unordered_groups:
            violations += group.check(observed)
        for constraint in self.argument_constraints:
            violations += constraint.check(observed)
        if self.max_cost_usd is not None:
            violations += check_cost_ceiling(observed, self.max_cost_usd)
        if self.max_latency_ms is not None:
            violations += check_latency_budget(observed, self.max_latency_ms)

        if self.output is not None:
            violations += self.output.check(observed)
        if self.detect_injection:
            violations += check_no_injected_content(observed, severity=self.injection_severity)

        return violations

    def passes(self, golden: Trace, observed: Trace) -> bool:
        """True when nothing fatal was found. Warnings do not fail a run."""
        return not has_errors(self.evaluate(golden, observed))
