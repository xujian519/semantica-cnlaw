"""Tests for the decision import plan (cnlaw/ingest/load_decisions_neo4j.py)."""

from cnlaw.ingest.load_decisions_neo4j import build_decision_plan
from cnlaw.ingest.parse_decision import PatentDecision


def _doc(**kw):
    base = dict(
        decision_id="1",
        case_number="4W1",
        case_type="无效",
        application_number="00807334.1",
        decision_result="维持专利权有效",
        full_text="决定全文",
        source_path="/abs/file.md",
        source_file="file",
        file_name="file.md",
    )
    base.update(kw)
    return PatentDecision(**{k: v for k, v in base.items()})


def test_dedup_same_case_fills_gaps():
    a = _doc(invention_name="X", patent_holder="A")
    b = _doc(invention_name="", patent_holder="B", decision_points="要点")  # same key, gaps on a
    plan = build_decision_plan([a, b])
    assert len(plan.decisions) == 1
    d = plan.decisions[0]
    assert d["invention_name"] == "X"          # kept from first
    assert d["patent_holder"] == "A"           # not overridden by empty-first sibling
    assert d["decision_points"] == "要点"       # gap filled from sibling
    assert d["decision_id"] == "1"


def test_patent_aggregation_and_involves():
    d1 = _doc(application_number="00807334.1", invention_name="分隔装置", ipc="H02G 3/00",
              patent_holder="威斯克", application_date="2000-06-21", grant_date="2004-01-21")
    d2 = _doc(decision_id="2", case_number="4W2", application_number="00807334.1",
              invention_name="分隔装置", ipc="H02G 3/00", patent_holder="威斯克")
    plan = build_decision_plan([d1, d2])
    assert len(plan.patents) == 1
    p = plan.patents[0]
    assert p["patent_number"] == "00807334.1"
    assert p["invention_name"] == "分隔装置"
    assert len(plan.involves) == 2
    assert ("4W1::1", "00807334.1") in plan.involves
    assert ("4W2::2", "00807334.1") in plan.involves


def test_empty_application_number_no_patent():
    d = _doc(application_number="")
    plan = build_decision_plan([d])
    assert plan.patents == []
    assert plan.involves == []


def test_decision_id_falls_back_to_source_file():
    d = _doc(decision_id="", source_file="WX9999")
    plan = build_decision_plan([d])
    assert plan.decisions[0]["decision_id"] == "WX9999"


def test_patent_kind_by_case_type():
    inv = _doc(case_type="无效")
    reex = _doc(decision_id="2", case_number="1F1", case_type="复审", application_number="200380109882.5")
    plan = build_decision_plan([inv, reex])
    kinds = {p["patent_number"]: p["kind"] for p in plan.patents}
    assert kinds["00807334.1"] == "grant"
    assert kinds["200380109882.5"] == "application"
