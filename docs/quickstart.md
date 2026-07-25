# Quickstart

From zero to a working regression gate in about five minutes.

## 1. Install

```bash
pip install agentgate
agentgate init
```

`init` creates a `traces/` directory and prints the configuration block to add to
your `pyproject.toml`.

## 2. Adapt your agent

An agentgate agent is any callable that takes a context and returns a string.
Instead of calling your model client and tools directly, go through the context:

```python
# before
def handle_refund():
    order = db.lookup_order("A-1042")
    decision = openai_client.chat(...)
    payments.refund(order["id"], order["amount"])

# after
def handle_refund(ctx):
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model(f"Should we refund {order['id']}?")
    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
    return decision
```

This is the only change agentgate asks for. The context is the seam that makes a
run both recordable and replayable.

## 3. Declare your tools and model

```python
from openai import OpenAI
from agentgate.adapters import openai_model_fn

TOOLS = {
    "lookup_order": db.lookup_order,
    "issue_refund": payments.refund,
}

model_fn = openai_model_fn(OpenAI(), model="gpt-4o-mini")
```

A model function is just `Callable[[str], str | ModelResult]`. Returning a
`ModelResult` adds token counts, which is what makes cost assertions work.

## 4. Record a golden trace

```bash
agentgate record app.agent:handle_refund \
  --model app.agent:model_fn \
  --tools app.agent:TOOLS \
  --name refund_flow
```

This is the one step that costs money and causes real side effects. **Point it at
a sandbox.** Everything after this is free.

Commit `traces/refund_flow.json`.

## 5. Gate on it

```python
# tests/test_agent.py
from app.agent import handle_refund

def test_refund_flow(agentgate):
    agentgate.assert_matches(handle_refund, "refund_flow")
```

```bash
pytest
```

Replay is deterministic and offline, so this runs in milliseconds and costs
nothing. Run it on every commit.

## 6. Handle intentional changes

When you deliberately change behaviour, the gate will fail. That is correct.
Re-record and review the diff:

```bash
pytest --agentgate-update
git diff traces/
```

Re-recording needs live access, so pass a `LiveSpec`:

```python
from agentgate.pytest_plugin import LiveSpec
from app.agent import TOOLS, handle_refund, model_fn

LIVE = LiveSpec(model_fn=model_fn, tools=TOOLS)

def test_refund_flow(agentgate):
    agentgate.assert_matches(handle_refund, "refund_flow", live=LIVE)
```

Without a `LiveSpec`, `--agentgate-update` skips rather than silently recording
nothing.

## Next

- [Writing policies](policies.md) - tune what counts as a regression
- [CLI reference](cli.md) - every command and flag
- [Architecture](architecture.md) - how replay stays deterministic
