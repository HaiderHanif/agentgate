"""Exception hierarchy.

Every error raised by agentgate derives from :class:`AgentGateError`, so callers
can catch the whole surface with one clause without swallowing unrelated bugs.
"""

from __future__ import annotations


class AgentGateError(Exception):
    """Base class for all agentgate errors."""


class TraceFormatError(AgentGateError):
    """A trace file is malformed, truncated, or of an unsupported schema version."""


class ReplayError(AgentGateError):
    """The agent asked for something the golden trace cannot serve.

    This is not a crash - it is the primary signal that agent behaviour changed.
    """


class ConfigError(AgentGateError):
    """Configuration in pyproject.toml is invalid."""


class ResolutionError(AgentGateError):
    """A 'module:attribute' entrypoint could not be imported or resolved."""
