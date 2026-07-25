"""Deterministic replay of a recorded agent run.

During replay no network call is made. Model responses and tool results are
served from the golden trace, so the run is fast, free, and identical every
time. What we observe is the agent's *decision path* under those conditions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentgate.trace import ModelCall, ToolCall, Trace, digest


class ReplayError(RuntimeError):
    """Raised when the agent asks for something the golden trace cannot serve."""


class ReplayContext:
    """The object an agent talks to during a *replayed* run.

    Mirrors the LiveContext API exactly, so the agent code is unchanged.
    """

    def __init__(self, golden: Trace, *, strict: bool = True) -> None:
        self._golden = golden
        self._strict = strict
        self._model_queue = list(golden.model_calls)
        self._tool_results: dict[tuple[str, str], Any] = {
            (t.name, digest(t.arguments)): t.result for t in golden.tool_calls
        }
        self._fallback_by_name: dict[str, Any] = {t.name: t.result for t in golden.tool_calls}
        self.observed = Trace(
            name=golden.name,
            agent=golden.agent,
            metadata={"replay_of": golden.name},
        )

    @property
    def _next_index(self) -> int:
        return len(self.observed.steps)

    def model(self, prompt: str, *, model: str = "unknown", cost_usd: float = 0.0) -> str:
        if not self._model_queue:
            raise ReplayError(
                "agent made more model calls than the golden trace contains "
                f"({len(self._golden.model_calls)}); re-record the trace if this is intended"
            )
        recorded = self._model_queue.pop(0)
        self.observed.steps.append(
            ModelCall(
                index=self._next_index,
                model=model if model != "unknown" else recorded.model,
                prompt_digest=digest(prompt),
                response_text=recorded.response_text,
                input_tokens=recorded.input_tokens,
                output_tokens=recorded.output_tokens,
                cost_usd=cost_usd or recorded.cost_usd,
                latency_ms=0.0,
            )
        )
        return recorded.response_text

    def tool(self, name: str, **arguments: Any) -> Any:
        key = (name, digest(arguments))
        if key in self._tool_results:
            result = self._tool_results[key]
        elif name in self._fallback_by_name and not self._strict:
            result = self._fallback_by_name[name]
        else:
            raise ReplayError(
                f"no recorded result for tool {name!r} with arguments {arguments!r}; "
                "the agent's behaviour changed, or the trace needs re-recording"
            )
        self.observed.steps.append(
            ToolCall(index=self._next_index, name=name, arguments=arguments, result=result)
        )
        return result

    def finish(self, final_output: str = "") -> Trace:
        self.observed.final_output = final_output
        return self.observed


def replay_run(
    golden: Trace,
    agent: Callable[[ReplayContext], str],
    *,
    strict: bool = True,
) -> Trace:
    """Replay an agent against a golden trace and return the observed trace."""
    context = ReplayContext(golden, strict=strict)
    output = agent(context)
    return context.finish(output)
