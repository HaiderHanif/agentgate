"""The violation type, shared by every check.

Lives in its own module so constraint modules and assertion modules can both
use it without importing each other.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel

Severity = Literal["error", "warning"]


class Violation(BaseModel):
    """A single behavioural finding.

    `severity` is what keeps the tool trustworthy: soft, opinion-shaped checks
    can report without failing a build, so developers never learn to ignore it.
    """

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


def has_errors(violations: Sequence[Violation]) -> bool:
    """True when at least one violation is fatal rather than advisory."""
    return any(v.is_error for v in violations)
