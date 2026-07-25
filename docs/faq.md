# FAQ

The questions worth asking, including the ones without a good answer yet. A FAQ
that only asks flattering questions is a brochure.

---

## Positioning

### Why not just use LangSmith, Langfuse, Braintrust or Weave?

Those are observability and evaluation platforms: they show you what happened
and score outputs, usually against a dataset and often with an LLM judge.
agentgate does one narrower thing - it **fails a build when an agent's behaviour
changes** - and it is a library, not a service. No account, no data leaving the
machine, no LLM in the assertion path.

They are complementary. Observability tells you what your agent did in
production. agentgate stops a pull request from changing it.

### Why not Promptfoo, DeepEval, Ragas or OpenAI Evals?

Those evaluate **output quality** against a dataset - is this answer good? That
is a different question from **did this agent's decision path change since the
commit that worked?** Evals grade the answer. agentgate diffs the behaviour: the
tools called, their order, their arguments, the cost, and what was said.

An agent can produce a perfectly good answer while calling the refund API twice.

### Is this just mocked integration testing?

Largely yes, and the honest version of the pitch says so. The contributions are
the trace format, deterministic replay, the assertion vocabulary for agent-shaped
behaviour, and CI wiring with signed traces. If you already have disciplined
mocked integration tests around your agent, you have most of the value.

---

## Method

### One golden trace is one run that happened to work. Isn't that a weak oracle?

Yes. See [limitations](limitations.md#1-the-oracle-problem-agentgate-does-not-know-what-correct-means).
This is the strongest criticism of the approach and the reason absolute
constraints exist. A golden trace pins the shape of a run; an
`ArgumentConstraint` or `OutputPolicy` states a requirement that is true whether
or not the recording was any good. **Constraints, not comparison, are the real
answer to the oracle problem.** Comparison is the cheap first layer.

### Doesn't this just teach the agent to pass the test?

It can. A suite of golden traces is a specification of past behaviour, and
optimising against it produces an agent that reproduces the past. Mitigate the
same way you would anywhere else: keep scenarios adversarial, add cases from
real incidents, and rely on absolute constraints that encode requirements rather
than recordings.

### What if a change is an improvement, not a regression?

agentgate cannot tell the difference and does not try. It reports that behaviour
changed and makes a human decide. Accept the new behaviour by re-recording:

```bash
pytest --agentgate-update
```

The diff then shows up in code review, which is where the judgement belongs.

### Two different tool sequences can both be correct. Doesn't strict ordering break refactors?

Yes, which is why `tool_sequence` is switchable and `Ordering` /
`UnorderedGroup` exist. Use `UnorderedGroup` for genuinely order-independent
work and `Ordering` for the one relationship that matters ("verify before
refund"). Whole-sequence matching is the blunt default, not the recommendation.

### Will false positives destroy trust in the tool?

That is the main adoption risk, and it is why every check has a `severity`.
Opinion-shaped checks like output similarity can report as `warning` and never
block a merge, so developers do not learn to ignore red. Use the `Normalizer`
for volatile values rather than loosening thresholds.

### What about false negatives?

Worse, and harder to see. A green run means "the recorded scenarios did not
regress" - nothing more. The failure modes agentgate structurally cannot catch
are listed in [limitations](limitations.md).

---

## Security and privacy

### Traces contain sensitive data. What protects them?

`redact_trace` runs by default on save, masking by key and by value pattern
across tool arguments, tool results, model response text and the final output.
It is best-effort, not a compliance control - see
[limitations §6](limitations.md#6-redaction-is-best-effort). **Do not record
traces against production data.**

### Can someone weaken a gate by editing a trace?

Yes, unless you stop them. That is what signing is for:

```bash
export AGENTGATE_SIGNING_KEY=...      # a CI secret, never committed
agentgate sign traces/refund_flow.json
agentgate scan traces/ --require-signature
```

A tampered trace is rejected before replay runs. This only binds if the verify
job is a **required** status check on a protected branch and `traces/` is under
CODEOWNERS review. A gate a pull request can switch off is not a gate.

### What if a recorded tool result contains a prompt injection?

Replay feeds recorded results back verbatim, so it can replay an injection.
`Policy(detect_injection=True)` scans for known patterns and reports findings.
Pattern matching is a signal, not a defence - treat traces from outside your
team as hostile input and review them like code.

### Does replay sandbox my agent?

No. Your agent code runs with the privileges of the process that invoked it.
agentgate removes network calls to the model and tools; it does not contain
anything else your code does.

---

## Practical

### How much work is adoption?

Your agent must accept a context object and call `ctx.model(...)` and
`ctx.tool(...)`. That indirection is the real cost, and for an existing codebase
it is not free. There are adapters for the OpenAI and Anthropic message shapes;
LangChain, LlamaIndex, CrewAI, AutoGen and the Vercel AI SDK are not covered yet.

### Do traces need constant maintenance?

They need re-recording whenever behaviour intentionally changes, which is the
same cost as any snapshot test. Keep traces small and scenario-focused. A trace
covering twelve steps of unrelated work will need re-recording constantly and
will teach the team to re-record without reading the diff.

### Does it run offline?

Yes. Replay makes no network calls, so the suite is free, fast, and works in a
sealed CI runner.
