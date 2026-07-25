"""OpenAI chat-completions adapter.

    from openai import OpenAI
    from agentgate.adapters import openai_model_fn

    model_fn = openai_model_fn(OpenAI(), model="gpt-4o-mini")
    trace = record_run("refund_flow", agent, model_fn, tools)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentgate.pricing import estimate_cost
from agentgate.trace import ModelResult


def openai_model_fn(
    client: Any,
    *,
    model: str = "gpt-4o-mini",
    system: str | None = None,
    **kwargs: Any,
) -> Callable[[str], ModelResult]:
    """Build a model function backed by an OpenAI client.

    `client` is duck-typed rather than imported, so the openai package is never
    a hard dependency and the adapter is trivial to fake in tests.
    """

    def call(prompt: str) -> ModelResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(model=model, messages=messages, **kwargs)
        text = response.choices[0].message.content or ""

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        return ModelResult(
            text=text,
            model=getattr(response, "model", model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(model, input_tokens, output_tokens),
        )

    return call
