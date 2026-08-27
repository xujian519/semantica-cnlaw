"""Tests for the decision -> statute based_on citation planner."""

from cnlaw.ingest.decision_citations import (
    build_decision_citation_plan,
    extract_statute_refs,
)
from cnlaw.ingest.parse_decision import PatentDecision

_ARTICLES = [
    {
        "full_name": "中华人民共和国专利法",
        "source_date": "2020-10-17",
        "number": "第二十二条",
        "text": "授予专利权…应当具有突出的实质性特点和显著的进步…",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国专利法实施细则",
        "source_date": "2023-12-11",
        "number": "第二十条",
        "text": "权利要求书应当说明发明或者实用新型的技术特征…",
        "status": "现行有效",
    },
]


def test_extract_statute_refs_dedup():
    text = "依据专利法第22条第3款和专利法第22条第2款，以及专利法实施细则第20条第1款。"
    refs = extract_statute_refs(text)
    assert ("专利法", 22) in refs
    assert ("专利法实施细则", 20) in refs
    # 第22条第3款 / 第2款 dedup to a single (专利法, 22) ref
    assert refs.count(("专利法", 22)) == 1


def test_build_plan_resolves_statute_and_drops_missing():
    d1 = PatentDecision(decision_id="1", case_number="4W1",
                        legal_basis="专利法第22条第3款、专利法实施细则第20条第1款",
                        full_text="本决定依据专利法第22条作出。")
    d2 = PatentDecision(decision_id="2", case_number="4W2",
                        legal_basis="专利法第26条第4款",  # not in corpus -> dropped
                        full_text="")
    plan = build_decision_citation_plan([d1, d2], _ARTICLES)
    assert ("4W1::1", "中华人民共和国专利法", "2020-10-17", "第二十二条") in plan
    assert ("4W1::1", "中华人民共和国专利法实施细则", "2023-12-11", "第二十条") in plan
    # 4W2::2 references 第26条, which has no Article node here -> dropped
    keys = [e[0] for e in plan]
    assert "4W2::2" not in keys


def test_build_plan_dedupes_repeated_refs():
    d = PatentDecision(decision_id="9", case_number="4W9",
                       legal_basis="专利法第22条第3款",
                       full_text="依据专利法第22条第2款的规定，另见专利法第22条。")
    plan = build_decision_citation_plan([d], _ARTICLES)
    assert len(plan) == 1
    assert plan[0] == ("4W9::9", "中华人民共和国专利法", "2020-10-17", "第二十二条")


def test_build_plan_ignores_unknown_statute():
    d = PatentDecision(decision_id="3", case_number="4W3",
                       legal_basis="商标法第57条", full_text="")
    assert build_decision_citation_plan([d], _ARTICLES) == []
