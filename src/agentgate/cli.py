"""Command line interface."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from agentgate import __version__
from agentgate.assertions import Policy
from agentgate.diff import render_report
from agentgate.replay import replay_run
from agentgate.trace import load_trace

app = typer.Typer(
    add_completion=False,
    help="Regression gating for AI agents: record, replay, verify.",
)
console = Console()


def _resolve(target: str) -> Any:
    """Resolve a 'module:attribute' string to a Python object."""
    if ":" not in target:
        raise typer.BadParameter("expected format module.path:callable")
    module_name, attribute = target.split(":", 1)
    sys.path.insert(0, str(Path.cwd()))
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"agentgate {__version__}")


@app.command(name="list")
def list_traces(trace_dir: Path = typer.Option(Path("traces"), "--dir", "-d")) -> None:
    """List golden traces in a directory."""
    if not trace_dir.exists():
        console.print(f"[yellow]no trace directory at {trace_dir}[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"golden traces in {trace_dir}")
    table.add_column("name")
    table.add_column("tools", justify="right")
    table.add_column("model calls", justify="right")
    table.add_column("cost", justify="right")
    table.add_column("recorded")

    for path in sorted(trace_dir.glob("*.json")):
        trace = load_trace(path)
        table.add_row(
            trace.name,
            str(len(trace.tool_calls)),
            str(len(trace.model_calls)),
            f"${trace.total_cost_usd:.4f}",
            trace.created_at.strftime("%Y-%m-%d"),
        )
    console.print(table)


@app.command()
def show(trace_path: Path) -> None:
    """Print the decision path recorded in a trace."""
    trace = load_trace(trace_path)
    console.print(f"[bold]{trace.name}[/bold]  agent={trace.agent}")
    for step in trace.steps:
        if step.kind == "tool":
            console.print(f"  {step.index:>2}. tool   {step.name}({step.arguments})")
        else:
            console.print(f"  {step.index:>2}. model  {step.model}  -> {step.response_text[:60]!r}")
    console.print(f"\nfinal output: {trace.final_output[:200]!r}")


@app.command()
def verify(
    agent: str = typer.Argument(..., help="agent entrypoint as module:callable"),
    trace_path: Path = typer.Argument(..., help="path to the golden trace"),
    max_cost: float = typer.Option(None, "--max-cost", help="cost ceiling in USD"),
    max_latency: float = typer.Option(None, "--max-latency", help="latency budget in ms"),
    similarity: float = typer.Option(0.85, "--similarity", help="output similarity threshold"),
) -> None:
    """Replay an agent against a golden trace and exit non-zero on regressions."""
    golden = load_trace(trace_path)
    agent_fn = _resolve(agent)
    observed = replay_run(golden, agent_fn)
    policy = Policy(
        max_cost_usd=max_cost,
        max_latency_ms=max_latency,
        output_similarity=similarity,
    )
    violations = policy.evaluate(golden, observed)
    console.print(render_report(golden, observed, violations))
    raise typer.Exit(code=1 if violations else 0)


if __name__ == "__main__":  # pragma: no cover
    app()
