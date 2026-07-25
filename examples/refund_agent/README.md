# Example: refund agent

A three-step agent that looks up an order, issues a refund, and notifies the customer.
The ordering matters: **never email the customer before the money actually moves.**

This example ships with a committed golden trace, and CI verifies the agent against it
on every pull request.

## Run the verification

```bash
agentgate verify \
  examples.refund_agent.agent:refund_agent \
  examples/refund_agent/traces/refund_flow.json \
  --max-cost 0.05
```

Expected output:

```text
agentgate: refund_flow
======================

PASS - 3 tool calls matched the golden trace
```

## See a regression get caught

`agent.py` also contains `regressed_refund_agent`, which emails before refunding.
Point the verifier at it:

```bash
agentgate verify \
  examples.refund_agent.agent:regressed_refund_agent \
  examples/refund_agent/traces/refund_flow.json
```

It exits non-zero and prints exactly which step moved.

## Inspect the trace

```bash
agentgate show examples/refund_agent/traces/refund_flow.json
```
