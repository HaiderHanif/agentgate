<div align="center">

# agentgate

**Stop shipping agent regressions.**

Golden-trace testing, deterministic replay, and behavioural CI gates for LLM agents.
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
3. **Compare** the decision path against the golden trace and your declared constraints.
4. **Block** the merge when behaviour changed and nobody meant it to.

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

## Three kinds of check

Comparing against a recording is only one of them, and on its own it is both too
strict and too weak. Too strict, because a valid refactor fails. Too weak, because
it inherits whatever the golden run happened to do.

### 1. Comparative - against the golden trace

```python
Policy(tool_sequence=True, tool_arguments=True, output_similarity=0.85)
```

### 2. Absolute - true regardless of any recording

```python
Policy(
    required_tools=["issue_refund"],
    forbidden_tools=["delete_customer"],
    ordering=[Ordering(first="issue_refund", second="send_email")],
    argument_constraints=[
        ArgumentConstraint(tool="issue_refund", path="amount", less_or_equal=500),
    ],
    max_cost_usd=0.05,
)
```

`Ordering` states the invariant that actually matters. Unlike whole-sequence
matching it survives valid refactors - an added audit step passes, refunding after
the email still fails.

`ArgumentConstraint` closes the right-tool-catastrophic-value gap: the agent calls
`issue_refund` correctly, in the correct position, for $10,000.

### 3. Content - what the agent said, not what it did

```python
Policy(
    output=OutputPolicy(
        must_contain=["reference number"],
        must_not_contain=["guaranteed", "goodwill bonus"],
        forbid_pii=["credit_card", "ssn"],
    ),
)
```

An agent can call every tool in the correct order and still promise a customer a
$10,000 bonus, leak a card number, or drop a legally required disclosure. That is
a different question from "did behaviour change", and it needs its own check.

| Check | Catches |
| :--- | :--- |
| `tool_sequence` | the agent reordered, skipped, or added actions |
| `tool_arguments` | same tools, wrong values |
| `ordering` | an invariant broke, without punishing refactors |
| `argument_constraint` | correct call, catastrophic value |
| `output_policy` | harmful, non-compliant, or PII-leaking text |
| `required_tools` | it *said* it refunded but never called the tool |
| `forbidden_tools` | the agent reached for something dangerous |
| `no_tool_errors` | a tool started failing |
| `cost_ceiling` | a prompt change quietly tripled spend |
| `step_count` | a reasoning loop started running away |
| `prompt_injection` | a payload in replayed tool output |
| `output_similarity` | the answer changed meaning, not just phrasing |

Every check runs on every replay, so one run reports every regression at once.
Soft checks can be downgraded to warnings rather than switched off.

## Determinism

Replay removes non-determinism from the model and the tools. It cannot remove it
from the agent's own code:

```python
from agentgate import deterministic

with deterministic(frozen_time="2026-07-25T09:00:00Z", seed=0):
    observed = replay_run(golden, agent)
```

For volatile values that must be present but always differ:

```python
Policy(normalize=Normalizer(uuids=True, timestamps=True, signed_urls=True))
```

False positives are what kill a CI check. These exist to prevent them.

## In CI

```yaml
- uses: HaiderHanif/agentgate@v1
  with:
    agent: app.agent:handle_refund
    trace: traces/refund_flow.json
    max-cost: "0.05"
```

Findings are emitted as GitHub annotations, so they appear inline in the diff.

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

Traces are plain JSON. A reviewer sees exactly which decision changed without
running anything. Behavioural change becomes a reviewable artifact instead of a
surprise in production.

## Safety

Traces are committed to source control, so sensitive tool arguments and results
are redacted on write, and prompts are stored only as digests.

```toml
[tool.agentgate]
trace_dir = "traces"
redact_keys = ["api_key", "customer_email", "card_number"]

[tool.agentgate.policy]
max_cost_usd = 0.05
```

Because a golden trace defines what "correct" means, editing one is a security
event. Traces can be signed:

```bash
export AGENTGATE_SIGNING_KEY=...
agentgate sign traces/refund_flow.json
```

Any post-signing edit is detected. Pair it with CODEOWNERS on the trace directory.

## Limitations

A green check means one specific thing:

> Against this recorded scenario, with these recorded tool results, the agent took
> the same decisions a human approved, and satisfied the constraints you declared.

It does **not** mean the agent is correct. In particular:

- **The golden trace might be wrong.** A recording captures what happened, not what
  should have. agentgate does not solve the oracle problem.
- **Replay does not test the model.** Change a prompt and replay verifies your
  orchestration, not whether the model now reasons worse. That needs a live eval.
- **Replay does not test failure handling** unless you recorded a failure.
- **Hidden state is invisible.** agentgate records the tool boundary, not the
  database behind it.
- **Output similarity is lexical, not semantic.** It cannot tell "refund complete"
  from "refund initiated". Use explicit `OutputPolicy` phrases for wording that
  carries legal or financial weight.
- **Coverage is exactly what you recorded.** Adversarial inputs, multi-turn
  manipulation, and unicode edge cases are invisible unless recorded.
- **Replay is not a sandbox.** It executes your agent code in-process.
- **Single-turn and synchronous only.** Multi-turn traces and parallel tool calls
  are unsupported rather than silently mis-verified.

agentgate is necessary but not sufficient. Run it alongside evals, adversarial
testing, and production sampling.

Full accounting: **[docs/limitations.md](docs/limitations.md)**.

## Docs

- [Quickstart](docs/quickstart.md)
- [CLI reference](docs/cli.md)
- [Writing policies](docs/policies.md)
- [Architecture](docs/architecture.md)
- [Limitations and security](docs/limitations.md)
- [FAQ](docs/faq.md) - including why not LangSmith, Promptfoo, or plain mocks
- [Worked example](examples/refund_agent/)

## Framework support

agentgate is framework-agnostic: if your agent can call `ctx.model()` and
`ctx.tool()`, it works. Adapters for OpenAI and Anthropic capture token counts and
pricing automatically.

- [x] Plain Python agents
- [x] OpenAI
- [x] Anthropic
- [ ] LangGraph (planned)
- [ ] CrewAI (planned)
- [ ] Multi-turn traces (planned)
- [ ] Async agents (planned)

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
