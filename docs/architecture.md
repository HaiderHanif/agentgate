# Architecture

## Design goal

Make agent behaviour testable without making tests brittle. Wording changes constantly
and harmlessly. Structure - which tools, in what order, with what arguments, at what
cost - is what actually breaks production.

## The context indirection

Everything rests on one indirection. The agent receives a context object and calls
`ctx.model(...)` and `ctx.tool(...)` instead of touching providers directly.

```
  LIVE                                   REPLAY
  ----                                   ------
  agent(ctx)                             agent(ctx)
     |                                      |
  LiveContext                          ReplayContext
     |-- model_fn  --> real provider       |-- model  --> recorded response
     |-- tools     --> real side effects   |-- tool   --> recorded result
     |                                      |
  Recorder                               observed Trace
     |
  golden Trace
```

The agent source is identical in both modes. Only the context differs.

## The trace format

A trace is plain JSON so it diffs cleanly in pull requests:

```jsonc
{
  "schema_version": "1.0",
  "name": "refund_flow",
  "steps": [
    { "kind": "model", "index": 0, "response_text": "...", "cost_usd": 0.0012 },
    { "kind": "tool",  "index": 1, "name": "lookup_order", "arguments": { "order_id": "A-1042" } }
  ],
  "final_output": "Refund of $49.00 issued for order A-1042."
}
```

Steps are a discriminated union on `kind`. Ordering is the contract.

## Determinism

During replay:

- Model responses are dequeued from the golden trace in order
- Tool results are looked up by `(name, digest(arguments))`
- Latency is recorded as zero, because nothing actually executes
- No network call is possible, so no cost is incurred and no side effect fires

An unmatched lookup is not a fallback - it is the signal. If the agent asks for a
tool call that was never recorded, its behaviour has changed, and `ReplayError` says so.

## Assertion layer

`Policy` bundles checks and returns a list of `Violation` objects rather than raising
on the first failure, so a single run reports every regression at once. `render_report`
turns violations into a step-by-step diff for terminals, CI logs, and PR comments.

## Boundaries

agentgate deliberately does **not**:

- Judge answer quality - use an LLM judge for that, on top of this layer
- Replace production observability - it gates *before* the merge, not after deploy
- Own your model or tool clients - it wraps them through the context, nothing more
