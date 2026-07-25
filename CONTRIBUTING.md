# Contributing to agentgate

Thanks for taking the time to contribute.

## Getting set up

```bash
git clone https://github.com/HaiderHanif/agentgate.git
cd agentgate
python -m venv .venv && source .venv/bin/activate
make install
make check
```

`make check` runs lint, type checking, and the test suite - the same gate CI applies.

## Ground rules

- **One concern per pull request.** Small, reviewable changes get merged.
- **Tests are required** for behaviour changes. Bug fixes should include a test that fails before the fix.
- **Types are required.** `mypy --strict` must pass on `src/agentgate`.
- **Formatting is automated.** Run `ruff format src tests` before pushing.
- **Public API changes** need a note in `CHANGELOG.md`.

## Commit messages

Conventional commits, e.g.:

```
feat: add OpenTelemetry trace import
fix: preserve tool ordering when replaying nested calls
docs: clarify strict replay semantics
```

## Reporting bugs

Open an issue using the bug report template. A minimal reproducing agent and the
golden trace (with any secrets removed) make fixes dramatically faster.

## Proposing features

Open a feature request first for anything larger than a small fix, so design can be
agreed before you invest time in an implementation.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
