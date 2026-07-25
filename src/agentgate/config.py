"""Project configuration, read from `[tool.agentgate]` in pyproject.toml.

Configuration is optional. Defaults are chosen so that a project with no
configuration at all still behaves sensibly.

    [tool.agentgate]
    trace_dir = "traces"
    strict = true
    redact_keys = ["api_key", "customer_email"]

    [tool.agentgate.policy]
    max_cost_usd = 0.05
    forbidden_tools = ["delete_customer"]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agentgate.assertions import Policy
from agentgate.exceptions import ConfigError
from agentgate.redaction import DEFAULT_REDACT_KEYS

if sys.version_info >= (3, 11):  # pragma: no cover - version branch
    import tomllib
else:  # pragma: no cover - version branch
    import tomli as tomllib

PYPROJECT = "pyproject.toml"


class Config(BaseModel):
    """Resolved agentgate configuration for a project."""

    trace_dir: Path = Path("traces")
    strict: bool = True
    redact_keys: list[str] = Field(default_factory=lambda: list(DEFAULT_REDACT_KEYS))
    policy: Policy = Field(default_factory=Policy)

    def trace_path(self, name: str) -> Path:
        """Path of the golden trace named `name`."""
        return self.trace_dir / f"{name}.json"


def find_pyproject(start: Path | None = None) -> Path | None:
    """Walk upwards from `start` looking for a pyproject.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        pyproject = candidate / PYPROJECT
        if pyproject.is_file():
            return pyproject
    return None


def load_config(start: Path | None = None) -> Config:
    """Load configuration, falling back to defaults when none is present."""
    pyproject = find_pyproject(start)
    if pyproject is None:
        return Config()

    try:
        data: dict[str, Any] = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {pyproject}: {exc}") from exc

    section = data.get("tool", {}).get("agentgate")
    if not section:
        return Config()

    try:
        return Config.model_validate(section)
    except ValidationError as exc:
        raise ConfigError(f"invalid [tool.agentgate] configuration in {pyproject}:\n{exc}") from exc
