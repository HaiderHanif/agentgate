"""pytest integration.

Golden-trace tests read like ordinary tests:

    def test_refund_flow(agentgate):
        agentgate.assert_matches(handle_refund, "refund_flow")

Re-record after an intended behaviour change:

    pytest --agentgate-update
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from agentgate.assertions import Policy, has_errors
from agentgate.config import Config, load_config
from agentgate.exceptions import AgentGateError
from agentgate.recorder import ModelFn, ToolRegistry, record_run
from agentgate.replay import replay_run
from agentgate.reporting import render_text
from agentgate.trace import Trace, load_trace


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("agentgate")
    group.addoption(
        "--agentgate-update",
        action="store_true",
        default=False,
        help="Re-record golden traces instead of asserting against them.",
    )
    group.addoption(
        "--agentgate-dir",
        action="store",
        default=None,
        help="Directory holding golden traces. Overrides [tool.agentgate] trace_dir.",
    )
    group.addoption(
        "--agentgate-allow-missing",
        action="store_true",
        default=False,
        help=(
            "Skip instead of failing when a golden trace has not been recorded. "
            "Intended for first adoption only - it disables the gate."
        ),
    )
    parser.addini("agentgate_trace_dir", "Directory holding golden traces.", default="")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "golden(name): mark a test as gating on the named golden trace"
    )


@dataclass
class LiveSpec:
    """Everything needed to re-record a trace under `--agentgate-update`."""

    model_fn: ModelFn
    tools: ToolRegistry = field(default_factory=dict)


class GoldenTraceMismatch(AssertionError):
    """Raised when replayed behaviour violates the policy."""


class MissingGoldenTrace(AssertionError):
    """Raised when the golden trace a test gates on does not exist."""


@dataclass
class GoldenRunner:
    """The `agentgate` fixture."""

    trace_dir: Path
    update: bool
    config: Config
    allow_missing: bool = False

    def path_for(self, name: str) -> Path:
        return self.trace_dir / f"{name}.json"

    def load(self, name: str) -> Trace:
        """Load a golden trace, failing if it has not been recorded.

        This used to skip. Skipping was the wrong default by a wide margin: a
        deleted trace, a bad path, or a trace that never got committed would
        remove the gate entirely and still report a green build. A gate that
        vanishes silently is worse than no gate, because the team believes it is
        still there.

        `--agentgate-allow-missing` restores the old behaviour for teams
        adopting agentgate incrementally, where it is a deliberate choice rather
        than an accident.
        """
        path = self.path_for(name)
        if path.is_file():
            return load_trace(path)

        message = (
            f"no golden trace at {path}. Record one with `agentgate record`, or run "
            f"`pytest --agentgate-update`. If this scenario is not recorded yet and "
            f"you want the suite to pass anyway, pass --agentgate-allow-missing."
        )
        if self.allow_missing:
            pytest.skip(message)
        raise MissingGoldenTrace(message)

    def record(self, name: str, agent: Callable[[Any], str], live: LiveSpec) -> Trace:
        """Capture a fresh golden trace and write it to disk."""
        return record_run(
            name,
            agent,
            live.model_fn,
            live.tools,
            trace_dir=self.trace_dir,
            redact=self.config.redact_keys,
        )

    def assert_matches(
        self,
        agent: Callable[[Any], str],
        name: str,
        policy: Policy | None = None,
        *,
        live: LiveSpec | None = None,
        strict: bool | None = None,
    ) -> Trace:
        """Replay `agent` against the named golden trace and enforce `policy`.

        Under `--agentgate-update` the trace is re-recorded instead, which
        requires a `live` spec since recording needs real model and tool access.
        """
        if self.update:
            if live is None:
                pytest.skip(
                    f"--agentgate-update was passed but no LiveSpec was supplied for {name!r}; "
                    f"pass live=LiveSpec(model_fn, tools) to re-record."
                )
            return self.record(name, agent, live)

        golden = self.load(name)
        effective_policy = policy or self.config.policy
        use_strict = self.config.strict if strict is None else strict

        try:
            observed = replay_run(golden, agent, strict=use_strict)
        except AgentGateError as exc:
            raise GoldenTraceMismatch(
                f"replay of {name!r} diverged from the golden trace:\n{exc}"
            ) from exc

        violations = effective_policy.evaluate(golden, observed)
        if has_errors(violations):
            raise GoldenTraceMismatch("\n" + render_text(golden, observed, violations))
        return observed


@pytest.fixture
def agentgate(request: pytest.FixtureRequest) -> GoldenRunner:
    """Golden-trace runner scoped to the current project configuration."""
    config = load_config(Path(str(request.config.rootpath)))

    override = request.config.getoption("--agentgate-dir")
    ini_value = str(request.config.getini("agentgate_trace_dir") or "")
    raw_dir = override or ini_value or config.trace_dir

    trace_dir = Path(raw_dir)
    if not trace_dir.is_absolute():
        trace_dir = Path(str(request.config.rootpath)) / trace_dir

    return GoldenRunner(
        trace_dir=trace_dir,
        update=bool(request.config.getoption("--agentgate-update")),
        config=config,
        allow_missing=bool(request.config.getoption("--agentgate-allow-missing")),
    )
