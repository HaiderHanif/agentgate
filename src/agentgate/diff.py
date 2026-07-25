"""Deprecated module kept for import stability.

Use :mod:`agentgate.reporting` instead. This shim will be removed in 1.0.
"""

from __future__ import annotations

from agentgate.reporting import render_json, render_markdown, render_report, render_text

__all__ = ["render_json", "render_markdown", "render_report", "render_text"]
