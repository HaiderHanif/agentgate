"""agentgate - regression gating for AI agents.

Record one good run, replay it deterministically, compare the decision path, and
block the merge when behaviour changed and nobody meant it to.

    from agentgate import Policy, record_run, replay_run

    golden = record_run("refund", agent, model_fn, tools)
    observed = replay_run(golden, agent)
    violations = Policy().evaluate(golden, observed)

Start with `docs/quickstart.md`. Read `docs/limitations.md` before trusting it
with anything that matters - what this tool does *not* verify is documented as
carefully as what it does.
"""

from __future__ import annotations

from agentgate.assertions import (
    ArgumentConstraint,
    Ordering,
    OutputPolicy,
    Policy,
    Severity,
    UnorderedGroup,
    Violation,
    check_cost_ceiling,
    check_forbidden_tools,
    check_latency_budget,
    check_no_injected_content,
    check_no_tool_errors,
    check_output_similarity,
    check_required_tools,
    check_step_count,
    check_tool_arguments,
    check_tool_sequence,
    has_errors,
)
from agentgate.config import Config, load_config
from agentgate.determinism import deterministic
from agentgate.exceptions import (
    AgentGateError,
    ConfigError,
    ReplayError,
    ResolutionError,
    TraceFormatError,
)
from agentgate.injection import InjectionFinding, scan_text, scan_trace
from agentgate.integrity import IntegrityError, fingerprint, sign_trace, verify_trace
from agentgate.normalize import Normalizer
from agentgate.pricing import estimate_cost, known_models, register_model
from agentgate.recorder import LiveContext, Recorder, record_run
from agentgate.redaction import redact_trace, redact_value
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
    ToolCall,
    Trace,
    load_trace,
    save_trace,
)

__version__ = "0.2.0"

__all__ = [
    "SCHEMA_VERSION",
    "AgentGateError",
    "ArgumentConstraint",
    "Config",
    "ConfigError",
    "InjectionFinding",
    "IntegrityError",
    "LiveContext",
    "ModelCall",
    "ModelResult",
    "Normalizer",
    "Ordering",
    "OutputPolicy",
    "Policy",
    "Recorder",
    "ReplayContext",
    "ReplayError",
    "ResolutionError",
    "Severity",
    "ToolCall",
    "Trace",
    "TraceFormatError",
    "UnorderedGroup",
    "Violation",
    "__version__",
    "check_cost_ceiling",
    "check_forbidden_tools",
    "check_latency_budget",
    "check_no_injected_content",
    "check_no_tool_errors",
    "check_output_similarity",
    "check_required_tools",
    "check_step_count",
    "check_tool_arguments",
    "check_tool_sequence",
    "deterministic",
    "estimate_cost",
    "fingerprint",
    "github_annotations",
    "has_errors",
    "known_models",
    "load_config",
    "load_trace",
    "record_run",
    "redact_trace",
    "redact_value",
    "register_model",
    "render_json",
    "render_markdown",
    "render_report",
    "render_text",
    "replay_run",
    "save_trace",
    "scan_text",
    "scan_trace",
    "sign_trace",
    "verify_trace",
]
