# Security policy

## Reporting a vulnerability

Report security issues privately through
[GitHub Security Advisories](https://github.com/HaiderHanif/agentgate/security/advisories/new).

Please do not open a public issue for a vulnerability.

Expect an acknowledgement within 72 hours and an assessment within seven days.
If a fix is warranted, you will be credited in the advisory unless you prefer
otherwise.

## Supported versions

The latest minor release receives security fixes.

## Threat model

agentgate is a developer tool that reads trace files and executes agent code. The
threats worth taking seriously:

### Traces are sensitive artifacts

Golden traces contain real tool arguments and results from the recorded run.
Redaction runs on every write against a configurable key list, and prompts are
stored only as digests - but redaction is **key-name based and is not a
guarantee**. It will not catch a card number inside a free-text field.

Read your first trace before committing it. Never record against production
customer data.

### Trace poisoning

A golden trace defines what "correct" means. An attacker who edits one turns the
CI check into cover for broken behaviour. This is the most serious attack against
the design.

Defences:

- `CODEOWNERS` on trace directories (configured in this repository)
- `agentgate sign` - HMAC-SHA256 over the behavioural content of a trace
- `verify_trace()` - detects any post-signing modification
- protected branches with required status checks
- reviewing trace diffs as behaviour changes, because that is what they are

### Replay executes agent code

Replay does not call your real tools, but it **does run your agent in the current
process**. If the agent shells out, writes files, or imports something hostile,
replay does too. agentgate provides no sandbox. Use the published Docker image
for untrusted code.

### Prompt injection in recorded tool output

Tool results may contain attacker-controlled text. Once recorded, that payload is
replayed into the agent on every CI run, and if the agent complied during
recording, the compliance is now the approved baseline.

`Policy(detect_injection=True)` scans for known injection shapes and reports them
as warnings. It is a heuristic, not a filter.

### CI bypass

A library cannot stop someone with write access from deleting the job that runs
it. Protect the gate with required status checks, protected branches, and
CODEOWNERS on workflow files.

## What is out of scope

- Sandboxing untrusted agent code (use containers)
- Guaranteeing complete redaction of unstructured data
- Retention, deletion, or access control for trace storage
- Anything downstream of a compromised signing key

See [docs/limitations.md](docs/limitations.md) for the full honest accounting.
