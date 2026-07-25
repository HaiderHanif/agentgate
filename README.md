<h1 align="center">agentgate</h1>

<p align="center">
  <b>Regression gating for AI agents.</b><br>
  Record what a working agent did. Replay it deterministically. Fail CI when the behaviour changes.
</p>

<p align="center">
  <a href="https://github.com/HaiderHanif/agentgate/actions/workflows/ci.yml"><img src="https://github.com/HaiderHanif/agentgate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-0B0B0B?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-0B0B0B?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/status-alpha-0B0B0B?style=flat-square" alt="Status">
</p>

---

## The problem

You ship an agent that handles refunds. It works. Two weeks later someone tweaks a prompt, or the model provider ships an update, and now the agent **emails the customer before the refund is actually issued**.

Nobody notices until a customer complains.

Normal code has a safety net for exactly this: you write a test, the test fails, you fix it. Agents don't, because they say something slightly different on every run. So most teams skip testing entirely and hope.

## What agentgate does

It makes agents testable by asserting on **what the agent did**, not **what it said**.

```
  record  ->  a working run is captured as a golden trace (tools, order, args, cost)
  replay  ->  the run is re-executed with the model and tools mocked from that trace
  compare ->  wording may drift freely; the decision path may not
  gate    ->  CI fails the pull request, pointing at the exact diverging step
```

Replay makes no network calls. A 50-trace suite runs in seconds and costs **$0**.

---

## Install

```bash
pip install agentgate
```

## 60-second example

Write the agent against a context object instead of calling the model and tools directly:

```python
def refund_agent(ctx) -> str:
    ctx.model("Customer wants a refund for order A-1042. Plan the steps.")
    order = ctx.tool("lookup_order", order_id="A-1042")
    ctx.tool("issue_refund", order_id="A-1042", amount=order["amount"])
    ctx.tool("send_email", to="customer@example.com", template="refund_confirmed")
    return f"Refund of ${order['amount']:.2f} issued for order A-1042."
```

**Record once**, while it behaves correctly:

```python
from agentgate import record_run

trace = record_run("refund_flow", refund_agent, model_fn, tools, trace_dir="traces")
```

**Assert forever**, in your normal test suite:

```python
def test_refund_flow(agentgate):
    agentgate.assert_matches(refund_agent, "refund_flow")
```

When someone reorders the refund and the email, the test fails like this:

```text
agentgate: refund_flow
======================

FAIL - 1 behavioural regression(s)

Tool call path
--------------
   1. ok       lookup_order
   2. changed  issue_refund -> send_email
   3. changed  send_email -> issue_refund

Violations
----------
  [tool_sequence] tool call order diverged from the golden trace
      expected: ['lookup_order', 'issue_refund', 'send_email']
      actual:   ['lookup_order', 'send_email', 'issue_refund']
```

No API key. No tokens spent. Sub-second.

---

## What you can assert

| Check | Catches |
| :--- | :--- |
| `tool_sequence` | The agent reordered, skipped, or added a step |
| `tool_arguments` | Same tools, wrong values passed |
| `required_tools` | A mandatory step (audit log, verification) silently disappeared |
| `forbidden_tools` | The agent reached for something it must never touch |
| `max_cost_usd` | A prompt change quietly tripled token spend |
| `max_latency_ms` | The run drifted past its time budget |
| `output_similarity` | The final answer changed meaningfully, not just cosmetically |

Bundle them into a reusable `Policy`:

```python
from agentgate import Policy

policy = Policy(
    required_tools=["lookup_order", "issue_refund"],
    forbidden_tools=["delete_customer"],
    max_cost_usd=0.05,
    output_similarity=0.85,
)

def test_refund_flow(agentgate):
    agentgate.assert_matches(refund_agent, "refund_flow", policy)
```

---

## Use it in CI

```yaml
- uses: HaiderHanif/agentgate@v0
  with:
    agent: examples.refund_agent.agent:refund_agent
    trace: examples/refund_agent/traces/refund_flow.json
    max-cost: "0.05"
```

The job fails on divergence and prints the exact step that changed.

## Command line

```bash
agentgate list                                  # every golden trace and its cost
agentgate show traces/refund_flow.json          # the recorded decision path
agentgate verify pkg.agent:refund_agent traces/refund_flow.json --max-cost 0.05
```

## Use it from your coding agent

agentgate also runs as an MCP server, so Claude Code, Cursor, Codex, or Gemini CLI can inspect and run your evals directly:

```bash
pip install "agentgate[mcp]"
python -m agentgate.mcp_server
```

---

## How it works

```
           LIVE RUN                              REPLAY RUN
  agent -> LiveContext -> real model      agent -> ReplayContext -> golden trace
                       -> real tools                             -> golden trace
              |                                        |
              v                                        v
        golden trace  ------------ compare ------->  observed trace
                                      |
                                 violations -> report -> exit code
```

The agent code is identical in both modes. The only thing that changes is the context it is handed. See [docs/architecture.md](docs/architecture.md).

---

## Why not just...

**...write normal unit tests?** They break on every harmless rewording, so teams delete them.

**...use an LLM-as-judge eval?** Useful, but slow, non-deterministic, and it costs money on every CI run. agentgate is the deterministic layer underneath: it catches structural regressions in milliseconds, leaving judges for genuine quality questions.

**...use a hosted observability platform?** Those tell you what broke *after* it reached production. agentgate blocks the pull request.

---

## Roadmap

- [x] Golden trace format, recorder, deterministic replay
- [x] Behavioural policy checks and CI-ready reports
- [x] pytest plugin and GitHub Action
- [x] MCP server mode
- [ ] Native adapters: OpenAI SDK, Anthropic SDK, LangGraph
- [ ] OpenTelemetry trace import
- [ ] PR comment bot with inline step diffs
- [ ] Flake detection across repeated live runs

## Contributing

Issues and pull requests are welcome - see [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labelled.

## License

MIT. See [LICENSE](LICENSE).

---

<p align="center"><sub>Built by <a href="https://github.com/HaiderHanif">Haider Hanif</a> - AI Automation Engineer</sub></p>
