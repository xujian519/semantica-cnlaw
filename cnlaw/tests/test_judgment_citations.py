"""Tests for the judgment -> statute based_on citation planner."""

from cnlaw.ingest.judgment_citations import (
    build_judgment_citation_plan,
    extract_statute_refs,
)
from cnlaw.ingest.parse_judgment import PatentJudgment

_ARTICLES = [
    {
        "full_name": "中华人民共和国专利法",
        "source_date": "2020-10-17",
        "number": "第十一条",
        "text": "发明和实用新型专利权被授予后…不得为生产经营目的制造、使用、许诺销售、销售、进口其专利产品…",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国专利法",
        "source_date": "2020-10-17",
        "number": "第五十九条",
        "text": "发明或者实用新型专利权的保护范围以权利要求的内容为准…",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国专利法实施细则",
        "source_date": "2023-12-11",
        "number": "第二十一条",
        "text": "独立权利要求应当从整体上反映发明或者实用新型的技术方案…",
        "status": "现行有效",
    },
]


def test_extract_statute_refs_dedup():
    text = "依据《中华人民共和国专利法》第十一条和《中华人民共和国专利法》第十一条。"
    refs = extract_statute_refs(text)
    assert ("中华人民共和国专利法", 11) in refs
    assert refs.count(("中华人民共和国专利法", 11)) == 1


def test_build_plan_resolves_and_drops_missing():
    j1 = PatentJudgment(case_number="(2011)民初字第1号", judgment_id="(2011)民初字第1号",
                        legal_basis="《中华人民共和国专利法》第十一条和《中华人民共和国专利法》第五十九条",
                        full_text="本院依照《中华人民共和国专利法》第十一条作出判决。")
    j2 = PatentJudgment(case_number="(2011)民初字第2号", judgment_id="(2011)民初字第2号",
                        legal_basis="《中华人民共和国专利法》第二十五条", full_text="")
    plan = build_judgment_citation_plan([j1, j2], _ARTICLES)
    assert ("(2011)民初字第1号", "(2011)民初字第1号", "中华人民共和国专利法", "2020-10-17", "第十一条") in plan
    assert ("(2011)民初字第1号", "(2011)民初字第1号", "中华人民共和国专利法", "2020-10-17", "第五十九条") in plan
    assert not any(e[0] == "(2011)民初字第2号" and e[4] == "第二十五条" for e in plan)


def test_build_plan_ignores_unknown_statute():
    j = PatentJudgment(case_number="(2011)民初字第3号", judgment_id="(2011)民初字第3号",
                       legal_basis="《商标法》第五十七条", full_text="")
    assert build_judgment_citation_plan([j], _ARTICLES) == []
