"""Token pricing so cost regressions can be caught, not guessed.

Prices are USD per million tokens and are intentionally easy to override: model
pricing changes often, and a stale hard-coded table is worse than none.

    from agentgate.pricing import register_model, estimate_cost

    register_model("my-finetune", input_per_mtok=0.30, output_per_mtok=1.20)
    estimate_cost("my-finetune", input_tokens=1000, output_tokens=250)
"""

from __future__ import annotations

from typing import NamedTuple


class ModelPrice(NamedTuple):
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float


_PRICES: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(2.50, 10.00),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
    "gpt-4.1": ModelPrice(2.00, 8.00),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60),
    "o3-mini": ModelPrice(1.10, 4.40),
    "claude-sonnet-4": ModelPrice(3.00, 15.00),
    "claude-haiku-4": ModelPrice(0.80, 4.00),
    "claude-opus-4": ModelPrice(15.00, 75.00),
    "gemini-2.5-pro": ModelPrice(1.25, 10.00),
    "gemini-2.5-flash": ModelPrice(0.30, 2.50),
}


def register_model(name: str, *, input_per_mtok: float, output_per_mtok: float) -> None:
    """Add or override pricing for a model."""
    _PRICES[name] = ModelPrice(input_per_mtok, output_per_mtok)


def known_models() -> list[str]:
    """Every model with registered pricing."""
    return sorted(_PRICES)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of one model call.

    Unknown models cost 0.0 rather than raising: a missing price should never
    break a test run, it should simply not participate in cost assertions.
    """
    price = _PRICES.get(model)
    if price is None:
        return 0.0
    cost = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
    return round(cost, 8)
