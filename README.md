<div align="center">

# agentgate

**Stop shipping agent regressions.**

Golden-trace testing, deterministic replay, and CI gates for LLM agents.
Runs as a pytest plugin, a CLI, a GitHub Action, or an MCP server.

[![CI](https://img.shields.io/github/actions/workflow/status/HaiderHanif/agentgate/ci.yml?branch=main&style=flat-square&labelColor=0B0B0B&color=0B0B0B)](https://github.com/HaiderHanif/agentgate/actions)
[![PyPI](https://img.shields.io/pypi/v/agentgate?style=flat-square&labelColor=0B0B0B&color=0B0B0B)](https://pypi.org/project/agentgate/)
[![Python](https://img.shields.io/pypi/pyversions/agentgate?style=flat-square&labelColor=0B0B0B&color=0B0B0B)](https://pypi.org/project/agentgate/)
[![License](https://img.shields.io/badge/license-MIT-0B0B0B?style=flat-square&labelColor=0B0B0B)](LICENSE)

</div>

---

## The problem

You tweak a prompt. Tests pass. Evals score the same. Two days later you find out
the agent started emailing customers *before* issuing their refunds.

Nothing was broken in a way any test could see. The output was fine. The cost was
fine. The **order of actions** changed, and nothing was watching that.

Agent regressions hide in the decision path, not the text.

## The approach

1. **Record** one good run. Every model call, every tool call, arguments, cost, latency.
2. **Replay** it deterministically. No network, no side effects, no spend, sub-second.
3. **Compare** the decision path against the golden trace.
4. **Block** the merge when behaviour changed and nobody meant it to.

It is a dashcam for your agent, plus a rehearsal room where you can re-run the
exact same conditions forever.

## Install

```bash
pip install agentgate
```

## Quickstart

Your agent takes a context object and uses it for model and tool calls. That one
convention is what makes a run recordable and replayable.

```python
def handle_refund(ctx):
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model(f"Should we refund order {order['id']}?")

    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
    ctx.tool("send_email", to=order["email"])

    return f"Refunded ${order['amount']}. {decision}"
```

Record a golden trace once:

```bash
agentgate record app.agent:handle_refund \
  --model app.agent:model_fn \
  --tools app.agent:TOOLS \
  --name refund_flow
```

Gate on it forever:

```python
def test_refund_flow(agentgate):
    agentgate.assert_matches(handle_refund, "refund_flow")
```

When the agent regresses, you get the decision path, not a stack trace:

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

Commit the trace. Now every pull request is checked against known-good behaviour.

## What it asserts

Behaviour, not wording. Phrasing drifts constantly and harmlessly; these do not.

| Check | Catches |
| :--- | :--- |
| `tool_sequence` | the agent reordered, skipped, or added actions |
| `tool_arguments` | same tools, wrong values |
| `required_tools` | a mandatory step silently disappeared |
| `forbidden_tools` | the agent reached for something dangerous |
| `no_tool_errors` | a tool started failing |
| `cost_ceiling` | a prompt change quietly tripled spend |
| `latency_budget` | the agent got slower |
| `step_count` | a reasoning loop started running away |
| `output_similarity` | the answer changed meaning, not just phrasing |

Every check runs on every replay, so one run reports every regression at once.

```python
from agentgate import Policy

POLICY = Policy(
    required_tools=["issue_refund"],
    forbidden_tools=["delete_customer"],
    max_cost_usd=0.05,
    output_similarity=0.85,
)
```

## In CI

```yaml
- uses: HaiderHanif/agentgate@v1
  with:
    agent: app.agent:handle_refund
    trace: traces/refund_flow.json
    max-cost: "0.05"
```

Findings are emitted as GitHub annotations, so they appear inline in the pull
request diff.

## For coding agents

```bash
pip install "agentgate[mcp]"
python -m agentgate.mcp_server
```

Exposes `list_traces`, `show_trace`, and `verify_agent` over MCP, so Claude Code,
Cursor, or Codex can check whether a change regressed your agent before it
suggests shipping it.

## Re-recording

Behaviour changes are often intentional. Re-record, then review the diff:

```bash
pytest --agentgate-update
git diff traces/
```

Traces are plain JSON. A reviewer can see exactly which decision changed without
running anything. Behavioural change becomes a reviewable artifact instead of a
surprise in production.

## Safety

Traces are committed to source control, so sensitive tool arguments and results
are redacted on write. Configure the key list in `pyproject.toml`:

```toml
[tool.agentgate]
trace_dir = "traces"
redact_keys = ["api_key", "customer_email", "card_number"]

[tool.agentgate.policy]
max_cost_usd = 0.05
```

Replay never makes a network call and never fires a side effect, by construction.

## Docs

- [Quickstart](docs/quickstart.md)
- [CLI reference](docs/cli.md)
- [Writing policies](docs/policies.md)
- [Architecture](docs/architecture.md)
- [Worked example](examples/refund_agent/)

## Framework support

agentgate is framework-agnostic: if your agent can call `ctx.model()` and
`ctx.tool()`, it works. Adapters for OpenAI and Anthropic capture token counts
and pricing automatically.

- [x] Plain Python agents
- [x] OpenAI
- [x] Anthropic
- [ ] LangGraph (planned)
- [ ] CrewAI (planned)
- [ ] Async agents (planned)

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
