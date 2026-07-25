"""Recording live agent runs into golden traces.

This module produces the artefact every other part of agentgate trusts. A
missing trace is an inconvenience; a *wrong* trace is a false expectation that
silently redefines correct behaviour for every future run. The care here is
spent accordingly: values are snapshotted at the moment of the call, failed
runs still yield a trace, and a run can never write outside its trace
directory.
"""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Union

from agentgate.exceptions import AgentGateError
from agentgate.pricing import estimate_cost
from agentgate.trace import ModelCall, ModelResult, ToolCall, Trace, digest, save_trace

ModelFn = Callable[[str], Union[str, ModelResult]]
ToolRegistry = dict[str, Callable[..., Any]]
AgentFn = Callable[[Any], str]

#: Trace names become filenames, so they may not contain separators or dots
#: that would let a run write outside its trace directory.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_trace_name(name: str) -> str:
    """Validate a trace name that will be turned into a path.

    Names arrive from configuration, CLI arguments and test code, and were
    previously joined onto the trace directory unchecked - so `../../id_rsa`
    was a valid trace name. Rejecting is the only reasonable response;
    sanitising silently would make two different scenarios collide on one file.
    """
    if not SAFE_NAME.match(name) or ".." in name:
        raise AgentGateError(
            f"unsafe trace name {name!r}. Names become filenames, so they must "
            f"start with a letter or digit and contain only letters, digits, "
            f"dots, dashes and underscores."
        )
    return name


def _snapshot(value: Any) -> Any:
    """Copy a value so later mutation cannot rewrite what was recorded.

    A tool that mutates a nested argument, or an agent that mutates a returned
    result, would otherwise change the recording after the fact. Values that
    cannot be deep-copied are stored as-is: recording must never break an agent
    that works.
    """
    try:
        return copy.deepcopy(value)
    except Exception:  # pragma: no cover - exotic unpicklable objects
        return value


class Recorder:
    """Collects steps from a live run and assembles a :class:`Trace`.

    Not thread-safe. Parallel tool calls are not modelled yet, and appending
    from several threads would produce a step order that does not reproduce.
    """

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
        """Append a tool step, snapshotting arguments and result."""
        self.trace.steps.append(
            ToolCall(
                index=self._next_index,
                name=name,
                arguments=_snapshot(arguments),
                result=_snapshot(result),
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
    context, which is precisely what makes the run capturable and later
    replayable. Tool exceptions are recorded and then re-raised, so a failing
    run still produces a diagnosable trace.
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
        # Snapshot before the call: a tool that mutates its own arguments would
        # otherwise be recorded as having received the mutated values.
        recorded_arguments = _snapshot(arguments)
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
                name, recorded_arguments, result, latency_ms=elapsed, error=error
            )
        return result


@contextmanager
def record(name: str, agent: str = "unknown", **metadata: Any) -> Iterator[Recorder]:
    """Context manager yielding a :class:`Recorder` for manual instrumentation."""
    recorder = Recorder(safe_trace_name(name), agent=agent, **metadata)
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
    """Run an agent for real, capture a golden trace, and optionally save it.

    If the agent raises, the partial trace is still written - to
    `<name>.failed.json`, never over the golden trace - and the exception is
    re-raised. The run that crashed is the one whose trace is most worth having,
    and it used to be the only one that produced nothing.
    """
    safe_name = safe_trace_name(name)
    recorder = Recorder(safe_name, agent=getattr(agent, "__name__", "unknown"), **metadata)
    context = LiveContext(model_fn, tools, recorder)

    try:
        output = agent(context)
    except Exception as exc:
        if trace_dir is not None:
            recorder.trace.metadata["failed"] = True
            recorder.trace.metadata["error"] = f"{type(exc).__name__}: {exc}"
            recorder.finish("")
            save_trace(
                recorder.trace,
                Path(trace_dir) / f"{safe_name}.failed.json",
                redact=redact,
            )
        raise

    trace = recorder.finish(output)
    if trace_dir is not None:
        save_trace(trace, Path(trace_dir) / f"{safe_name}.json", redact=redact)
    return trace
