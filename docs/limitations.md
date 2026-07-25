# Limitations and security considerations

The most dangerous failure mode for a testing tool is not a false alarm. It is a
green check over a path that was never tested. Teams calibrate their trust to
what a tool claims, so an overstated claim is a safety problem rather than a
marketing one.

Everything below is a known gap in agentgate 0.2.x.

---

## 1. The oracle problem: agentgate does not know what "correct" means

A golden trace records one run that a human looked at once and accepted. That is
evidence of a plausible path, not proof of a correct one. If the recorded run was
subtly wrong, every future run is measured against that mistake and the suite
will faithfully defend the bug.

- **Comparative checks** (`tool_sequence`, `tool_arguments`, `output_similarity`)
  inherit the golden run's judgement completely.
- **Absolute constraints** (`Ordering`, `ArgumentConstraint`, `OutputPolicy`,
  `required_tools`, `forbidden_tools`, cost and latency budgets) do not. They
  state a requirement that holds regardless of any recording.

Use absolute constraints for anything that actually matters. If the only thing
standing between you and a $10,000 refund is that the golden trace happened to
say $49.99, you have a diff, not a gate.

## 2. Output comparison is lexical, not semantic

`check_output_similarity` uses `difflib.SequenceMatcher`. It catches a wholly
different answer and ignores punctuation drift. It does not understand meaning:

| Golden | Observed | Score | Reality |
|---|---|---|---|
| `Refund complete.` | `Refund initiated.` | very high | materially different |
| `You will receive it today.` | `You may receive it soon.` | high | materially different |
| `Your account is closed.` | `Account closure requested.` | moderate | materially different |

agentgate passes all three. There is no LLM judge and no embedding model in the
library, deliberately: a non-deterministic grader inside a determinism tool is a
contradiction, and it would make the gate itself flaky.

Express meaning-sensitive wording as explicit rules instead:

```python
OutputPolicy(
    must_contain=["reference number"],
    must_not_contain=["guaranteed", "goodwill bonus"],
)
```

## 3. Coverage: only the paths you recorded are tested

A passing suite means "the scenarios in `traces/` did not regress". It says
nothing about the scenarios you never recorded, which is where incidents live.
There is no scenario generation, no fuzzing, and no coverage measure over the
agent's decision space. Three golden traces are three data points, not a safety
argument.

## 4. Replay is not production

Replay serves recorded results. It therefore cannot observe:

- tool timeouts, 5xx responses, rate limits, partial or malformed payloads
- auth expiry, permission changes, schema drift in a tool's response shape
- real latency (replayed steps record `latency_ms = 0.0`, so `max_latency_ms`
  is inert during replay and meaningful only on recorded runs)
- anything depending on hidden state: database rows, feature flags, caches,
  inventory, account status, cross-session memory

Replay answers "given these exact inputs, did the decision path change?". It
does not answer "does this agent work".

## 5. Determinism has edges

`deterministic()` patches module attributes. Code that captured a reference
before entry keeps the real one:

```python
from datetime import datetime   # captured at import time - NOT frozen
import datetime                 # datetime.datetime.now() - frozen
```

Also note:

- Wall clocks (`time.time`, `datetime.now`) are **frozen**. Elapsed clocks
  (`time.monotonic`, `perf_counter`) **advance** by a fixed step, because
  freezing them makes `while monotonic() - start < timeout` loop forever. Both
  are reproducible run to run.
- Naive `datetime.now()` returns the frozen instant with the timezone dropped,
  not converted to local time. Converting would reintroduce the machine's
  timezone as a source of divergence.
- Concurrency is not controlled. `Recorder` is **not thread-safe**, and parallel
  tool calls are not currently modelled - step order under concurrency is not
  guaranteed reproducible.

## 6. Redaction is best-effort

`redact_trace` masks by key and by value pattern, but:

- Email addresses and phone numbers are **not masked by default**. They are
  frequently load-bearing in a trace, and masking them silently would break more
  runs than it protects. Use `OutputPolicy(forbid_pii=[...])` to *detect* them.
- The `credit_card` pattern has **no Luhn check** and `phone` matches bare digit
  runs, so both over-match. `api_key` matches common prefixes only.
- `Trace.metadata` is free-form and is **not redacted**. Do not put secrets there.
- Tool *arguments* are masked by key only. Value-pattern rewriting of arguments
  would change what the agent is recorded as having asked for.

**Never record traces against production data.** Redaction reduces the blast
radius of a mistake; it is not a compliance control.

## 7. Trace integrity depends on how you wire CI

A golden trace is an executable expectation living in the repository, so anyone
who can edit it can weaken the gate. `agentgate sign` and
`agentgate scan --require-signature` exist for this, but they only bind if:

- `AGENTGATE_SIGNING_KEY` is a CI secret, not a committed value
- the verify job is a **required** status check on a protected branch
- `.github/` and `traces/` are covered by CODEOWNERS review

A gate that a pull request can switch off is not a gate. agentgate cannot
enforce any of this for you - it is repository configuration.

## 8. Recorded tool output is untrusted input

A recorded tool result can contain prompt-injection text, and replay feeds it
back to the agent verbatim. `Policy(detect_injection=True)` scans for known
patterns and reports findings, but pattern matching is not a defence - it is a
signal. Treat any trace from an external source as hostile until reviewed.

agentgate does **not** sandbox replay. Your agent code runs with the privileges
of the process that invoked it.

## 9. Not yet supported

Multi-turn conversations, parallel tool calls, streaming responses, async
agents, multiple acceptable traces for one scenario, fault injection during
replay, a trace viewer UI, and retention/deletion tooling. Framework adapters
exist for OpenAI and Anthropic message shapes only; LangChain, LlamaIndex,
CrewAI, AutoGen and the Vercel AI SDK are not covered.

---

If you hit a failure mode that is not listed here, that is a documentation bug
as much as a code one. Please open an issue.
