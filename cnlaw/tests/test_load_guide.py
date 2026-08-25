"""Tests for the 专利审查指南 import pipeline (cnlaw/ingest/load_guide.py).

These exercise the pure plan-building helpers (build_import_plan /
build_article_plan) on guide-shaped documents — chapter sections carrying the
section-path hierarchy (number/level/parent) plus a separate 修改对照表 document
— without touching a live Neo4j store or the on-disk corpus.
"""

from cnlaw.ingest.load_laws_neo4j import build_article_plan, build_import_plan
from cnlaw.ingest.parse_laws import LawArticle, LawDocument


def _chapter_doc():
    """A synthetic guide chapter: a chapter intro plus nested numbered sections."""
    doc = LawDocument(
        name="说明书和权利要求书",
        full_name="专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书",
        category="审查指南",
        domain="专利",
        legal_level="部门规章",
        status="现行有效",
        source_date="2023-12-11",
    )
    doc.articles = [
        LawArticle(number="0", text="本章引言……", title="本章引言", level=0,
                   part="二", chapter="说明书和权利要求书", parent_number="",
                   kind="introduction"),
        LawArticle(number="1", text="引言正文……", title="引言", level=1,
                   part="二", chapter="说明书和权利要求书", parent_number="",
                   kind="guideline_section"),
        LawArticle(number="2", text="说明书概述……", title="说明书", level=1,
                   part="二", chapter="说明书和权利要求书", parent_number="",
                   kind="guideline_section"),
        LawArticle(number="2.1", text="说明书应当满足的要求……", title="说明书应当满足的要求",
                   level=2, part="二", chapter="说明书和权利要求书", parent_number="2",
                   kind="guideline_section"),
        LawArticle(number="2.1.1", text="清楚……", title="清楚", level=3,
                   part="二", chapter="说明书和权利要求书", parent_number="2.1",
                   kind="guideline_section"),
    ]
    return doc


def _amendment_doc():
    doc = LawDocument(
        name="专利审查指南修改对照表",
        full_name="专利审查指南修改对照表",
        category="审查指南",
        domain="专利",
        legal_level="部门规章",
        status="现行有效",
        source_date="2026-01-01",
    )
    doc.articles = [
        LawArticle(number="1", text="旧版（2023）：……\n新版（2026）：……",
                   title="4.1.2 发明人", kind="amendment"),
    ]
    return doc


def test_import_plan_guide_and_amendment_are_separate_docs():
    docs = [_chapter_doc(), _amendment_doc()]
    plan = build_import_plan(docs)
    # 两版（章节 + 对照表）各成一个节点，且无 supersedes
    assert len(plan.nodes) == 2
    assert plan.supersedes == []
    names = {n["full_name"] for n in plan.nodes}
    assert "专利审查指南修改对照表" in names
    # 每个节点都归属审查指南、domain 专利
    for n in plan.nodes:
        assert n["categories"] == ["审查指南"]
        assert n["domain"] == "专利"
        assert n["legal_level"] == "部门规章"


def test_article_plan_preserves_guide_hierarchy():
    records = build_article_plan([_chapter_doc()])
    by_num = {r["number"]: r for r in records}
    assert set(by_num) == {"0", "1", "2", "2.1", "2.1.1"}

    s_intro = by_num["0"]
    assert s_intro["kind"] == "introduction"
    assert s_intro["level"] == 0

    s21 = by_num["2.1"]
    assert s21["kind"] == "guideline_section"
    assert s21["level"] == 2
    assert s21["parent_number"] == "2"
    assert s21["part"] == "二"
    assert s21["chapter"] == "说明书和权利要求书"
    assert s21["title"] == "说明书应当满足的要求"

    s211 = by_num["2.1.1"]
    assert s211["level"] == 3
    assert s211["parent_number"] == "2.1"

    # order tracks document order (intro first)
    assert [r["order"] for r in records] == [0, 1, 2, 3, 4]


def test_article_plan_keeps_amendment_distinct():
    records = build_article_plan([_amendment_doc()])
    assert len(records) == 1
    assert records[0]["kind"] == "amendment"
    assert records[0]["title"] == "4.1.2 发明人"
    assert "新版（2026）：" in records[0]["text"]
    assert records[0]["full_name"] == "专利审查指南修改对照表"
    assert records[0]["source_date"] == "2026-01-01"
