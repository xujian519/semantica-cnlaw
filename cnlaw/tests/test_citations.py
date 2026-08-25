"""Tests for article citation extraction / resolution (citations.py)."""

from cnlaw.ingest.citations import (
    build_citation_plan,
    cn2int,
    extract_citations,
    number_int,
    pick_doc_version,
    resolve_name,
)


def test_cn2int_arabic_and_chinese():
    assert cn2int("二百九十四") == 294
    assert cn2int("十五") == 15
    assert cn2int("一百") == 100
    assert cn2int("三十八") == 38
    assert cn2int("一百零五") == 105
    assert cn2int("一") == 1
    assert cn2int("十") == 10
    assert cn2int("二十") == 20
    assert cn2int("125") == 125


def test_cn2int_invalid():
    assert cn2int("") is None
    assert cn2int("零") is None  # 条号不会为 0
    assert cn2int("abc") is None
    assert cn2int("二百甲四") is None


def test_number_int_from_article_number():
    assert number_int("第一百二十五条") == 125
    assert number_int("第一条") == 1
    assert number_int("") is None


def test_extract_citations_same_and_cross():
    text = "依据本法第五条和《中华人民共和国刑法》第二百九十四条的规定。"
    cits = extract_citations(text, "中华人民共和国刑法")
    assert ("same", "中华人民共和国刑法", 5) in cits
    assert ("cross", "中华人民共和国刑法", 294) in cits


def test_extract_citations_ignores_short_forms_without_number():
    # 无数字引用（如“本法”）不应产生引用
    assert extract_citations("本法另有规定", "中华人民共和国刑法") == []


def _doc(name, date, status):
    return name, date, status


def test_resolve_name_exact_then_substring():
    doc_index = {
        "中华人民共和国刑法": {"2020-12-26": "现行有效"},
        "中华人民共和国土地管理法": {"": "现行有效"},
    }
    assert resolve_name("中华人民共和国刑法", doc_index) == "中华人民共和国刑法"
    # 简称 → 唯一的包含匹配
    assert resolve_name("土地管理法", doc_index) == "中华人民共和国土地管理法"
    # 无名匹配
    assert resolve_name("不存在的法", doc_index) is None


def test_resolve_name_ambiguous_returns_none():
    doc_index = {
        "中华人民共和国刑法": {"2020-12-26": "现行有效"},
        "中华人民共和国刑法修正案": {"2018-03-11": "现行有效"},
    }
    assert resolve_name("刑法", doc_index) is None  # 命中两个，歧义


def test_pick_doc_version_prefers_current_then_dated():
    doc_index = {
        "某法": {"2020-01-01": "现行有效", "2019-01-01": "已被修订", "": "现行有效"},
    }
    # 既有日期又有无日期现行版，取日期最新
    assert pick_doc_version("某法", doc_index) == "2020-01-01"


def test_pick_doc_version_undated_current_fallback():
    doc_index = {"某法": {"": "现行有效"}}
    assert pick_doc_version("某法", doc_index) == ""


def test_pick_doc_version_revised_only():
    doc_index = {"某法": {"2018-01-01": "已被修订"}}
    assert pick_doc_version("某法", doc_index) == "2018-01-01"


ARTICLES = [
    {
        "full_name": "中华人民共和国刑法",
        "source_date": "2020-12-26",
        "number": "第五条",
        "text": "依据《中华人民共和国治安管理处罚法》第三条和本法第七条的规定。",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国刑法",
        "source_date": "2020-12-26",
        "number": "第七条",
        "text": "本法另有规定。",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国治安管理处罚法",
        "source_date": "2012-10-26",
        "number": "第三条",
        "text": "依据《土地管理法》第一条规定。",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国土地管理法",
        "source_date": "",
        "number": "第一条",
        "text": "依据本法第二条。",
        "status": "现行有效",
    },
]


