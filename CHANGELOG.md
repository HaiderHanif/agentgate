# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Native adapters for the OpenAI SDK, Anthropic SDK, and LangGraph
- OpenTelemetry trace import
- Pull request comment bot with inline step diffs

## [0.1.0] - 2026-07-25

### Added
- Golden trace data model with model calls, tool calls, cost, and latency
- `Recorder` and `LiveContext` for capturing real agent runs
- `ReplayContext` and `replay_run` for deterministic, zero-cost replay
- Behavioural checks: tool sequence, tool arguments, required and forbidden tools,
  cost ceiling, latency budget, output similarity
- Reusable `Policy` bundles
- Plain-text divergence reports for terminals and CI logs
- pytest plugin exposing the `agentgate` fixture, with `--agentgate-update`
- CLI: `list`, `show`, `verify`, `version`
- MCP server mode for coding agents
- Composite GitHub Action for pull request gating

[Unreleased]: https://github.com/HaiderHanif/agentgate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/HaiderHanif/agentgate/releases/tag/v0.1.0
