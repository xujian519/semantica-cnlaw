"""Tests for the judgment -> Neo4j plan builder."""

from cnlaw.ingest.load_judgments_neo4j import (
    apply_judgment_plan,
    build_judgment_plan,
    judgment_key,
)
from cnlaw.ingest.parse_judgment import PatentJudgment


def _j(case_number="", jid="", pnums=None, **kw):
    return PatentJudgment(case_number=case_number, judgment_id=jid or case_number,
                          patent_numbers=pnums or [], domain="专利判决", **kw)


def test_judgment_key():
    assert judgment_key("(2012)民提字第1号", "(2012)民提字第1号") == "(2012)民提字第1号"
    # no case number -> fall back to the judgment id
    assert judgment_key("", "some-source-file") == "some-source-file"


def test_build_plan_dedup_and_fill_gaps():
    a = _j("(2012)民提字第1号", invention_name="", court="")
    b = _j("(2012)民提字第1号", invention_name="后换档器支架", court="最高人民法院",
           pnums=["94102612.4"])
    plan = build_judgment_plan([a, b])
    assert len(plan.judgments) == 1
    assert plan.judgments[0]["invention_name"] == "后换档器支架"
    assert plan.judgments[0]["court"] == "最高人民法院"


def test_build_plan_patent_aggregation_and_involves():
    a = _j("(2012)民提字第1号", pnums=["94102612.4"], invention_name="后换档器支架")
    b = _j("(2012)民提字第2号", pnums=["94102612.4", "200480001590.4"])
    plan = build_judgment_plan([a, b])
    # one judgment per case
    assert len(plan.judgments) == 2
    # patent aggregated once per distinct number
    assert {p["patent_number"] for p in plan.patents} == {"94102612.4", "200480001590.4"}
    # involves edges: (cn, jid, patent) tuples
    assert ("(2012)民提字第1号", "(2012)民提字第1号", "94102612.4") in plan.involves
    assert ("(2012)民提字第2号", "(2012)民提字第2号", "94102612.4") in plan.involves
    assert len(plan.involves) == 3
    # the aggregated Patent node keeps the invention name once
    pat = next(p for p in plan.patents if p["patent_number"] == "94102612.4")
    assert pat["invention_name"] == "后换档器支架"


def test_apply_plan_is_noop_on_empty():
    plan = build_judgment_plan([])
    assert plan.judgments == [] and plan.patents == [] and plan.involves == []
