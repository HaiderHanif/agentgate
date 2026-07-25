"""MCP server, so coding agents can inspect and run your evals directly.

    pip install "agentgate[mcp]"
    python -m agentgate.mcp_server

Register it with Claude Code, Cursor, or any MCP client and the assistant can
read golden traces and verify agents without leaving the editor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentgate.assertions import has_errors
from agentgate.config import load_config
from agentgate.exceptions import AgentGateError
from agentgate.replay import replay_run
from agentgate.reporting import render_text
from agentgate.resolve import resolve_callable
from agentgate.trace import load_trace

try:  # pragma: no cover - optional dependency
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "the MCP server needs the 'mcp' extra: pip install \"agentgate[mcp]\""
    ) from exc

mcp = FastMCP("agentgate")


@mcp.tool()
def list_traces(directory: str = "") -> list[dict[str, Any]]:
    """List golden traces in the project, with their tool paths and costs."""
    target = Path(directory) if directory else load_config().trace_dir
    if not target.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.json")):
        try:
            summary = load_trace(path).summary()
        except AgentGateError as exc:
            summaries.append({"path": str(path), "error": str(exc)})
            continue
        summary["path"] = str(path)
        summaries.append(summary)
    return summaries


@mcp.tool()
def show_trace(path: str) -> dict[str, Any]:
    """Return the full contents of one golden trace."""
    try:
        return load_trace(path).model_dump(mode="json")
    except AgentGateError as exc:
        return {"error": str(exc)}


@mcp.tool()
def verify_agent(agent: str, trace_path: str, strict: bool = True) -> dict[str, Any]:
    """Replay an agent against a golden trace and report any behavioural regressions.

    `agent` is a 'module:attribute' entrypoint, for example 'app.agent:handle_refund'.
    Replay makes no network calls and causes no side effects.
    """
    config = load_config()
    try:
        agent_fn = resolve_callable(agent)
        golden = load_trace(trace_path)
        observed = replay_run(golden, agent_fn, strict=strict)
    except AgentGateError as exc:
        return {"passed": False, "error": str(exc)}

    violations = config.policy.evaluate(golden, observed)
    return {
        "passed": not has_errors(violations),
        "violations": [v.model_dump() for v in violations],
        "report": render_text(golden, observed, violations),
        "golden": golden.summary(),
        "observed": observed.summary(),
    }


def main() -> None:  # pragma: no cover - process entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
