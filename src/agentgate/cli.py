"""Command line interface.

    agentgate init                       scaffold configuration and a trace dir
    agentgate list                       show golden traces in the project
    agentgate show traces/refund.json    inspect one trace
    agentgate record app:agent ...       capture a new golden trace
    agentgate verify app:agent trace     replay and gate on behaviour
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from agentgate import __version__
from agentgate.assertions import Policy, has_errors
from agentgate.config import PYPROJECT, load_config
from agentgate.exceptions import AgentGateError
from agentgate.recorder import record_run
from agentgate.replay import replay_run
from agentgate.reporting import github_annotations, render_report
from agentgate.resolve import resolve_callable, resolve_tools
from agentgate.trace import load_trace

app = typer.Typer(
    name="agentgate",
    help="Regression gating for AI agents: record, replay, and gate on behaviour.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_USAGE = 2

CONFIG_SNIPPET = """
[tool.agentgate]
trace_dir = "traces"
strict = true

[tool.agentgate.policy]
tool_sequence = true
tool_arguments = true
output_similarity = 0.85
""".lstrip()


def _fail(message: str, code: int = EXIT_USAGE) -> None:
    err_console.print(f"[bold red]error[/bold red] {message}")
    raise typer.Exit(code)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"agentgate {__version__}")


@app.command(name="init")
def init_project(
    trace_dir: Path = typer.Option(Path("traces"), "--dir", help="Directory for golden traces."),
) -> None:
    """Create the trace directory and print the configuration to add."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = trace_dir / ".gitkeep"
    if not any(trace_dir.iterdir()):
        gitkeep.touch()

    console.print(f"[green]created[/green] {trace_dir}/")
    console.print(f"\nAdd this to your {PYPROJECT}:\n")
    console.print(Syntax(CONFIG_SNIPPET, "toml", theme="ansi_dark"))


@app.command(name="list")
def list_traces(
    directory: Optional[Path] = typer.Option(
        None, "--dir", help="Trace directory. Defaults to the configured trace_dir."
    ),
) -> None:
    """List every golden trace in the project."""
    target = directory or load_config().trace_dir
    if not target.is_dir():
        _fail(f"no trace directory at {target}; run 'agentgate init' first")

    paths = sorted(target.glob("*.json"))
    if not paths:
        console.print(f"[yellow]no traces found in {target}[/yellow]")
        raise typer.Exit(EXIT_OK)

    table = Table(title=f"golden traces in {target}", header_style="bold")
    for column in ("name", "agent", "tools", "steps", "cost", "recorded"):
        table.add_column(column)

    for path in paths:
        try:
            trace = load_trace(path)
        except AgentGateError as exc:
            table.add_row(path.stem, f"[red]unreadable[/red] {exc}", "-", "-", "-", "-")
            continue
        table.add_row(
            trace.name,
            trace.agent,
            " -> ".join(trace.tool_sequence) or "-",
            str(len(trace.steps)),
            f"${trace.total_cost_usd:.4f}",
            trace.created_at.strftime("%Y-%m-%d"),
        )
    console.print(table)


@app.command()
def show(
    path: Path = typer.Argument(..., help="Path to a golden trace JSON file."),
) -> None:
    """Print a step-by-step view of one trace."""
    try:
        trace = load_trace(path)
    except AgentGateError as exc:
        _fail(str(exc))
        return

    console.print(f"[bold]{trace.name}[/bold]  agent={trace.agent}  schema={trace.schema_version}")
    console.print(
        f"steps={len(trace.steps)}  tokens={trace.total_tokens}  "
        f"cost=${trace.total_cost_usd:.4f}  latency={trace.total_latency_ms:.1f}ms\n"
    )

    for step in trace.steps:
        if step.kind == "model":
            preview = step.response_text[:80].replace("\n", " ")
            console.print(f"  {step.index:>2}. [cyan]model[/cyan]  {step.model}  {preview!r}")
        else:
            status = f"[red]{step.error}[/red]" if step.error else ""
            console.print(
                f"  {step.index:>2}. [magenta]tool[/magenta]   {step.name}"
                f"({step.arguments}) {status}"
            )

    if trace.final_output:
        console.print(f"\n[bold]final output[/bold]\n{trace.final_output}")


