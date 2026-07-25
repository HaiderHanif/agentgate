"""Recording live agent runs into golden traces."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agentgate.trace import ModelCall, ToolCall, Trace, digest, save_trace

ModelFn = Callable[[str], str]
ToolRegistry = dict[str, Callable[..., Any]]


class Recorder:
    """Collects steps from a live run and assembles a Trace."""

    def __init__(self, name: str, agent: str = "unknown", **metadata: Any) -> None:
        self.trace = Trace(name=name, agent=agent, metadata=metadata)

    @property
    def _next_index(self) -> int:
        return len(self.trace.steps)

    def record_model_call(
        self,
        prompt: str,
        response: str,
        *,
        model: str = "unknown",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        self.trace.steps.append(
            ModelCall(
                index=self._next_index,
                model=model,
                prompt_digest=digest(prompt),
                response_text=response,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )
        )

    def record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        result: Any = None,
        *,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
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
        self.trace.final_output = final_output
        return self.trace


class LiveContext:
    """The object an agent talks to during a *recorded* run.

    The agent never calls the model or its tools directly - it goes through
    this context, which is what makes the run capturable and later replayable.
    """

    def __init__(self, model_fn: ModelFn, tools: ToolRegistry, recorder: Recorder) -> None:
        self._model_fn = model_fn
        self._tools = tools
        self._recorder = recorder

    def model(self, prompt: str, *, model: str = "unknown", cost_usd: float = 0.0) -> str:
        started = time.perf_counter()
        response = self._model_fn(prompt)
        elapsed = (time.perf_counter() - started) * 1000
        self._recorder.record_model_call(
            prompt,
            response,
            model=model,
            cost_usd=cost_usd,
            latency_ms=elapsed,
        )
        return response

    def tool(self, name: str, **arguments: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name!r}")
        started = time.perf_counter()
        error: str | None = None
        result: Any = None
        try:
            result = self._tools[name](**arguments)
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
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
    """Context manager yielding a Recorder."""
    recorder = Recorder(name, agent=agent, **metadata)
    yield recorder


def record_run(
    name: str,
    agent: Callable[[LiveContext], str],
    model_fn: ModelFn,
    tools: ToolRegistry,
    *,
    trace_dir: str | Path | None = None,
    **metadata: Any,
) -> Trace:
    """Run an agent for real, capture a golden trace, optionally save it."""
    recorder = Recorder(name, agent=getattr(agent, "__name__", "unknown"), **metadata)
    context = LiveContext(model_fn, tools, recorder)
    output = agent(context)
    trace = recorder.finish(output)
    if trace_dir is not None:
        save_trace(trace, Path(trace_dir) / f"{name}.json")
    return trace
