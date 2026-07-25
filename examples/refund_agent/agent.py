"""A refund agent, and the one-line change that quietly breaks it.

The agent must issue the refund *before* telling the customer it happened. Swap
those two lines and every unit test still passes, the output still reads
correctly, and customers start being promised money that was never sent.

That is the class of bug agentgate exists to catch.

Run the gate:

    pytest examples/refund_agent
"""

from __future__ import annotations

from typing import Any

from agentgate.pytest_plugin import LiveSpec
from agentgate.trace import ModelResult

ORDER = {
    "id": "A-1042",
    "amount": 49.99,
    "email": "customer@example.com",
    "status": "delivered",
}

DECISION = "Yes - the order qualifies for a full refund under the 30-day policy."


# --------------------------------------------------------------------------- #
# Tools. In a real system these hit your database and payment provider.
# --------------------------------------------------------------------------- #


def lookup_order(order_id: str) -> dict[str, Any]:
    return {**ORDER, "id": order_id}


def issue_refund(order_id: str, amount: float) -> dict[str, Any]:
    return {"refund_id": "RF-77120", "order_id": order_id, "amount": amount}


def send_email(to: str) -> dict[str, Any]:
    return {"delivered": True, "to": to}


TOOLS = {
    "lookup_order": lookup_order,
    "issue_refund": issue_refund,
    "send_email": send_email,
}


def model_fn(prompt: str) -> ModelResult:
    """Stand-in for a real provider call, so the example runs offline.

    Replace with `openai_model_fn(OpenAI())` to record against a live model.
    """
    return ModelResult(
        text=DECISION,
        model="gpt-4o-mini",
        input_tokens=412,
        output_tokens=38,
    )


LIVE = LiveSpec(model_fn=model_fn, tools=TOOLS)


# --------------------------------------------------------------------------- #
# The agent.
# --------------------------------------------------------------------------- #


def handle_refund(ctx: Any) -> str:
    """Correct: money moves first, then the customer is notified."""
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model(f"Should we refund order {order['id']} for ${order['amount']}?")

    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])
    ctx.tool("send_email", to=order["email"])

    return f"Refunded ${order['amount']} for order {order['id']}. {decision}"


def handle_refund_regressed(ctx: Any) -> str:
    """Broken: the email goes out before the refund is issued.

    Identical output. Identical cost. Identical everything a normal test checks.
    """
    order = ctx.tool("lookup_order", order_id="A-1042")
    decision = ctx.model(f"Should we refund order {order['id']} for ${order['amount']}?")

    ctx.tool("send_email", to=order["email"])
    ctx.tool("issue_refund", order_id=order["id"], amount=order["amount"])

    return f"Refunded ${order['amount']} for order {order['id']}. {decision}"
