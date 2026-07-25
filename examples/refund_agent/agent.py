"""A worked example: a refund agent whose step order matters.

The correct sequence is lookup -> refund -> notify. Emailing the customer before
the refund is actually issued is the classic silent regression this catches.
"""

from __future__ import annotations

from typing import Any

ORDER_ID = "A-1042"
CUSTOMER_EMAIL = "customer@example.com"


def refund_agent(ctx: Any) -> str:
    """The correct implementation."""
    ctx.model(f"Customer wants a refund for order {ORDER_ID}. Plan the steps.")
    order = ctx.tool("lookup_order", order_id=ORDER_ID)
    ctx.tool("issue_refund", order_id=ORDER_ID, amount=order["amount"])
    ctx.tool("send_email", to=CUSTOMER_EMAIL, template="refund_confirmed")
    return (
        f"Refund of ${order['amount']:.2f} issued for order {ORDER_ID}. "
        f"Confirmation emailed to {CUSTOMER_EMAIL}."
    )


def regressed_refund_agent(ctx: Any) -> str:
    """The same agent after a bad change: it notifies before it refunds."""
    ctx.model(f"Customer wants a refund for order {ORDER_ID}. Plan the steps.")
    order = ctx.tool("lookup_order", order_id=ORDER_ID)
    ctx.tool("send_email", to=CUSTOMER_EMAIL, template="refund_confirmed")
    ctx.tool("issue_refund", order_id=ORDER_ID, amount=order["amount"])
    return (
        f"Refund of ${order['amount']:.2f} issued for order {ORDER_ID}. "
        f"Confirmation emailed to {CUSTOMER_EMAIL}."
    )


# --- the real implementations, used only when recording a fresh trace ---


def model_fn(prompt: str) -> str:  # pragma: no cover - illustrative
    """Stand-in for a real provider call."""
    return "Look up the order, issue the refund, then notify the customer."


TOOLS = {
    "lookup_order": lambda order_id: {
        "id": order_id,
        "amount": 49.0,
        "status": "delivered",
    },
    "issue_refund": lambda order_id, amount: {
        "refund_id": "RF-771",
        "refunded": amount,
    },
    "send_email": lambda to, template: {"sent": True, "to": to, "template": template},
}


if __name__ == "__main__":  # pragma: no cover
    from agentgate import record_run

    trace = record_run(
        "refund_flow",
        refund_agent,
        model_fn,
        TOOLS,
        trace_dir="examples/refund_agent/traces",
    )
    print(f"recorded {len(trace.tool_calls)} tool calls -> {trace.tool_sequence}")
