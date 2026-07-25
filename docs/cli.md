# CLI reference

```bash
agentgate --help
```

Exit codes are stable and CI-friendly:

| Code | Meaning |
| ---: | :--- |
| `0` | behaviour matched the golden trace |
| `1` | a behavioural regression, integrity failure, or injection finding |
| `2` | usage error - bad entrypoint, missing trace, unreadable file |

---

## `agentgate init`

Create the trace directory and print the configuration block to add.

```bash
agentgate init --dir traces
```

---

## `agentgate record`

Run an agent for real and save the result as a golden trace.

```bash
agentgate record app.agent:handle_refund \
  --model app.agent:model_fn \
  --tools app.agent:TOOLS \
  --name refund_flow \
  --dir traces
```

| Flag | Meaning |
| :--- | :--- |
| `--model` | entrypoint to a `Callable[[str], str \| ModelResult]` |
| `--tools` | entrypoint to a `dict[str, Callable]` |
| `--name` | trace name; the file becomes `<dir>/<name>.json` |
| `--dir` | output directory; defaults to the configured `trace_dir` |

This makes real model and tool calls. It costs money and can cause side effects.
Point it at a sandbox.

If the recorded run captured anything that looks like a prompt-injection payload,
the command says so. It still writes the trace - the decision to approve it is
yours - but you should not approve it blind.

---

## `agentgate list`

Show every golden trace with its tool path, step count, cost, and whether it is
signed.

```bash
agentgate list --dir traces
```

---

## `agentgate show`

Step-by-step view of a single trace.

```bash
agentgate show traces/refund_flow.json
```

---

## `agentgate sign`

Sign a golden trace in place so later tampering is detectable.

```bash
export AGENTGATE_SIGNING_KEY=...
agentgate sign traces/refund_flow.json
```

| Flag | Meaning |
| :--- | :--- |
| `--key` | signing key; defaults to `$AGENTGATE_SIGNING_KEY` |

A golden trace defines what "correct" means, which makes it a security control:
anyone who can quietly edit one can make broken behaviour look approved, and the
CI check becomes cover rather than protection.

The signature is an HMAC-SHA256 over a fingerprint of the trace's **behaviour** -
steps and final output - and deliberately excludes `created_at` and `metadata`, so
adding a note does not invalidate it while changing a tool argument does.

Signing does not replace review. Keep `CODEOWNERS` on the trace directory and
protected branches on `main`; signing catches the cases where those fail.

---

## `agentgate scan`

Audit golden traces for injection payloads and, optionally, signatures.

```bash
agentgate scan traces/*.json --require-signature
```

| Flag | Meaning |
| :--- | :--- |
| `--require-signature` | also fail if a trace is unsigned or was modified after signing |
| `--key` | signing key; defaults to `$AGENTGATE_SIGNING_KEY` |

Recorded tool output is attacker-controlled: a web search result, a support
ticket, a scraped page. A payload that lands in a golden trace is replayed into
the agent on every CI run, and if the agent complied when the trace was recorded,
that compliance is now the approved baseline.

Detection is heuristic. It reports what a human should look at; it cannot decide
intent.

---

## `agentgate verify`

Replay an agent against a golden trace and gate on the result.

```bash
agentgate verify app.agent:handle_refund traces/refund_flow.json \
  --format text \
  --max-cost 0.05 \
  --require-signature \
  --github
```

| Flag | Default | Meaning |
| :--- | :--- | :--- |
| `--format` | `text` | `text`, `markdown`, or `json` |
| `--report PATH` | - | also write the report to a file |
| `--strict / --no-strict` | strict | match tool arguments exactly, or by tool name only |
| `--github` | off | emit GitHub Actions annotations |
| `--require-signature` | off | refuse to run against an unsigned or tampered trace |
| `--key` | `$AGENTGATE_SIGNING_KEY` | signing key for the check above |
| `--max-cost` | from config | cost ceiling in USD |
| `--max-latency` | from config | latency budget in milliseconds |
| `--similarity` | from config | minimum final-output similarity, 0 to 1 |

Command-line flags override `[tool.agentgate.policy]` in `pyproject.toml`.

`--format markdown` is designed for posting as a pull request comment;
`--format json` for dashboards.

The signature check runs **before** replay, so a tampered trace never reaches
your agent.

---

## In CI

```yaml
- name: Verify agent behaviour
  env:
    AGENTGATE_SIGNING_KEY: ${{ secrets.AGENTGATE_SIGNING_KEY }}
  run: |
    agentgate scan traces/*.json --require-signature
    agentgate verify app.agent:handle_refund traces/refund_flow.json --github
```

Make both steps required status checks on a protected branch. A gate that a pull
request can switch off is not a gate.

---

## Entrypoints

Every `module:attribute` argument is imported from the current working
directory, the same way `uvicorn` and `gunicorn` resolve theirs:

```text
app.agent:handle_refund     -> attribute handle_refund of module app.agent
examples.refund_agent.agent:TOOLS
```

---

## pytest flags

The plugin is installed automatically with the package.

| Flag | Meaning |
| :--- | :--- |
| `--agentgate-update` | re-record golden traces instead of asserting |
| `--agentgate-dir DIR` | override the trace directory for this run |

Also configurable in `pytest.ini` / `pyproject.toml` as `agentgate_trace_dir`.
