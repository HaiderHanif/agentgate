"""Golden trace data model.

A trace is an ordered record of everything an agent did during one run:
model calls and tool calls, with cost and latency attached. Traces are plain
JSON so they diff cleanly in pull requests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def digest(value: Any) -> str:
    """Stable short digest of any JSON-serialisable value."""
    payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


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
    def total_cost_usd(self) -> float:
        return round(sum(m.cost_usd for m in self.model_calls), 6)

    @property
    def total_latency_ms(self) -> float:
        return round(sum(s.latency_ms for s in self.steps), 3)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


def save_trace(trace: Trace, path: str | Path) -> Path:
    """Write a trace to disk, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(trace.to_json(), encoding="utf-8")
    return target


def load_trace(path: str | Path) -> Trace:
    """Read a trace from disk."""
    return Trace.model_validate_json(Path(path).read_text(encoding="utf-8"))
