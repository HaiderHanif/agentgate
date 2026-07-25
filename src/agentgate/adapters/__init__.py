"""Adapters that turn provider SDK clients into agentgate model functions.

A model function is any callable taking a prompt and returning a string or a
:class:`~agentgate.trace.ModelResult`. Adapters exist only to capture token
counts and pricing, which is what makes cost assertions meaningful. They are
not required - a plain function works fine.

Provider SDKs are imported lazily, so agentgate never depends on them.
"""

from __future__ import annotations

from agentgate.adapters.anthropic import anthropic_model_fn
from agentgate.adapters.openai import openai_model_fn

__all__ = ["anthropic_model_fn", "openai_model_fn"]
