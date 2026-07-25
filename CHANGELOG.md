# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. See [the roadmap](README.md#roadmap) for what is planned.

## [0.2.0] - 2026-07-25

This release is the answer to a full red-team review of the project. The theme is
that comparing a run against one golden trace is not a definition of correct
behaviour, so 0.2.0 adds checks that hold **independently** of any recording.

### Added

- `OutputPolicy`: required and forbidden phrases, regex rules, length limits, and
  built-in PII detection for emails, phone numbers, card numbers, national
  identifiers, and API keys. Catches the case where the tool calls are correct but
  the agent promises something it should not.
- `ArgumentConstraint`: bounds on individual tool arguments by dotted path
  (`amount` less than 500, `currency` one of a set, and so on), so a call to the
  right tool with a catastrophic argument still fails.
- `Ordering` and `UnorderedGroup`: express the invariants that actually matter
  (refund before the confirmation email) without failing valid refactors that add
  a step or reorder independent checks.
- `Normalizer`: strips UUIDs, timestamps, epochs, hex identifiers, and signed URL
  parameters from both sides of a comparison, removing a large class of false
  positives.
- `deterministic()`: context manager that freezes time, seeds randomness, and makes
  `uuid4` reproducible during replay.
- Trace signing with HMAC-SHA256 (`sign_trace`, `verify_trace`) plus the
  `agentgate sign` command and `--require-signature` on `verify` and `scan`. The
  fingerprint covers behaviour only, so re-annotating a trace does not invalidate it.
- `agentgate scan`: audits golden traces for prompt-injection payloads sitting in
  recorded tool output, and optionally for signatures.
- Injection detection across five pattern families, reported as a warning by
  default because a scanner that fails builds on false positives gets disabled.
- `.github/CODEOWNERS` requiring review on trace directories and CI workflows.
- `docs/limitations.md` and `docs/faq.md`: an explicit statement of what AgentGate
  does not verify, and answers to the hard questions.

### Changed

- `Policy` now carries `ordering`, `unordered_groups`, `argument_constraints`,
  `output`, `normalize`, `detect_injection`, and `injection_severity`.
- Assertions are organised into three families - comparative, absolute, and content
  - to make clear which checks depend on the golden trace and which do not.
- `agentgate list` shows whether each trace is signed.
- `agentgate record` warns when it captures a possible injection payload.
- Configuration through `[tool.agentgate]` in `pyproject.toml`, including
  project-wide policy defaults.
- Automatic redaction of sensitive tool arguments and results before traces are
  written to disk.
- Token pricing table with `register_model()` for private and fine-tuned models.
- OpenAI and Anthropic adapters that capture token counts and cost automatically.
- Markdown and JSON report formats, plus `--github` for inline pull request
  annotations.
- Severity levels on violations, so soft checks warn instead of failing the build.
- `agentgate.diff` is deprecated in favour of `agentgate.reporting`; the old import
  path still works and will be removed in 1.0.
- Model functions may return a `ModelResult` carrying token counts, in addition to
  a plain string.
- Trace loading validates `schema_version` and fails clearly on malformed files.
- Docker image, pre-commit configuration, CodeQL analysis, and a CI matrix through
  Python 3.13.

### Fixed

- Tool exceptions are recorded before being re-raised, so a failing run still
  produces a diagnosable trace.

### Known limitations

Deliberate, and documented rather than hidden: output similarity is lexical and
not semantic; replay is single-turn and sequential, so parallel tool calls,
streaming, and multi-turn conversations are not verified; replay is not
sandboxed. See `docs/limitations.md`.

## [0.1.0] - 2026-07-25

### Added

- Initial release: trace model, recorder, deterministic replay, behavioural
  assertions, pytest plugin, CLI, and MCP server.
