"""Executive commentary plus the gate that blocks the report if any figure is not in the KPI table.

Two writers share one interface: a deterministic template (offline) and Claude (structured JSON).
Whatever writes the commentary, `approve()` checks every number in it against the numbers that were
computed from the data. A number that is not in the KPI context blocks publication.

What the gate catches: wrong, invented or re-rounded figures. What it does not catch: a correct figure
used in a misleading sentence (for example calling a decline "growth"). Keep a human read before sending.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

# A number not glued to letters/digits (so ids like M0001 are ignored); years are excluded separately.
NUMBER = re.compile(r"(?<![A-Za-z0-9])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")  # 52,369 / 11.09 / 2026 (a trailing comma is not part of the number)
YEAR = re.compile(r"^20\d\d$")


class CommentaryMismatch(Exception):
    """Raised when commentary contains a figure that is not in the computed KPIs."""


def numbers_in(text: str) -> set[float]:
    found = set()
    for token in NUMBER.findall(text):
        if YEAR.match(token):
            continue
        found.add(round(float(token.replace(",", "")), 2))
    return found


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def allowed_numbers(context: dict) -> set[float]:
    out: set[float] = set()
    for s in _strings(context):
        out |= numbers_in(s)
    return out


def to_text(c: dict) -> str:
    return c["headline"] + "\n" + "\n".join(c["bullets"])


def approve(commentary: dict, context: dict) -> dict:
    """Return the commentary unchanged if every figure checks out, otherwise raise CommentaryMismatch."""
    if not isinstance(commentary.get("headline"), str) or not isinstance(commentary.get("bullets"), list) \
            or not all(isinstance(b, str) for b in commentary["bullets"]):
        raise CommentaryMismatch("commentary is not in the expected {headline, bullets[]} shape")
    unknown = sorted(numbers_in(to_text(commentary)) - allowed_numbers(context))
    if unknown:
        raise CommentaryMismatch(f"figures not found in the KPI table: {unknown}")
    return commentary


class TemplateCommentary:
    """Deterministic, offline. Every figure is copied from the context."""

    name = "template"

    def write(self, ctx: dict) -> dict:
        cur, prev = ctx["months"][-1], ctx["months"][-2]
        methods, merchants = ctx["payment_methods_latest_month"], ctx["top_merchants_latest_month"]
        bullets = [
            f"Success rate was {cur['success_rate']} in {cur['month']}, against {prev['success_rate']} in {prev['month']}.",
            f"Refunds were {cur['refund_rate']} of GMV in {cur['month']} ({prev['refund_rate']} in {prev['month']}).",
            f"{methods[0]['method']} was the largest payment method at {methods[0]['gmv_share']} of GMV, "
            f"followed by {methods[1]['method']} at {methods[1]['gmv_share']}.",
            f"The largest merchant ({merchants[0]['merchant']}) accounted for {merchants[0]['gmv_share']} of GMV.",
        ]
        return {"headline": f"{cur['month']} GMV was {cur['gmv']} ({cur['gmv_mom_growth']} month on month) "
                            f"across {cur['transactions']} transactions.", "bullets": bullets}


SYSTEM_PROMPT = (
    "You write the executive commentary for a monthly payments MIS report. Use ONLY figures that appear in the "
    "data provided, copied exactly as displayed (keep units such as Cr and %). Do not compute new numbers, do not "
    "round differently and do not use any other numerals; write counts such as 'three' in words. Refer to months by the "
    "name and year shown. Describe what the numbers show; do not speculate about causes. "
    "Return one headline sentence and three to five bullet sentences by calling the write_commentary tool."
)

COMMENTARY_TOOL = {
    "name": "write_commentary",
    "description": "Submit the executive commentary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        },
        "required": ["headline", "bullets"],
    },
}


class ClaudeCommentary:
    """Claude writes the commentary from computed KPIs. Needs ANTHROPIC_API_KEY in the environment."""

    name = "claude"

    def __init__(self, client: Any = None, model: str | None = None):
        if client is None:
            import anthropic

            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("Set ANTHROPIC_API_KEY to use the Claude commentary backend.")
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("MIS_MODEL", "claude-sonnet-5-5")

    def write(self, ctx: dict) -> dict:
        response = self.client.messages.create(
            model=self.model, max_tokens=700, system=SYSTEM_PROMPT, tools=[COMMENTARY_TOOL],
            tool_choice={"type": "tool", "name": "write_commentary"},
            messages=[{"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}],
        )
        for block in response.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "write_commentary":
                return {"headline": block.input.get("headline"), "bullets": block.input.get("bullets")}
        raise CommentaryMismatch("Claude did not return the write_commentary tool call")


def pick_backend(choice: str):
    """'auto' uses Claude when a key is configured, otherwise the template."""
    if choice == "claude" or (choice == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        return ClaudeCommentary()
    return TemplateCommentary()
