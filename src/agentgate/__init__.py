"""agentgate - regression gating for AI agents.

Record what a working agent did, replay it deterministically, and fail CI when
the agent's *behaviour* changes - not when its wording changes.
"""

from agentgate.assertions import (
    Policy,
    Violation,
    check_cost_ceiling,
    check_forbidden_tools,
    check_latency_budget,
    check_output_similarity,
    check_required_tools,
    check_tool_arguments,
    check_tool_sequence,
)
from agentgate.diff import render_report
from agentgate.recorder import LiveContext, Recorder, record, record_run
from agentgate.replay import ReplayContext, ReplayError, replay_run
from agentgate.trace import ModelCall, ToolCall, Trace, load_trace, save_trace

__version__ = "0.1.0"

__all__ = [
    "LiveContext",
    "ModelCall",
    "Policy",
    "Recorder",
    "ReplayContext",
    "ReplayError",
    "ToolCall",
    "Trace",
    "Violation",
    "__version__",
    "check_cost_ceiling",
    "check_forbidden_tools",
    "check_latency_budget",
    "check_output_similarity",
    "check_required_tools",
    "check_tool_arguments",
    "check_tool_sequence",
    "load_trace",
    "record",
    "record_run",
    "render_report",
    "replay_run",
    "save_trace",
]
