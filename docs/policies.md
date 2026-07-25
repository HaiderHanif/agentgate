# Writing policies

A `Policy` decides what counts as a regression. The default policy is
intentionally strict: any change to the decision path fails.

```python
from agentgate import Policy

Policy()  # tool order, arguments, tool errors, and output similarity all checked
```

## The checks

### Structural

```python
Policy(
    tool_sequence=True,     # same tools, same order
    tool_arguments=True,    # same values passed to them
    no_tool_errors=True,    # nothing threw
)
```

`tool_sequence` is the one that earns its keep. It catches reordering, skipped
steps, and extra steps - the failures that leave output and cost untouched.

### Ignoring volatile arguments

Timestamps, request IDs, and nonces change every run and mean nothing:

```python
Policy(ignore_arguments=["request_id", "timestamp", "idempotency_key"])
```

Matching is case-insensitive.

### Safety rails

```python
Policy(
    required_tools=["audit_log", "issue_refund"],
    forbidden_tools=["delete_customer", "send_wire"],
)
```

These are independent of the golden trace. Use them for invariants that must hold
no matter how the agent evolves - the compliance step that must always run, the
destructive tool that must never be reached in this flow.

### Budgets

```python
Policy(
    max_cost_usd=0.05,
    max_latency_ms=5000,
    max_extra_steps=2,
)
```

`max_extra_steps` is the runaway-loop guard: it fails when a run uses more steps
than the golden trace, beyond the tolerance you allow.

Cost is computed from token counts using the pricing table. Register private
models yourself:

```python
from agentgate.pricing import register_model

register_model("internal-7b", input_per_mtok=0.05, output_per_mtok=0.10)
```

### Output similarity

```python
Policy(output_similarity=0.85)
```

Compares the final output to the golden run's, tolerating rewording while
catching a genuinely different answer. This is the softest check in the set, and
the one most likely to produce noise. Two ways to loosen it:

```python
Policy(output_similarity=None)                           # off
Policy(output_similarity_severity="warning")             # report, do not fail
```

Warnings appear in the report and in GitHub annotations, but do not fail the
build.

## Configuration file

Set project defaults once:

```toml
[tool.agentgate]
trace_dir = "traces"
strict = true
redact_keys = ["api_key", "customer_email"]

[tool.agentgate.policy]
tool_sequence = true
ignore_arguments = ["request_id"]
required_tools = ["audit_log"]
max_cost_usd = 0.05
output_similarity = 0.85
```

Per-test policies override the file:

```python
def test_refund(agentgate):
    agentgate.assert_matches(handle_refund, "refund_flow", Policy(max_cost_usd=0.01))
```

## Strict mode

In strict mode (the default) replay serves a tool result only when the tool name
**and** its arguments match the recording. A miss raises immediately - the agent
asked for something it never asked for during the good run.

Non-strict mode matches on tool name alone:

```python
agentgate.assert_matches(handle_refund, "refund_flow", strict=False)
```

Use it while a flow is still churning, then tighten up before you rely on the
gate. Non-strict replay can mask exactly the argument drift you want to catch.

## Choosing a starting policy

A reasonable default for a new project:

```python
Policy(
    tool_sequence=True,
    tool_arguments=True,
    ignore_arguments=["request_id", "timestamp"],
    forbidden_tools=[...],           # your destructive tools
    max_cost_usd=<3x your median>,
    output_similarity_severity="warning",
)
```

Hard-fail on structure and safety. Warn on wording. Tighten as the flow settles.
