"""pytest integration.

    def test_refund_flow(agentgate):
        agentgate.assert_matches(refund_agent, "refund_flow")

Run with --agentgate-update to re-record golden traces after an intended change.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentgate.assertions import Policy
from agentgate.diff import render_report
from agentgate.recorder import LiveContext, record_run
from agentgate.replay import ReplayContext, replay_run
from agentgate.trace import Trace, load_trace, save_trace


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("agentgate")
    group.addoption(
        "--agentgate-update",
        action="store_true",
        default=False,
        help="re-record golden traces instead of asserting against them",
    )
    group.addoption(
        "--agentgate-dir",
        action="store",
        default="traces",
        help="directory holding golden trace files (default: traces)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "golden(name): bind a test to a golden trace")


class GoldenRunner:
    """Test-facing helper exposed as the `agentgate` fixture."""

    def __init__(self, trace_dir: Path, update: bool) -> None:
        self.trace_dir = trace_dir
        self.update = update

    def path_for(self, name: str) -> Path:
        return self.trace_dir / f"{name}.json"

    def load(self, name: str) -> Trace:
        path = self.path_for(name)
        if not path.exists():
            pytest.fail(
                f"golden trace {path} not found - record it first "
                "(agentgate record, or pytest --agentgate-update)"
            )
        return load_trace(path)

    def rerecord(
        self,
        name: str,
        agent: Callable[[LiveContext], str],
        model_fn: Callable[[str], str],
        tools: dict[str, Callable[..., Any]],
    ) -> Trace:
        trace = record_run(name, agent, model_fn, tools)
        save_trace(trace, self.path_for(name))
        return trace

    def assert_matches(
        self,
        agent: Callable[[ReplayContext], str],
        name: str,
        policy: Policy | None = None,
        *,
        strict: bool = True,
    ) -> Trace:
        """Replay `agent` against golden trace `name` and assert no regressions."""
        golden = self.load(name)
        observed = replay_run(golden, agent, strict=strict)
        violations = (policy or Policy()).evaluate(golden, observed)
        if violations:
            pytest.fail(render_report(golden, observed, violations), pytrace=False)
        return observed


@pytest.fixture
def agentgate(request: pytest.FixtureRequest) -> GoldenRunner:
    """Golden-trace runner bound to the current pytest invocation."""
    trace_dir = Path(request.config.getoption("--agentgate-dir"))
    update = bool(request.config.getoption("--agentgate-update"))
    return GoldenRunner(trace_dir, update)
