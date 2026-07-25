"""Shared fixtures.

The sample agent here is deliberately small but structurally realistic: it looks
something up, asks a model to decide, then takes an irreversible action.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentgate.recorder import ToolRegistry
from agentgate.trace import ModelResult

pytest_plugins = ["pytester"]

ORDER = {"id": "A-1042", "amount": 49.99, "email": "customer@example.com"}
DECISION = "Yes - the order qualifies for a full refund."


@pytest.fixture
def tools() -> ToolRegistry:
    return {
        "lookup_order": lambda order_id: {**ORDER, "id": order_id},
        "issue_refund": lambda order_id, amount: {"refund_id": "RF-77120", "amount": amount},
        "send_email": lambda to: {"delivered": True, "to": to},
    }


@pytest.fixture
def model_fn() -> Any:
    def call(prompt: str) -> ModelResult:
        return ModelResult(
            text=DECISION,
            model="gpt-4o-mini",
            input_tokens=120,
            output_tokens=20,
        )

    return call


@pytest.fixture
def agent() -> Any:
    """Correct behaviour: refund first, notify afterwards."""

    def handle_refund(ctx: Any) -> str:
        order = ctx.tool("lookup_order", order_id="A-1042")
        decision = ctx.model(f"Refund order {order['id']} for ${order['amount']}?")
        ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
        ctx.tool("send_email", to=order["email"])
        return f"Refunded ${order['amount']} for order {order['id']}. {decision}"

    return handle_refund


@pytest.fixture
def regressed_agent() -> Any:
    """The bug we want caught: the customer is told before the money moves."""

    def handle_refund(ctx: Any) -> str:
        order = ctx.tool("lookup_order", order_id="A-1042")
        decision = ctx.model(f"Refund order {order['id']} for ${order['amount']}?")
        ctx.tool("send_email", to=order["email"])
        ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
        return f"Refunded ${order['amount']} for order {order['id']}. {decision}"

    return handle_refund
