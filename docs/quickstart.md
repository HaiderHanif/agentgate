# Quickstart

## 1. Install

```bash
pip install agentgate
```

## 2. Write the agent against a context

The single design rule: the agent never calls the model or its tools directly.
It goes through a context object, which is what makes runs capturable and replayable.

```python
def refund_agent(ctx) -> str:
    ctx.model("Customer wants a refund for order A-1042. Plan the steps.")
    order = ctx.tool("lookup_order", order_id="A-1042")
    ctx.tool("issue_refund", order_id="A-1042", amount=order["amount"])
    ctx.tool("send_email", to="customer@example.com", template="refund_confirmed")
    return f"Refund of ${order['amount']:.2f} issued for order A-1042."
```

## 3. Record a golden trace

Run it for real, once, while it behaves correctly.

```python
from agentgate import record_run

def model_fn(prompt: str) -> str:
    ...  # your real model call

tools = {
    "lookup_order": lookup_order,
    "issue_refund": issue_refund,
    "send_email": send_email,
}

record_run("refund_flow", refund_agent, model_fn, tools, trace_dir="traces")
```

Commit `traces/refund_flow.json`. Review it like source code - it *is* your specification.

## 4. Assert in your test suite

```python
from agentgate import Policy

policy = Policy(
    required_tools=["lookup_order", "issue_refund"],
    forbidden_tools=["delete_customer"],
    max_cost_usd=0.05,
)

def test_refund_flow(agentgate):
    agentgate.assert_matches(refund_agent, "refund_flow", policy)
```

```bash
pytest
```

## 5. Re-record after an intended change

When you deliberately change behaviour, update the golden trace and commit the diff
so reviewers can see exactly what changed:

```bash
pytest --agentgate-update
```

## 6. Gate pull requests

```yaml
- uses: HaiderHanif/agentgate@v0
  with:
    agent: myapp.agents:refund_agent
    trace: traces/refund_flow.json
    max-cost: "0.05"
```

## Strict vs lenient replay

By default replay is **strict**: a tool call must match a recorded call by name *and*
arguments, otherwise `ReplayError` is raised. This is what catches silent argument drift.

Pass `strict=False` to fall back to matching by tool name alone, which is useful while
an agent is still under heavy development.
