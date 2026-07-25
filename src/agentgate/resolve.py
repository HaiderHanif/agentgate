"""Resolving `module:attribute` entrypoint strings.

Used by the CLI and the GitHub Action so agents, model functions, and tool
registries can be named on the command line.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from agentgate.exceptions import ResolutionError


def ensure_cwd_importable() -> None:
    """Put the working directory on sys.path so local modules resolve."""
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


def resolve(target: str) -> Any:
    """Import and return the object named by `"package.module:attribute"`."""
    if ":" not in target:
        raise ResolutionError(
            f"{target!r} is not a valid entrypoint; expected 'module:attribute', "
            f"for example 'myapp.agent:handle_refund'"
        )
    module_name, _, attribute = target.partition(":")
    ensure_cwd_importable()

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ResolutionError(f"could not import module {module_name!r}: {exc}") from exc

    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ResolutionError(
            f"module {module_name!r} has no attribute {attribute!r}"
        ) from exc


def resolve_callable(target: str) -> Any:
    """Resolve an entrypoint and verify it is callable."""
    obj = resolve(target)
    if not callable(obj):
        raise ResolutionError(f"{target!r} resolved to {type(obj).__name__}, which is not callable")
    return obj


def resolve_tools(target: str) -> dict[str, Any]:
    """Resolve an entrypoint and verify it is a tool registry."""
    obj = resolve(target)
    if not isinstance(obj, dict):
        raise ResolutionError(
            f"{target!r} resolved to {type(obj).__name__}; expected a dict of "
            f"{{tool_name: callable}}"
        )
    return obj
