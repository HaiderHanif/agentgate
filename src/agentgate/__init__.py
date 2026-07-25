"""agentgate - regression gating for AI agents.

Record what your agent did once, replay it deterministically forever, and fail
the build when its behaviour changes.

    from agentgate import record_run, replay_run, Policy

    golden = record_run("refund_flow", agent, model_fn, tools, trace_dir="traces")
    observed = replay_run(golden, agent)
    violations = Policy(max_cost_usd=0.05).evaluate(golden, observed)
"""

from __future__ import annotations

from agentgate.assertions import (
    Policy,
    Severity,
    Violation,
    check_cost_ceiling,
    check_forbidden_tools,
    check_latency_budget,
    check_no_tool_errors,
    check_output_similarity,
    check_required_tools,
    check_step_count,
    check_tool_arguments,
    check_tool_sequence,
    has_errors,
)
from agentgate.config import Config, load_config
from agentgate.exceptions import (
    AgentGateError,
    ConfigError,
    ReplayError,
    ResolutionError,
    TraceFormatError,
)
from agentgate.pricing import estimate_cost, register_model
from agentgate.recorder import LiveContext, Recorder, record, record_run
from agentgate.redaction import redact_trace
from agentgate.replay import ReplayContext, replay_run
from agentgate.reporting import (
    github_annotations,
    render_json,
    render_markdown,
    render_report,
    render_text,
)
from agentgate.trace import (
    SCHEMA_VERSION,
    ModelCall,
    ModelResult,
    Step,
    ToolCall,
    Trace,
    digest,
    load_trace,
    save_trace,
)

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "AgentGateError",
    "Config",
    "ConfigError",
    "LiveContext",
    "ModelCall",
    "ModelResult",
    "Policy",
    "Recorder",
    "ReplayContext",
    "ReplayError",
    "ResolutionError",
    "Severity",
    "Step",
    "ToolCall",
    "Trace",
    "TraceFormatError",
    "Violation",
    "__version__",
    "check_cost_ceiling",
    "check_forbidden_tools",
    "check_latency_budget",
    "check_no_tool_errors",
    "check_output_similarity",
    "check_required_tools",
    "check_step_count",
    "check_tool_arguments",
    "check_tool_sequence",
    "digest",
    "estimate_cost",
    "github_annotations",
    "has_errors",
    "load_config",
    "load_trace",
    "record",
    "record_run",
    "redact_trace",
    "register_model",
    "render_json",
    "render_markdown",
    "render_report",
    "render_text",
    "replay_run",
    "save_trace",
]
