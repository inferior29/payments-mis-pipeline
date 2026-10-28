from types import SimpleNamespace

import pytest

from mis.commentary import (ClaudeCommentary, CommentaryMismatch, TemplateCommentary, allowed_numbers, approve,
                            numbers_in)
from mis.kpis import build_context
from conftest import make_con


@pytest.fixture
def ctx(big_df):
    return build_context(make_con(big_df))


def test_template_commentary_passes_the_gate(ctx):
    c = approve(TemplateCommentary().write(ctx), ctx)
    assert ctx["months"][-1]["gmv"] in c["headline"]


def test_number_extraction_ignores_years_ids_and_trailing_commas():
    assert numbers_in("In Sep 2026, GMV was ₹11.09 Cr across 52,369 transactions for M0001.") == {11.09, 52369.0}
    assert numbers_in("Success was 96.7% in Aug 2026.") == {96.7}


@pytest.mark.parametrize("bad_sentence", [
    "GMV was ₹99.99 Cr.",                      # wrong figure
    "GMV was ₹11.1 Cr.",                       # re-rounded: 11.1 is not the displayed 11.09
    "Success rate improved by 7 points.",      # invented number
    "There were 53,000 transactions.",         # plausible but not the real count
])
def test_gate_blocks_any_figure_not_in_the_kpis(ctx, bad_sentence):
    c = TemplateCommentary().write(ctx)
    c["bullets"].append(bad_sentence)
    with pytest.raises(CommentaryMismatch):
        approve(c, ctx)


def test_gate_rejects_malformed_commentary(ctx):
    with pytest.raises(CommentaryMismatch):
        approve({"headline": "x", "bullets": "not a list"}, ctx)


def test_allowed_numbers_come_only_from_the_context(ctx):
    assert 11.09 not in allowed_numbers({"months": []})
    assert any(abs(x - float(ctx["months"][-1]["gmv"].replace("₹", "").replace(" Cr", "").replace(",", ""))) < 1e-9
               for x in allowed_numbers(ctx))


class FakeClient:
    def __init__(self, data):
        self.calls = []
        self._data = data
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="write_commentary", input=self._data)])


def test_claude_commentary_is_forced_structured_and_gated(ctx):
    cur = ctx["months"][-1]
    good = {"headline": f"{cur['month']} GMV was {cur['gmv']}.", "bullets": [f"Success rate was {cur['success_rate']}.", "Refunds were stable.", "Mix was steady."]}
    client = FakeClient(good)
    out = approve(ClaudeCommentary(client=client, model="m").write(ctx), ctx)
    assert out["headline"] == good["headline"]
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "write_commentary"}
    assert "gmv" in call["messages"][0]["content"]

    bad = dict(good, bullets=good["bullets"] + ["Transactions grew 12.3% in the quarter."])
    with pytest.raises(CommentaryMismatch):
        approve(ClaudeCommentary(client=FakeClient(bad), model="m").write(ctx), ctx)
