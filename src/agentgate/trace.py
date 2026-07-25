"""Golden trace data model.

A trace is an ordered record of everything an agent did during one run: model
calls and tool calls, with cost and latency attached. Traces are plain JSON so
they diff cleanly in pull requests and can be reviewed like source code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, ValidationError

from agentgate.exceptions import TraceFormatError

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})


def digest(value: Any) -> str:
    """Stable short digest of any JSON-serialisable value.

    Keys are sorted so that argument dictionaries compare by content, never by
    insertion order.
    """
    payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


class ModelResult(BaseModel):
    """Rich return value from a model function.

    A model function may simply return a string. Returning a ModelResult adds
    token counts and pricing, which is what makes cost assertions meaningful.
    """

    text: str
    model: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class ModelCall(BaseModel):
    """One call to a language model."""

    kind: Literal["model"] = "model"
    index: int
    model: str = "unknown"
    prompt_digest: str = ""
    response_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class ToolCall(BaseModel):
    """One tool invocation made by the agent."""

    kind: Literal["tool"] = "tool"
    index: int
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    latency_ms: float = 0.0
    error: str | None = None


Step = Annotated[Union[ModelCall, ToolCall], Field(discriminator="kind")]


class Trace(BaseModel):
    """A complete, replayable record of a single agent run."""

    schema_version: str = SCHEMA_VERSION
    name: str
    agent: str = "unknown"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[Step] = Field(default_factory=list)
    final_output: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [s for s in self.steps if isinstance(s, ToolCall)]

    @property
    def model_calls(self) -> list[ModelCall]:
        return [s for s in self.steps if isinstance(s, ModelCall)]

    @property
    def tool_sequence(self) -> list[str]:
        """The ordered list of tool names - the agent's decision path."""
        return [t.name for t in self.tool_calls]

    @property
    def failed_tool_calls(self) -> list[ToolCall]:
        return [t for t in self.tool_calls if t.error]

    @property
    def total_cost_usd(self) -> float:
        return round(sum(m.cost_usd for m in self.model_calls), 8)

    @property
    def total_tokens(self) -> int:
        return sum(m.input_tokens + m.output_tokens for m in self.model_calls)

    @property
    def total_latency_ms(self) -> float:
        return round(sum(s.latency_ms for s in self.steps), 3)

    def summary(self) -> dict[str, Any]:
        """Compact machine-readable summary, used by reports and the MCP server."""
        return {
            "name": self.name,
            "agent": self.agent,
            "steps": len(self.steps),
            "tool_calls": len(self.tool_calls),
            "model_calls": len(self.model_calls),
            "tool_sequence": self.tool_sequence,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": self.total_latency_ms,
        }

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


def reindex(steps: Sequence[ModelCall | ToolCall]) -> list[ModelCall | ToolCall]:
    """Renumber steps so `index` always matches position."""
    return [step.model_copy(update={"index": i}) for i, step in enumerate(steps)]


def save_trace(
    trace: Trace,
    path: str | Path,
    *,
    redact: Sequence[str] | None = None,
) -> Path:
    """Write a trace to disk, redacting sensitive values first.

    Passing `redact=[]` disables redaction explicitly; passing None applies the
    default key list.
    """
    from agentgate.redaction import redact_trace  # local import avoids a cycle

    payload = trace if redact is not None and not redact else redact_trace(trace, redact)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.to_json(), encoding="utf-8")
    return target


def load_trace(path: str | Path) -> Trace:
    """Read and validate a trace from disk."""
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceFormatError(f"could not read trace {source}: {exc}") from exc

    try:
        trace = Trace.model_validate_json(raw)
    except ValidationError as exc:
        raise TraceFormatError(f"malformed trace {source}:\n{exc}") from exc

    if trace.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise TraceFormatError(
            f"trace {source} uses schema version {trace.schema_version!r}; "
            f"this build supports {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    return trace
