"""Anthropic messages adapter.

    import anthropic
    from agentgate.adapters import anthropic_model_fn

    model_fn = anthropic_model_fn(anthropic.Anthropic(), model="claude-sonnet-4")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentgate.pricing import estimate_cost
from agentgate.trace import ModelResult


def anthropic_model_fn(
    client: Any,
    *,
    model: str = "claude-sonnet-4",
    max_tokens: int = 1024,
    system: str | None = None,
    **kwargs: Any,
) -> Callable[[str], ModelResult]:
    """Build a model function backed by an Anthropic client."""

    def call(prompt: str) -> ModelResult:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }
        if system:
            payload["system"] = system

        response = client.messages.create(**payload)
        blocks = getattr(response, "content", []) or []
        text = "".join(getattr(block, "text", "") for block in blocks)

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        return ModelResult(
            text=text,
            model=getattr(response, "model", model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(model, input_tokens, output_tokens),
        )

    return call
