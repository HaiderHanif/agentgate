"""Recording live agent runs into golden traces."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Union

from agentgate.pricing import estimate_cost
from agentgate.trace import ModelCall, ModelResult, ToolCall, Trace, digest, save_trace

ModelFn = Callable[[str], Union[str, ModelResult]]
ToolRegistry = dict[str, Callable[..., Any]]
AgentFn = Callable[[Any], str]


class Recorder:
    """Collects steps from a live run and assembles a :class:`Trace`."""

    def __init__(self, name: str, agent: str = "unknown", **metadata: Any) -> None:
        self.trace = Trace(name=name, agent=agent, metadata=metadata)

    @property
    def _next_index(self) -> int:
        return len(self.trace.steps)

    def record_model_call(
        self,
        prompt: str,
        result: str | ModelResult,
        *,
        latency_ms: float = 0.0,
    ) -> ModelResult:
        """Append a model step, pricing it when the caller did not."""
        normalised = ModelResult(text=result) if isinstance(result, str) else result
        cost = normalised.cost_usd
        if cost is None:
            cost = estimate_cost(
                normalised.model, normalised.input_tokens, normalised.output_tokens
            )
        self.trace.steps.append(
            ModelCall(
                index=self._next_index,
                model=normalised.model,
                prompt_digest=digest(prompt),
                response_text=normalised.text,
                input_tokens=normalised.input_tokens,
                output_tokens=normalised.output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
        )
        return normalised

    def record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        result: Any = None,
        *,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Append a tool step."""
        self.trace.steps.append(
            ToolCall(
                index=self._next_index,
                name=name,
                arguments=arguments,
                result=result,
                latency_ms=latency_ms,
                error=error,
            )
        )

    def finish(self, final_output: str = "") -> Trace:
        """Seal the trace with the agent's final output."""
        self.trace.final_output = final_output
        return self.trace

    def save(self, path: str | Path, *, redact: Sequence[str] | None = None) -> Path:
        """Persist the trace, redacting sensitive values."""
        return save_trace(self.trace, path, redact=redact)


class LiveContext:
    """The object an agent talks to during a *recorded* run.

    The agent never calls the model or its tools directly - it goes through this
    context, which is precisely what makes the run capturable and later replayable.
    Tool exceptions are recorded and then re-raised, so a failing run still
    produces a diagnosable trace.
    """

    def __init__(self, model_fn: ModelFn, tools: ToolRegistry, recorder: Recorder) -> None:
        self._model_fn = model_fn
        self._tools = tools
        self._recorder = recorder

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def model(self, prompt: str) -> str:
        started = time.perf_counter()
        result = self._model_fn(prompt)
        elapsed = (time.perf_counter() - started) * 1000
        recorded = self._recorder.record_model_call(prompt, result, latency_ms=elapsed)
        return recorded.text

    def tool(self, name: str, **arguments: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown tool {name!r}; registered tools: {self.tool_names}")
        started = time.perf_counter()
        error: str | None = None
        result: Any = None
        try:
            result = self._tools[name](**arguments)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self._recorder.record_tool_call(
                name, arguments, result, latency_ms=elapsed, error=error
            )
        return result


@contextmanager
def record(name: str, agent: str = "unknown", **metadata: Any) -> Iterator[Recorder]:
    """Context manager yielding a :class:`Recorder` for manual instrumentation."""
    recorder = Recorder(name, agent=agent, **metadata)
    yield recorder


def record_run(
    name: str,
    agent: AgentFn,
    model_fn: ModelFn,
    tools: ToolRegistry,
    *,
    trace_dir: str | Path | None = None,
    redact: Sequence[str] | None = None,
    **metadata: Any,
) -> Trace:
    """Run an agent for real, capture a golden trace, and optionally save it."""
    recorder = Recorder(name, agent=getattr(agent, "__name__", "unknown"), **metadata)
    context = LiveContext(model_fn, tools, recorder)
    output = agent(context)
    trace = recorder.finish(output)
    if trace_dir is not None:
        save_trace(trace, Path(trace_dir) / f"{name}.json", redact=redact)
    return trace
