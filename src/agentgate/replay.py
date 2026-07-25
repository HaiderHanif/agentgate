"""Deterministic replay of a recorded agent run.

During replay no network call is made and no side effect fires. Model responses
and tool results are served from the golden trace, so the run is fast, free, and
identical every time. What we observe is the agent's *decision path* under
exactly the conditions that were recorded.

One consequence is worth stating plainly: replay can only serve results that were
recorded. An agent that starts calling a tool the golden run never called has no
recorded answer to receive, and that is reported rather than guessed. When the
new step is intentional, supply a stub for it with `extra_tools` - which lets you
verify a refactor without re-recording - or re-record the trace.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agentgate.exceptions import ReplayError
from agentgate.redaction import DEFAULT_REDACT_KEYS, redact_value
from agentgate.trace import ModelCall, ToolCall, Trace, digest

__all__ = ["ReplayContext", "ReplayError", "replay_run"]


class ReplayContext:
    """The object an agent talks to during a *replayed* run.

    Mirrors :class:`~agentgate.recorder.LiveContext` exactly, so agent code is
    byte-for-byte identical in both modes.
    """

    def __init__(
        self,
        golden: Trace,
        *,
        strict: bool = True,
        extra_tools: Mapping[str, Any] | None = None,
        redact_keys: Sequence[str] | None = None,
    ) -> None:
        self._golden = golden
        self._strict = strict
        self._model_queue: list[ModelCall] = list(golden.model_calls)
        self._exact: dict[tuple[str, str], Any] = {
            (t.name, digest(t.arguments)): t.result for t in golden.tool_calls
        }
        self._by_name: dict[str, Any] = {t.name: t.result for t in golden.tool_calls}
        self._extra: dict[str, Any] = dict(extra_tools or {})
        self._redact_keys: list[str] = [
            k.lower() for k in (redact_keys if redact_keys is not None else DEFAULT_REDACT_KEYS)
        ]
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

    def _lookup(self, name: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
        """Resolve a recorded result, or report that there is none.

        Resolution order: the exact recorded call; the same call with sensitive
        arguments masked; an explicit `extra_tools` stub; then, in non-strict
        mode, any recorded call to the same tool.

        The masked attempt is not a convenience. Traces are redacted before they
        are committed, so a golden trace holds `<redacted>` where the live agent
        passes a real API key. Without this step, redacting an argument would
        quietly make that scenario impossible to replay - privacy and
        testability would be in direct conflict, and privacy would lose.
        """
        key = (name, digest(arguments))
        if key in self._exact:
            return True, self._exact[key]

        masked_key = (name, digest(redact_value(arguments, self._redact_keys)))
        if masked_key in self._exact:
            return True, self._exact[masked_key]

        if name in self._extra:
            return True, self._extra[name]
        if not self._strict and name in self._by_name:
            return True, self._by_name[name]
        return False, None

    def tool(self, name: str, **arguments: Any) -> Any:
        """Serve the recorded result for this tool call.

        A miss is not an error condition to work around, it *is* the finding.
        The agent asked for something it never asked for when the trace was good.
        """
        found, result = self._lookup(name, arguments)
        if not found:
            raise ReplayError(
                f"no recorded result for tool {name!r} with arguments {arguments!r}. "
                f"Recorded path was {self._golden.tool_sequence}. "
                f"Either the agent's behaviour changed, or the trace needs "
                f"re-recording. To verify an intentional new step without "
                f"re-recording, pass extra_tools={{{name!r}: <result>}}."
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
    extra_tools: Mapping[str, Any] | None = None,
    redact_keys: Sequence[str] | None = None,
) -> Trace:
    """Replay `agent` against `golden` and return the observed trace.

    :param strict: match recorded tool calls on arguments as well as name.
    :param extra_tools: stub results for tools absent from the golden trace,
        so an intentionally added step can be verified without re-recording.
    :param redact_keys: argument keys that were masked when the trace was
        saved. Defaults to the same list the recorder uses.
    """
    context = ReplayContext(
        golden, strict=strict, extra_tools=extra_tools, redact_keys=redact_keys
    )
    output = agent(context)
    return context.finish(output)
