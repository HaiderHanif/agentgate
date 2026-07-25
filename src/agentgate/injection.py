"""Detecting prompt-injection payloads inside recorded tool output.

Tool results are attacker-controlled surfaces: a web search, a support ticket, a
scraped page. If a payload lands in a golden trace it gets replayed into the
agent on every CI run, and if the agent complied when the trace was recorded,
that compliance is now the approved baseline.

Detection here is heuristic and reports as a **warning** by default. Pattern
matching cannot decide intent, and a scanner that fails builds on false
positives gets disabled within a week.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from agentgate.trace import Trace
from agentgate.violations import Severity, Violation

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|forget)\b[^.\n]{0,30}\b(previous|prior|above|earlier|all)\b"
        r"[^.\n]{0,30}\b(instruction|prompt|rule|direction)",
        re.IGNORECASE,
    ),
    "role_reassignment": re.compile(
        r"\byou are now\b|\bact as (?:a |an )?(?:developer|admin|root|dan)\b"
        r"|\bdeveloper mode\b|\bpretend (?:you are|to be)\b",
        re.IGNORECASE,
    ),
    "prompt_exfiltration": re.compile(
        r"\b(reveal|repeat|print|output|show)\b[^.\n]{0,30}"
        r"\b(system prompt|your instructions|initial prompt)\b",
        re.IGNORECASE,
    ),
    "chat_delimiter": re.compile(
        r"<\|im_(?:start|end)\|>|\[/?INST\]|<<SYS>>|###\s*system:",
        re.IGNORECASE,
    ),
    "privilege_escalation": re.compile(
        r"\b(approve|authori[sz]e|grant|issue)\b[^.\n]{0,40}"
        r"\b(without|bypass|skip|regardless of)\b[^.\n]{0,30}"
        r"\b(check|approval|verification|policy|confirmation)\b",
        re.IGNORECASE,
    ),
}


class InjectionFinding(BaseModel):
    """One suspicious span found in recorded content."""

    pattern: str
    location: str
    excerpt: str


def scan_text(text: str, location: str = "text") -> list[InjectionFinding]:
    """Scan a string for known injection shapes."""
    findings: list[InjectionFinding] = []
    for name, pattern in INJECTION_PATTERNS.items():
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 30)
            findings.append(
                InjectionFinding(
                    pattern=name,
                    location=location,
                    excerpt=text[start : match.end() + 30].strip(),
                )
            )
    return findings


def _walk(value: Any, location: str) -> list[InjectionFinding]:
    if isinstance(value, str):
        return scan_text(value, location)
    if isinstance(value, dict):
        return [f for k, v in value.items() for f in _walk(v, f"{location}.{k}")]
    if isinstance(value, list):
        return [f for i, v in enumerate(value) for f in _walk(v, f"{location}[{i}]")]
    return []


def scan_trace(trace: Trace) -> list[InjectionFinding]:
    """Scan every tool result in a trace for injection payloads."""
    findings: list[InjectionFinding] = []
    for call in trace.tool_calls:
        findings += _walk(call.result, f"{call.name}[{call.index}].result")
    return findings


def check_no_injected_content(
    observed: Trace, *, severity: Severity = "warning"
) -> list[Violation]:
    """Report injection payloads sitting in replayed tool output."""
    return [
        Violation(
            code="prompt_injection",
            message=(
                f"possible prompt injection ({finding.pattern}) in {finding.location}; "
                f"review before trusting this trace as a baseline"
            ),
            severity=severity,
            actual=finding.excerpt,
        )
        for finding in scan_trace(observed)
    ]
