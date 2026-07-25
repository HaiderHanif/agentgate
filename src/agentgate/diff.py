"""Human-readable divergence reports."""

from __future__ import annotations

from collections.abc import Sequence

from agentgate.assertions import Violation
from agentgate.trace import Trace


def _sequence_diff(expected: Sequence[str], actual: Sequence[str]) -> list[str]:
    lines: list[str] = []
    width = max(len(expected), len(actual))
    for i in range(width):
        want = expected[i] if i < len(expected) else None
        got = actual[i] if i < len(actual) else None
        if want == got:
            lines.append(f"  {i + 1:>2}. ok       {want}")
        elif want is None:
            lines.append(f"  {i + 1:>2}. added    {got}")
        elif got is None:
            lines.append(f"  {i + 1:>2}. missing  {want}")
        else:
            lines.append(f"  {i + 1:>2}. changed  {want} -> {got}")
    return lines


def render_report(golden: Trace, observed: Trace, violations: Sequence[Violation]) -> str:
    """Render a plain-text report suitable for terminals and CI logs."""
    header = f"agentgate: {golden.name}"
    lines = [header, "=" * len(header), ""]

    if not violations:
        lines.append(f"PASS - {len(observed.tool_calls)} tool calls matched the golden trace")
        lines.append(
            f"       cost ${observed.total_cost_usd:.4f} | "
            f"steps {len(observed.steps)} | model calls {len(observed.model_calls)}"
        )
        return "\n".join(lines) + "\n"

    lines.append(f"FAIL - {len(violations)} behavioural regression(s)")
    lines.append("")
    lines.append("Tool call path")
    lines.append("--------------")
    lines += _sequence_diff(golden.tool_sequence, observed.tool_sequence)
    lines.append("")
    lines.append("Violations")
    lines.append("----------")
    for violation in violations:
        lines.append(f"  [{violation.code}] {violation.message}")
        if violation.expected is not None:
            lines.append(f"      expected: {violation.expected}")
        if violation.actual is not None:
            lines.append(f"      actual:   {violation.actual}")
    return "\n".join(lines) + "\n"