@app.command()
def record(
    agent: str = typer.Argument(..., help="Agent entrypoint, e.g. 'app.agent:handle_refund'."),
    model: str = typer.Option(..., "--model", help="Model function entrypoint."),
    tools: str = typer.Option(..., "--tools", help="Tool registry entrypoint (a dict)."),
    name: str = typer.Option(..., "--name", help="Name for the golden trace."),
    directory: Optional[Path] = typer.Option(None, "--dir", help="Where to write the trace."),
) -> None:
    """Run an agent for real and save the result as a golden trace.

    This makes real model and tool calls, so it costs money and can cause side
    effects. Point it at a sandbox.
    """
    config = load_config()
    target_dir = directory or config.trace_dir

    try:
        agent_fn = resolve_callable(agent)
        model_fn = resolve_callable(model)
        tool_registry = resolve_tools(tools)
    except AgentGateError as exc:
        _fail(str(exc))
        return

    trace = record_run(
        name,
        agent_fn,
        model_fn,
        tool_registry,
        trace_dir=target_dir,
        redact=config.redact_keys,
    )
    path = target_dir / f"{name}.json"
    console.print(f"[green]recorded[/green] {path}")
    console.print(
        f"  {len(trace.tool_calls)} tool calls: {' -> '.join(trace.tool_sequence) or '-'}"
    )
    console.print(f"  cost ${trace.total_cost_usd:.4f}  tokens {trace.total_tokens}")


@app.command()
def verify(
    agent: str = typer.Argument(..., help="Agent entrypoint, e.g. 'app.agent:handle_refund'."),
    trace_path: Path = typer.Argument(..., help="Golden trace to replay against."),
    fmt: str = typer.Option("text", "--format", help="Report format: text, markdown, or json."),
    report: Optional[Path] = typer.Option(None, "--report", help="Also write the report here."),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Match tool arguments exactly."),
    github: bool = typer.Option(False, "--github", help="Emit GitHub Actions annotations."),
    max_cost: Optional[float] = typer.Option(None, "--max-cost", help="Cost ceiling in USD."),
    max_latency: Optional[float] = typer.Option(
        None, "--max-latency", help="Latency budget in milliseconds."
    ),
    similarity: Optional[float] = typer.Option(
        None, "--similarity", help="Minimum final-output similarity, 0 to 1."
    ),
) -> None:
    """Replay an agent against a golden trace and gate on the result.

    Exits 0 when behaviour matches, 1 when it regressed, 2 on a usage error, so
    it drops straight into any CI system.
    """
    config = load_config()

    try:
        agent_fn = resolve_callable(agent)
        golden = load_trace(trace_path)
    except AgentGateError as exc:
        _fail(str(exc))
        return

    policy = config.policy.model_copy(deep=True)
    if max_cost is not None:
        policy.max_cost_usd = max_cost
    if max_latency is not None:
        policy.max_latency_ms = max_latency
    if similarity is not None:
        policy.output_similarity = similarity

    try:
        observed = replay_run(golden, agent_fn, strict=strict)
    except AgentGateError as exc:
        err_console.print(f"[bold red]replay diverged[/bold red]\n{exc}")
        if github:
            print(f"::error::[replay] {exc}")
        raise typer.Exit(EXIT_VIOLATIONS) from exc

    violations = policy.evaluate(golden, observed)

    try:
        rendered = render_report(golden, observed, violations, fmt)
    except ValueError as exc:
        _fail(str(exc))
        return

    sys.stdout.write(rendered)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(rendered, encoding="utf-8")
    if github and violations:
        print(github_annotations(violations, file=str(trace_path)))

    raise typer.Exit(EXIT_VIOLATIONS if has_errors(violations) else EXIT_OK)


def main() -> None:  # pragma: no cover - console script shim
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
