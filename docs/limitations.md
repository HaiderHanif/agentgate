# Limitations and security considerations

This page exists because a testing tool that overstates its coverage is worse
than no testing tool. A green agentgate check means one specific thing, and it is
narrower than "the agent is correct".

## What a passing run actually proves

> Against **this recorded scenario**, with **these recorded tool results**, the
> agent took the same decisions it took when a human approved that recording,
> and satisfied the constraints you declared.

That is genuinely valuable and it is not a correctness proof.

## What it does not prove

### The golden trace might not be correct

A recording captures what happened, not what should have happened. If the
original run got lucky, took a shortcut, or was reviewed carelessly, agentgate
will defend that behaviour forever with complete confidence.

**This is the oracle problem, and the tool does not solve it.** A trace is only
as good as the human who approved it.

Mitigate it by treating trace files as reviewed artifacts: put them behind
CODEOWNERS, require a second approver, and state absolute invariants as
`required_tools`, `Ordering`, and `ArgumentConstraint` rules rather than relying
on the recording alone. Constraints are independent of what the golden run did,
which is exactly why they are worth writing.

### Replay does not test the model

Model responses are served from the recording. If you change a prompt, replay
tells you whether your **orchestration** still behaves correctly given the old
response. It cannot tell you whether the new prompt makes the model reason worse.

That requires a live eval. agentgate is not one, and does not replace one.

Use replay for orchestration regressions on every commit, and live evals on a
slower cadence for reasoning quality. They answer different questions.

### Replay does not test failure handling

Recorded tool results are the results you recorded - usually successful ones.
Replay will not surface a timeout, a 500, malformed JSON, an expired token, or a
rate limit unless you deliberately recorded a run containing one.

Record failure scenarios explicitly. A trace where `issue_refund` raises is a
valid, useful golden trace.

### Replay does not capture hidden state

agentgate records the tool boundary, not the world behind it. If a tool returned
`{"eligible": true}` because the test account was premium, replay reproduces that
answer regardless of whether the same is true in production.

This is a real gap. Replay verifies the agent's logic given an environment; it
cannot verify that the environment still behaves that way. Contract tests on your
tools cover the other half.

### Determinism is only as good as the environment

`deterministic()` freezes `time`, `random`, and `uuid`. It does not freeze:

- functions captured before the block (`from time import time`)
- C extensions with their own clocks
- concurrency and thread scheduling
- environment variables and locale
- network access your tools perform outside the recorded boundary

Run replay in a container with no network for the strongest guarantee.

### Comparison is lexical, not semantic

`output_similarity` is a character-ratio measure. It reliably catches a wholly
different answer and reliably ignores punctuation drift. It **cannot** tell that
"refund complete" and "refund initiated" mean different things - they are one
word apart and score as nearly identical.

If a distinction is meaning-critical, encode it explicitly:

```python
OutputPolicy(
    must_contain=["has been requested"],
    must_not_contain=["is complete", "has been closed"],
)
```

Do not rely on similarity scoring for compliance wording. It is a smoke alarm,
not a fire inspection.

### Coverage is exactly what you recorded

agentgate tests the scenarios in your trace directory. Nothing else. Unseen
inputs, adversarial prompts, multi-intent requests, unicode edge cases, and
long-session drift are all invisible to it unless recorded.

**agentgate is necessary but not sufficient.** Pair it with adversarial evals,
fuzzing, production sampling, and human review.

### Single-turn only, for now

The trace model represents one agent run. Multi-turn manipulation - trust built
over turn one, an exception requested in turn two, a policy violation in turn
three - is not currently expressible. Multi-turn traces are on the roadmap.

### No parallel tool calls

Concurrent calls have no deterministic order, so there is nothing stable to
assert against. Agents issuing parallel tool calls are unsupported rather than
silently mis-verified.

## Security considerations

### Traces are sensitive artifacts

A golden trace contains real tool arguments and real tool results from the
recorded run. That can include customer names, emails, internal IDs, and
financial records.

agentgate redacts a default key list on write, and prompts are stored only as
digests. **Redaction is key-name based and is not a guarantee.** It will not
catch a card number embedded in a free-text field.

Before committing your first trace:

1. Open the JSON and read it.
2. Extend `redact_keys` for your domain.
3. Record against synthetic data where you can.
4. Never commit a trace recorded against production customer data.

### Traces are a security control, so protect them

An attacker who edits a golden trace redefines "correct" and turns the CI check
into cover. Defences, in order of importance:

1. **CODEOWNERS on the trace directory** - trace changes need a named reviewer.
2. **Signing** - `agentgate sign` adds an HMAC over the behavioural content;
   `verify_trace` detects any post-signing edit.
3. **Required status checks on a protected branch** - so the gate cannot be
   skipped by editing a workflow in the same pull request.
4. **Review trace diffs like code.** A trace diff *is* a behaviour change.

### Replay is not a sandbox

Replay does not call your real tools, but it **does execute your agent code** in
the current process. If the agent shells out, writes files, or imports something
hostile, replay will do that too.

Run untrusted agent code in a container. The published Docker image exists for
this. Do not treat "it's only a test" as isolation.

### Recorded tool output can carry prompt injections

Tool results from web searches, tickets, or scraped pages may contain injection
payloads. Once recorded, they are replayed into the agent on every run - and if
the agent complied when the trace was made, that compliance is now the approved
baseline.

Enable `Policy(detect_injection=True)`. It reports as a warning by default,
because pattern matching cannot judge intent and a scanner that fails builds on
false positives gets switched off within a week.

### Retention

agentgate stores traces as files in your repository. It has no retention or
deletion policy, because it has no storage layer to apply one to. If you operate
under GDPR, HIPAA, or PCI-DSS, treat the trace directory as regulated data and
apply your own controls.

## How to use this tool responsibly

- Treat a passing gate as "no known regression", not "safe to ship".
- Write absolute constraints, not just comparisons against a recording.
- Add an `OutputPolicy` for anything with legal or financial consequences.
- Record failure paths, not only happy paths.
- Review trace diffs as carefully as code diffs.
- Run it alongside evals, not instead of them.
