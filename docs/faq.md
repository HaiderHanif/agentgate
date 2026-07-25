# FAQ

Direct answers to the questions that get asked in public.

## Positioning

### Isn't this just mocked integration testing?

The mechanism is similar. The problem is not.

A mocked integration test asserts that a deterministic function produces an
expected value. agentgate asserts that a **probabilistic decision-maker** takes
an acceptable sequence of actions, where the acceptable set is broader than one
exact answer and narrower than anything-goes.

That difference is where the actual work lives: severity levels, ordering
constraints rather than exact sequences, argument bounds, cost budgets,
normalisation of volatile values, and similarity tolerances on output. None of
that exists in `unittest.mock`, because deterministic code does not need it.

If your agent is deterministic, you do not need agentgate. Use `unittest.mock`.

### Why not LangSmith, Langfuse, Braintrust, or Promptfoo?

Different question, different answer:

| Tool class | Question it answers |
| :--- | :--- |
| Observability (LangSmith, Langfuse) | what happened in production? |
| Evals (Promptfoo, DeepEval, Ragas) | how good is the output? |
| **agentgate** | **did behaviour change since the last approved run?** |

Observability tells you after the fact. Evals score quality on a rubric, need a
judge model, cost money per run, and are too slow and too noisy to block every
commit.

agentgate is a binary gate: free, offline, deterministic, millisecond-fast, and
cheap enough to run on every push. It is the unit test in that stack, not the
report.

Most serious teams should run all three. They are complements.

### Why is this better than a normal integration test?

It is not better. It covers something a normal integration test structurally
cannot: the *order and shape of decisions* a non-deterministic component makes.
Write both.

## Technical

### How do you ensure replay is deterministic?

Model responses and tool results are served from the recording, so neither the
network nor the model can introduce variance. `deterministic()` freezes `time`,
seeds `random`, and makes `uuid4` reproducible for non-determinism inside the
agent's own code.

What that does not cover is documented in [limitations](limitations.md). The
strongest guarantee is replay in a network-isolated container.

### What exactly is recorded?

Per model call: model name, prompt **digest** (not the prompt), response text,
input and output token counts, cost, latency.

Per tool call: name, arguments, result, latency, and error if it raised.

Per trace: schema version, name, agent, creation time, final output, metadata.

Prompts are digested rather than stored, so proprietary prompt text never enters
a committed artifact.

### How do you handle stateful tools?

Only partially, and this is a real limitation. agentgate records the tool
boundary, not the state behind it. Replay reproduces what the tool returned; it
cannot verify the world still works that way. Cover the other half with contract
tests on your tools.

### How do you handle parallel tool calls?

Unsupported. Concurrent calls have no deterministic order, so there is nothing
stable to assert against. Better to be explicitly unsupported than quietly wrong.

### How do you handle streaming?

Recording captures the assembled response, not the chunk sequence. Chunk-level
regressions are out of scope.

### How do you compare semantic meaning?

Honestly: it does not, and it says so. `output_similarity` is lexical. For
meaning-critical wording, use explicit `OutputPolicy` phrase rules. A required
phrase is a check you can reason about; an embedding score is a number you have
to trust.

### How do you avoid false positives?

False positives are the failure mode that kills adoption, so several features
exist only to prevent them: `Normalizer` for UUIDs, timestamps, and signed URLs;
`ignore_arguments` for volatile keys; `Ordering` constraints instead of exact
sequence matching; `severity="warning"` for opinion-shaped checks; and
`--agentgate-update` so intentional changes take one command.

### How do you avoid false negatives?

By not relying on comparison alone. Comparative checks inherit the golden run's
blind spots. Absolute constraints - `required_tools`, `forbidden_tools`,
`Ordering`, `ArgumentConstraint`, `OutputPolicy`, cost ceilings - hold
independently of what the recording did.

The repository's own test suite includes each named red-team scenario:
right-tool-wrong-amount, correct-actions-harmful-sentence, and
said-it-happened-without-doing-it.

### How do you handle tool schema changes?

Badly, deliberately. A renamed parameter is an argument change, so replay stops
and reports it rather than guessing. Re-record after a schema change; the diff is
the review artifact.

### How do you handle model upgrades?

Swap the model and re-record. The trace diff shows what the new model does
differently in decision terms, which is usually more informative than an eval
score moving by two points.

## Security

### Do traces contain secrets? Do you redact PII?

They can, which is why redaction runs on write with a default key list and prompts
are stored only as digests. Redaction is key-name based, so it will not catch a
card number in a free-text field. Read your first trace before committing it.

### Can traces be poisoned?

Yes, and it is the most serious attack on the design: rewrite the baseline and
broken behaviour passes forever. Defences are CODEOWNERS on the trace directory,
HMAC signing via `agentgate sign`, protected branches with required checks, and
reviewing trace diffs as behaviour changes. See [limitations](limitations.md).

### How do you sandbox replay?

agentgate does not sandbox. Replay avoids your real tools but still executes your
agent code in-process. Use the Docker image for untrusted code. Claiming
isolation the tool does not provide would be worse than saying this plainly.

### How do you prevent CI bypass?

That is a repository-settings problem, not a library problem: required status
checks, protected branches, CODEOWNERS, and reviewing workflow changes. agentgate
can report a finding; it cannot stop someone with write access from deleting the
job.

### How do you handle prompt injection in recorded tool outputs?

`Policy(detect_injection=True)` scans replayed tool results for known injection
shapes and reports them as warnings. Heuristic, not a filter - the goal is to stop
a payload from silently becoming your approved baseline.

## Product

### How much maintenance do traces require?

One command when behaviour changes intentionally (`pytest --agentgate-update`),
plus reviewing the resulting diff.

The cost scales with how strict your policies are. Teams that lean on `Ordering`
and `ArgumentConstraint` rather than whole-sequence matching re-record far less
often, because unrelated refactors stop triggering failures.

### What if multiple behaviours are valid?

That is what constraints are for. "Refund before emailing" as an `Ordering` rule
accepts every implementation that respects the invariant, including ones that add
an audit step or ask for confirmation first. Whole-sequence matching would reject
both improvements.

### What if the agent is correct but says something risky?

`OutputPolicy`. Required disclosures, forbidden phrases, regex rules, PII
detection, length limits. This was the strongest criticism levelled at the design
and it is now a first-class check.

### How do developers debug a failure?

The report shows the tool path with each step marked ok, changed, added, or
missing, then every finding with expected and actual values. In CI those become
inline pull request annotations. The golden trace is readable JSON, so the last
resort is reading the file.

### How do you measure coverage?

You cannot, meaningfully, and no tool in this category can. Trace count is not
coverage. Treat agentgate as protection for the paths you have deliberately
approved, and use adversarial evals and production sampling to find the paths you
have not.
