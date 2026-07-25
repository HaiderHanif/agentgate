# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Configuration through `[tool.agentgate]` in `pyproject.toml`, including project-wide policy defaults.
- Automatic redaction of sensitive tool arguments and results before traces are written to disk.
- Token pricing table with `register_model()` for private and fine-tuned models, so cost assertions work out of the box.
- OpenAI and Anthropic adapters that capture token counts and cost automatically.
- `agentgate init` and `agentgate record` commands.
- Markdown and JSON report formats, plus `--github` for inline pull request annotations.
- Working `--agentgate-update` re-recording via `LiveSpec`.
- `verify_agent` MCP tool, so coding agents can run the gate directly.
- Severity levels on violations, so soft checks can warn instead of failing the build.
- New checks: `no_tool_errors` and `step_count` for runaway reasoning loops.
- `ResolutionError`, `TraceFormatError`, and `ConfigError` under a common `AgentGateError` base.
- Docker image, pre-commit configuration, CodeQL analysis, and an expanded CI matrix through Python 3.13.

### Changed

- `agentgate.diff` is deprecated in favour of `agentgate.reporting`; the old import path still works and will be removed in 1.0.
- Model functions may now return a `ModelResult` carrying token counts, in addition to a plain string.
- Trace loading validates `schema_version` and fails clearly on unsupported or malformed files.

### Fixed

- Tool exceptions are now recorded before being re-raised, so a failing run still produces a diagnosable trace.

## [0.1.0] - 2026-07-25

### Added

- Initial release: trace model, recorder, deterministic replay, behavioural assertions, pytest plugin, CLI, and MCP server.