def test_build_citation_plan_cross_and_same():
    plan = build_citation_plan(ARTICLES)
    # 刑法第五条 → 治安管理处罚法第三条（跨文档精确名）
    assert (
        ("中华人民共和国刑法", "2020-12-26", "第五条"),
        ("中华人民共和国治安管理处罚法", "2012-10-26", "第三条"),
    ) in plan
    # 治安管理处罚法第三条 → 土地管理法第一条（跨文档简称，无日期现行版）
    assert (
        ("中华人民共和国治安管理处罚法", "2012-10-26", "第三条"),
        ("中华人民共和国土地管理法", "", "第一条"),
    ) in plan


def test_build_citation_plan_drops_unresolvable_and_self():
    plan = build_citation_plan(ARTICLES)
    # 刑法第五条“本法第七条”在同版存在 → 应成同文档引用边
    assert (
        ("中华人民共和国刑法", "2020-12-26", "第五条"),
        ("中华人民共和国刑法", "2020-12-26", "第七条"),
    ) in plan
    # 土地管理法第一条“本法第二条”目标不存在 → 被丢弃
    assert not any(
        s == ("中华人民共和国土地管理法", "", "第一条") and t == ("中华人民共和国土地管理法", "", "第二条")
        for s, t in plan
    )


def test_extract_citations_guide_everywhere_including_out_of_range():
    # the guide uses bare law names (no 《》) and intra-guide section refs
    text = "根据专利法第二十二条第三款的规定。参见本章第 2.1 节。适用本部分第四章第 3.1 节的规定。"
    self_name = "专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书"
    cits = extract_citations(text, self_name)
    assert ("cross", "专利法", 22) in cits
    assert ("guide_chapter", self_name, "2.1") in cits
    assert ("guide_part", "四", "3.1") in cits


def test_extract_citations_bare_law_implementation_regulation():
    # “专利法实施细则” must not be swallowed as a plain “专利法” reference
    cits = extract_citations("依照专利法实施细则第五十七条的规定。", "中华人民共和国专利法实施细则")
    assert ("cross", "专利法实施细则", 57) in cits
    assert not any(c.number == 5 for c in cits if c.kind == "cross")  # not 第五条第...


GUIDE_ARTICLES = [
    {
        "full_name": "专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书",
        "source_date": "2023-12-11",
        "number": "2",
        "text": "根据专利法第二十二条第三款的规定。参见本章第 2.1 节。适用本部分第四章第 3.1 节的规定。",
        "status": "现行有效",
    },
    {
        "full_name": "专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书",
        "source_date": "2023-12-11",
        "number": "2.1",
        "text": "说明书应当对发明作出清楚、完整的说明。",
        "status": "现行有效",
    },
    {
        "full_name": "专利审查指南 第二部分 实质审查·第四章 创造性",
        "source_date": "2023-12-11",
        "number": "3.1",
        "text": "审查创造性时……",
        "status": "现行有效",
    },
    {
        "full_name": "中华人民共和国专利法",
        "source_date": "2020-10-17",
        "number": "第二十二条",
        "text": "授予专利权的发明和实用新型应当具备新颖性、创造性和实用性。",
        "status": "现行有效",
    },
]


def test_build_citation_plan_guide_sections_and_bare_law():
    plan = build_citation_plan(GUIDE_ARTICLES)
    guide = "专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书"
    creative = "专利审查指南 第二部分 实质审查·第四章 创造性"
    # 指南 第2节 引 专利法第二十二条（bare 法名 → 唯一全称）
    assert (
        (guide, "2023-12-11", "2"),
        ("中华人民共和国专利法", "2020-10-17", "第二十二条"),
    ) in plan
    # 指南 第2节 引 本章 2.1（同文档节引用）
    assert ((guide, "2023-12-11", "2"), (guide, "2023-12-11", "2.1")) in plan
    # 指南 第2节 引 本部分第四章 3.1（跨章同部分）
    assert ((guide, "2023-12-11", "2"), (creative, "2023-12-11", "3.1")) in plan
