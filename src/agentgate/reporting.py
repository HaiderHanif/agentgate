"""Rendering divergence reports for humans, CI logs, and pull requests."""

from __future__ import annotations

import json
from collections.abc import Sequence

from agentgate.assertions import Violation, has_errors
from agentgate.trace import Trace


def _sequence_diff(expected: Sequence[str], actual: Sequence[str]) -> list[tuple[str, str]]:
    """Align two tool paths into (status, description) rows."""
    rows: list[tuple[str, str]] = []
    for i in range(max(len(expected), len(actual))):
        want = expected[i] if i < len(expected) else None
        got = actual[i] if i < len(actual) else None
        if want == got and want is not None:
            rows.append(("ok", f"{i + 1:>2}. {want}"))
        elif want is None:
            rows.append(("added", f"{i + 1:>2}. {got}"))
        elif got is None:
            rows.append(("missing", f"{i + 1:>2}. {want}"))
        else:
            rows.append(("changed", f"{i + 1:>2}. {want} -> {got}"))
    return rows


def render_text(golden: Trace, observed: Trace, violations: Sequence[Violation]) -> str:
    """Plain-text report for terminals and CI logs."""
    header = f"agentgate: {golden.name}"
    lines = [header, "=" * len(header), ""]

    if not violations:
        lines.append(f"PASS - {len(observed.tool_calls)} tool calls matched the golden trace")
        lines.append(
            f"       cost ${observed.total_cost_usd:.4f} | "
            f"tokens {observed.total_tokens} | steps {len(observed.steps)}"
        )
        return "\n".join(lines) + "\n"

    verdict = "FAIL" if has_errors(violations) else "WARN"
    lines.append(f"{verdict} - {len(violations)} behavioural finding(s)")
    lines.append("")
    lines.append("Tool call path")
    lines.append("--------------")
    lines += [f"  {status:<8} {text}" for status, text in _sequence_diff(
        golden.tool_sequence, observed.tool_sequence
    )]
    lines.append("")
    lines.append("Findings")
    lines.append("--------")
    for violation in violations:
        lines.append(f"  [{violation.severity}] [{violation.code}] {violation.message}")
        if violation.expected is not None:
            lines.append(f"      expected: {violation.expected}")
        if violation.actual is not None:
            lines.append(f"      actual:   {violation.actual}")
    return "\n".join(lines) + "\n"


def render_markdown(golden: Trace, observed: Trace, violations: Sequence[Violation]) -> str:
    """Markdown report, suitable for posting as a pull request comment."""
    if not violations:
        return (
            f"### agentgate: `{golden.name}` passed\n\n"
            f"{len(observed.tool_calls)} tool calls matched the golden trace "
            f"(cost ${observed.total_cost_usd:.4f}, {observed.total_tokens} tokens).\n"
        )

    verdict = "failed" if has_errors(violations) else "raised warnings"
    lines = [
        f"### agentgate: `{golden.name}` {verdict}",
        "",
        "| step | status | tool |",
        "| ---: | :--- | :--- |",
    ]
    for i, (status, text) in enumerate(
        _sequence_diff(golden.tool_sequence, observed.tool_sequence), start=1
    ):
        _, _, label = text.partition(". ")
        lines.append(f"| {i} | {status} | `{label}` |")

    lines += ["", "| severity | code | detail |", "| :--- | :--- | :--- |"]
    for violation in violations:
        detail = violation.message.replace("|", "\\|")
        lines.append(f"| {violation.severity} | `{violation.code}` | {detail} |")
    return "\n".join(lines) + "\n"


def render_json(golden: Trace, observed: Trace, violations: Sequence[Violation]) -> str:
    """Machine-readable report for dashboards and downstream tooling."""
    payload = {
        "name": golden.name,
        "passed": not has_errors(violations),
        "golden": golden.summary(),
        "observed": observed.summary(),
        "violations": [v.model_dump() for v in violations],
    }
    return json.dumps(payload, indent=2, default=str) + "\n"


def github_annotations(violations: Sequence[Violation], *, file: str = "") -> str:
    """GitHub Actions workflow commands, so findings surface in the PR diff UI."""
    location = f" file={file}" if file else ""
    return "\n".join(
        f"::{'error' if v.is_error else 'warning'}{location}::[{v.code}] {v.message}"
        for v in violations
    )


RENDERERS = {
    "text": render_text,
    "markdown": render_markdown,
    "json": render_json,
}


def render_report(
    golden: Trace,
    observed: Trace,
    violations: Sequence[Violation],
    fmt: str = "text",
) -> str:
    """Render a report in the requested format."""
    try:
        renderer = RENDERERS[fmt]
    except KeyError:
        raise ValueError(f"unknown report format {fmt!r}; choose from {sorted(RENDERERS)}") from None
    return renderer(golden, observed, violations)
