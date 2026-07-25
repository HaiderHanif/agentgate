# Refund agent example

A worked example of the failure agentgate is built to catch.

## The bug

The agent must **issue the refund before emailing the customer**. Swap those two
lines and:

- every unit test still passes
- the final output is byte-for-byte identical
- the token cost is identical
- the LLM-as-judge score is identical

...and customers get told their money is on the way when it never left. Nothing
in a conventional test suite looks at the *order of actions*. agentgate does.

## Run it

```bash
pip install -e ".[dev]"
pytest examples/refund_agent -v
```

Two tests run. The first replays the correct agent against the committed golden
trace and passes. The second replays the regressed agent and asserts that the
gate fires.

## What the gate reports

```text
agentgate: refund_flow
======================

FAIL - 1 behavioural finding(s)

Tool call path
--------------
  ok        1. lookup_order
  changed   2. issue_refund -> send_email
  changed   3. send_email -> issue_refund

Findings
--------
  [error] [tool_sequence] tool call order diverged from the golden trace
      expected: ['lookup_order', 'issue_refund', 'send_email']
      actual:   ['lookup_order', 'send_email', 'issue_refund']
```

## Re-recording

When a behaviour change is intentional, re-record and commit the new trace so it
shows up in code review as a deliberate diff:

```bash
pytest examples/refund_agent --agentgate-update
git diff examples/refund_agent/traces/
```

The golden trace is plain JSON, so a reviewer can see exactly which decision
changed without running anything.

## Going live

`model_fn` here is a stub so the example runs offline and free. To record
against a real model:

```python
from openai import OpenAI
from agentgate.adapters import openai_model_fn

model_fn = openai_model_fn(OpenAI(), model="gpt-4o-mini")
```

Recording costs real money and causes real side effects. Replay never does.
