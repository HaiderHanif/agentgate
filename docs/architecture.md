# Architecture

agentgate is small on purpose. Five ideas hold it together.

## 1. The context seam

Agents do not call models or tools directly. They call a context object:

```python
def agent(ctx):
    result = ctx.tool("lookup", id="A-1")
    text = ctx.model("decide")
```

Two implementations satisfy that interface:

| | `LiveContext` | `ReplayContext` |
| :--- | :--- | :--- |
| model calls | real provider call | served from the trace |
| tool calls | real function call | served from the trace |
| side effects | yes | never |
| cost | real | zero |
| determinism | no | total |

Because both expose the same two methods, agent code is byte-for-byte identical
in recording and replay. There is no test-only branch to drift out of sync.

## 2. Traces are plain data

A `Trace` is a Pydantic model that serialises to readable JSON: an ordered list
of `ModelCall` and `ToolCall` steps, discriminated by a `kind` field.

This matters more than it sounds. Because traces are plain JSON:

- `git diff` shows exactly which decision changed
- reviewers can audit behaviour change without running code
- traces can be generated, inspected, and edited by other tools

The schema carries a `schema_version`, and loading rejects versions this build
does not understand rather than failing in a confusing way later.

## 3. Replay by content, not position

Tool results are keyed by `(tool_name, digest(arguments))`, where the digest is a
truncated SHA-256 of the canonically serialised arguments - keys sorted, so
argument order never matters.

The consequence: **a cache miss is the finding.** If the agent asks for a tool
call it never made during the good run, replay stops and tells you, rather than
improvising a result and letting the difference go unnoticed.

Model calls are served in order from a queue, since prompts legitimately change
wording between runs while the sequence of decisions should not.

## 4. Assertions target actions, not prose

LLM output is stochastic. Asserting on text produces a flaky suite that people
switch off within a month.

The decision path is not stochastic in the same way. A well-built agent looks up
an order, decides, refunds, then notifies - every time. That order is a
specification, and it is what the assertions target.

Output similarity exists as a soft check, defaults to a forgiving 0.85, and can
be downgraded to a warning. It is the exception, not the model.

## 5. One replay reports everything

`Policy.evaluate()` runs every enabled check and returns all violations. You are
never fixing one regression only to discover a second on the next run.

Violations carry a `severity`, so a policy can distinguish "this must not ship"
from "a human should look at this".

## Module map

```text
src/agentgate/
  trace.py           data model, digests, load and save
  recorder.py        LiveContext, Recorder, record_run
  replay.py          ReplayContext, replay_run
  assertions.py      checks and Policy
  reporting.py       text, markdown, JSON, GitHub annotations
  config.py          [tool.agentgate] in pyproject.toml
  redaction.py       strips secrets before traces hit disk
  pricing.py         token cost table
  resolve.py         module:attribute entrypoints
  cli.py             init, record, list, show, verify
  pytest_plugin.py   the agentgate fixture
  mcp_server.py      list_traces, show_trace, verify_agent
  adapters/          OpenAI and Anthropic model functions
```

## Redaction

Golden traces get committed, so `save_trace` redacts sensitive tool arguments and
results on the way out. Redaction happens at write time, never at record time -
the live run always receives real values.

Model prompts are stored only as digests, so prompt content never reaches disk.

## Deliberate limits

- **Synchronous only.** Async agent support is planned, not present.
- **No parallel tool calls.** Concurrent calls have no deterministic order to assert against.
- **Replay assumes tool purity.** A tool whose result depends on wall-clock time will need `ignore_arguments`.
- **Not an eval harness.** agentgate answers "did behaviour change?", not "is the answer good?". Use both.
