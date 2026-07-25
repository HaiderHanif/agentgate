"""Deterministic replay of a recorded agent run.

During replay no network call is made and no side effect fires. Model responses
and tool results are served from the golden trace, so the run is fast, free, and
identical every time. What we observe is the agent's *decision path* under
exactly the conditions that were recorded.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentgate.exceptions import ReplayError
from agentgate.trace import ModelCall, ToolCall, Trace, digest

__all__ = ["ReplayContext", "ReplayError", "replay_run"]


class ReplayContext:
    """The object an agent talks to during a *replayed* run.

    Mirrors :class:`~agentgate.recorder.LiveContext` exactly, so agent code is
    byte-for-byte identical in both modes.
    """

    def __init__(self, golden: Trace, *, strict: bool = True) -> None:
        self._golden = golden
        self._strict = strict
        self._model_queue: list[ModelCall] = list(golden.model_calls)
        self._exact: dict[tuple[str, str], Any] = {
            (t.name, digest(t.arguments)): t.result for t in golden.tool_calls
        }
        self._by_name: dict[str, Any] = {t.name: t.result for t in golden.tool_calls}
        self.observed = Trace(
            name=golden.name,
            agent=golden.agent,
            metadata={"replay_of": golden.name, "strict": strict},
        )

    @property
    def _next_index(self) -> int:
        return len(self.observed.steps)

    def model(self, prompt: str) -> str:
        """Serve the next recorded model response, in order."""
        if not self._model_queue:
            raise ReplayError(
                f"agent made more model calls than the golden trace contains "
                f"({len(self._golden.model_calls)}). If this change is intended, "
                f"re-record with: pytest --agentgate-update"
            )
        recorded = self._model_queue.pop(0)
        self.observed.steps.append(
            ModelCall(
                index=self._next_index,
                model=recorded.model,
                prompt_digest=digest(prompt),
                response_text=recorded.response_text,
                input_tokens=recorded.input_tokens,
                output_tokens=recorded.output_tokens,
                cost_usd=recorded.cost_usd,
                latency_ms=0.0,
            )
        )
        return recorded.response_text

    def tool(self, name: str, **arguments: Any) -> Any:
        """Serve the recorded result for this exact tool call.

        A miss is not an error condition to work around - it *is* the finding.
        The agent asked for something it never asked for when the trace was good.
        """
        key = (name, digest(arguments))
        if key in self._exact:
            result = self._exact[key]
        elif not self._strict and name in self._by_name:
            result = self._by_name[name]
        else:
            raise ReplayError(
                f"no recorded result for tool {name!r} with arguments {arguments!r}. "
                f"Recorded path was {self._golden.tool_sequence}. "
                f"Either the agent's behaviour changed, or the trace needs re-recording."
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
    """Replay `agent` against `golden` and return the observed trace."""
    context = ReplayContext(golden, strict=strict)
    output = agent(context)
    return context.finish(output)
