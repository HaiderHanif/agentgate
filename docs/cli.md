# CLI reference

```bash
agentgate --help
```

Exit codes are stable and CI-friendly:

| Code | Meaning |
| ---: | :--- |
| `0` | behaviour matched the golden trace |
| `1` | a behavioural regression was found |
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

---

## `agentgate list`

Show every golden trace with its tool path, step count, and cost.

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

## `agentgate verify`

Replay an agent against a golden trace and gate on the result.

```bash
agentgate verify app.agent:handle_refund traces/refund_flow.json \
  --format text \
  --max-cost 0.05 \
  --github
```

| Flag | Default | Meaning |
| :--- | :--- | :--- |
| `--format` | `text` | `text`, `markdown`, or `json` |
| `--report PATH` | - | also write the report to a file |
| `--strict / --no-strict` | strict | match tool arguments exactly, or by tool name only |
| `--github` | off | emit GitHub Actions annotations |
| `--max-cost` | from config | cost ceiling in USD |
| `--max-latency` | from config | latency budget in milliseconds |
| `--similarity` | from config | minimum final-output similarity, 0 to 1 |

Command-line flags override `[tool.agentgate.policy]` in `pyproject.toml`.

`--format markdown` is designed for posting as a pull request comment;
`--format json` for dashboards.

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
