"""Optional MCP server so coding agents can run evals themselves.

Install the extra first:  pip install "agentgate[mcp]"
Then point Claude Code / Cursor / Codex at:  python -m agentgate.mcp_server
"""

from __future__ import annotations

from pathlib import Path

from agentgate.trace import load_trace

try:  # pragma: no cover - optional dependency
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        'the MCP extra is not installed - run: pip install "agentgate[mcp]"'
    ) from exc

mcp = FastMCP("agentgate")


@mcp.tool()
def list_traces(trace_dir: str = "traces") -> list[dict[str, object]]:
    """List golden traces with their recorded tool paths."""
    directory = Path(trace_dir)
    if not directory.exists():
        return []
    summaries: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        trace = load_trace(path)
        summaries.append(
            {
                "name": trace.name,
                "path": str(path),
                "tool_sequence": trace.tool_sequence,
                "cost_usd": trace.total_cost_usd,
            }
        )
    return summaries


@mcp.tool()
def show_trace(trace_path: str) -> dict[str, object]:
    """Return the full decision path of one golden trace."""
    trace = load_trace(trace_path)
    return {
        "name": trace.name,
        "agent": trace.agent,
        "tool_sequence": trace.tool_sequence,
        "final_output": trace.final_output,
        "cost_usd": trace.total_cost_usd,
        "steps": [step.model_dump() for step in trace.steps],
    }


if __name__ == "__main__":  # pragma: no cover
    mcp.run()
