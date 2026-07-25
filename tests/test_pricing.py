from __future__ import annotations

import pytest

from agentgate.pricing import estimate_cost, known_models, register_model


def test_known_model_is_priced() -> None:
    # 1M in + 1M out on gpt-4o-mini = $0.15 + $0.60
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)


def test_unknown_model_costs_nothing_rather_than_raising() -> None:
    assert estimate_cost("some-private-finetune", 1000, 1000) == 0.0


def test_models_can_be_registered() -> None:
    register_model("test-model", input_per_mtok=1.0, output_per_mtok=2.0)

    assert "test-model" in known_models()
    assert estimate_cost("test-model", 1_000_000, 500_000) == pytest.approx(2.0)
