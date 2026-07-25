"""Deterministic replay of a recorded agent run.

During replay no network call is made and no *routed* side effect fires: model
responses and tool results are served from the golden trace. What we observe is
the agent's decision path under exactly the conditions that were recorded.

Read that guarantee narrowly. Only calls made through `ctx.model()` and
`ctx.tool()` are stubbed. Agent code is still ordinary Python running in-process
and can open sockets, spawn subprocesses, and write files. Replay removes the
model and the tools from the loop; it is not a sandbox.

Two properties this module must get right, because both failures are silent:

* **Order.** Recorded calls are consumed in the order they were recorded, so a
  tool called twice with identical arguments returns its first result first.
  Keying results by argument digest alone loses this and makes polling loops
  untestable.
* **Completeness.** An agent that *stops* making a recorded call has changed its
  behaviour just as much as one that adds a call. Strict replay reports both.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agentgate.exceptions import ReplayError
from agentgate.redaction import DEFAULT_REDACT_KEYS, redact_value
from agentgate.trace import ModelCall, ToolCall, Trace, digest

__all__ = ["ReplayContext", "ReplayError", "ReplayedToolError", "replay_run"]


class ReplayedToolError(RuntimeError):
    """Raised in place of a tool failure that was captured in the golden trace.

    The original exception type cannot be reconstructed - a trace stores the
    message, not the class - so agent code that catches a specific exception
    will not behave identically here. That is a known limitation, and it is
    still far better than the alternative: returning `None` and letting a
    recorded outage replay as a success.
    """


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

        # A single ordered ledger of tool calls that have not been served yet.
        # One structure rather than several indexes, so "consumed" can never
        # disagree between lookup strategies.
        self._remaining: list[ToolCall | None] = list(golden.tool_calls)

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

    # ----------------------------------------------------------------- #
    # Model
    # ----------------------------------------------------------------- #

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

    # ----------------------------------------------------------------- #
    # Tools
    # ----------------------------------------------------------------- #

    def _take(self, name: str, arguments: dict[str, Any]) -> ToolCall | None:
        """Consume the earliest unserved recorded call that matches.

        Order of preference: exact name and arguments; the same call with
        sensitive arguments masked; then, in non-strict mode, any unserved call
        to the same tool.

        The masked attempt is not a convenience. Traces are redacted before they
        are committed, so a golden trace holds `<redacted>` where the live agent
        passes a real credential. Without it, redacting an argument would make
        that scenario impossible to replay, putting privacy and testability in
        direct conflict.
        """
        wanted = digest(arguments)
        masked = digest(redact_value(arguments, self._redact_keys))

        strategies = (
            lambda call: call.name == name and digest(call.arguments) in (wanted, masked),
            lambda call: (not self._strict) and call.name == name,
        )
        for matches in strategies:
            for position, call in enumerate(self._remaining):
                if call is not None and matches(call):
                    self._remaining[position] = None
                    return call
        return None

    def tool(self, name: str, **arguments: Any) -> Any:
        """Serve the recorded result for this tool call.

        A miss is not an error condition to work around, it *is* the finding:
        the agent asked for something it never asked for when the trace was good.
        """
        recorded = self._take(name, arguments)

        if recorded is None:
            if name in self._extra:
                result = copy.deepcopy(self._extra[name])
                self.observed.steps.append(
                    ToolCall(
                        index=self._next_index, name=name, arguments=arguments, result=result
                    )
                )
                return result
            # Never interpolate live arguments directly: a strict miss on a call
            # carrying an API key would print it into the CI log.
            safe_arguments = redact_value(arguments, self._redact_keys)
            raise ReplayError(
                f"no recorded result for tool {name!r} with arguments {safe_arguments!r} "
                f"remains unserved. Recorded path was {self._golden.tool_sequence}. "
                f"Either the agent's behaviour changed, or the trace needs "
                f"re-recording. To verify an intentional new step without "
                f"re-recording, pass extra_tools={{{name!r}: <result>}}."
            )

        # Deep-copy so agent code mutating a nested value cannot rewrite the
        # golden trace in memory and quietly change what "correct" means.
        result = copy.deepcopy(recorded.result)

        self.observed.steps.append(
            ToolCall(
                index=self._next_index,
                name=name,
                arguments=arguments,
                result=result,
                error=recorded.error,
            )
        )

        if recorded.error:
            raise ReplayedToolError(recorded.error)
        return result

    # ----------------------------------------------------------------- #
    # Completion
    # ----------------------------------------------------------------- #

    def _unconsumed(self) -> list[str]:
        tools = [call.name for call in self._remaining if call is not None]
        models = ["<model>"] * len(self._model_queue)
        return tools + models

    def finish(self, final_output: str = "") -> Trace:
        """Close the run, reporting recorded steps the agent never made.

        Only enforced under `strict`. An agent that skips a recorded step has
        changed its behaviour, but non-strict replay exists precisely to explore
        partial or refactored paths, and failing there would make it useless.
        """
        if self._strict:
            missing = self._unconsumed()
            if missing:
                raise ReplayError(
                    f"agent did not make {len(missing)} recorded step(s): {missing}. "
                    f"Recorded path was {self._golden.tool_sequence}. Dropping a step is "
                    f"a behaviour change; re-record with pytest --agentgate-update if "
                    f"it is intended, or use strict=False to allow partial paths."
                )
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

    :param strict: match recorded tool calls on arguments as well as name, and
        require every recorded step to be consumed.
    :param extra_tools: stub results for tools absent from the golden trace, so
        an intentionally added step can be verified without re-recording.
    :param redact_keys: argument keys that were masked when the trace was saved.
        Defaults to the same list the recorder uses.
    """
    context = ReplayContext(
        golden, strict=strict, extra_tools=extra_tools, redact_keys=redact_keys
    )
    output = agent(context)
    return context.finish(output)
