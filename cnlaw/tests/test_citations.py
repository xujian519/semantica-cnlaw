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
