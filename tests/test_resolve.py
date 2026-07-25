from __future__ import annotations

import pytest

from agentgate.exceptions import ResolutionError
from agentgate.resolve import resolve, resolve_callable, resolve_tools


def test_resolves_an_attribute() -> None:
    assert resolve("agentgate:__version__")


def test_requires_colon_syntax() -> None:
    with pytest.raises(ResolutionError, match="module:attribute"):
        resolve("agentgate.cli")


def test_missing_module() -> None:
    with pytest.raises(ResolutionError, match="could not import"):
        resolve("no_such_module_xyz:thing")


def test_missing_attribute() -> None:
    with pytest.raises(ResolutionError, match="no attribute"):
        resolve("agentgate:not_a_real_attribute")


def test_callable_check() -> None:
    assert callable(resolve_callable("agentgate:record_run"))
    with pytest.raises(ResolutionError, match="not callable"):
        resolve_callable("agentgate:__version__")


def test_tools_must_be_a_dict() -> None:
    with pytest.raises(ResolutionError, match="expected a dict"):
        resolve_tools("agentgate:__version__")
