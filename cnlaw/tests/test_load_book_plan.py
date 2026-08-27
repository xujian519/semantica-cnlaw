"""Tests for the 以案说法 import pipeline (cnlaw/ingest/load_book.py).

These exercise the pure plan-building helpers (build_import_plan /
build_article_plan) on book-shaped documents — a chapter intro plus nested
numbered 要点 sections tagged as the 书籍 book layer — without touching a live
Neo4j store or the on-disk corpus.
"""

from cnlaw.ingest.load_laws_neo4j import build_article_plan, build_import_plan
from cnlaw.ingest.parse_laws import LawArticle, LawDocument


def _chapter_doc():
    doc = LawDocument(
        name="以案说法 第一章 不授予专利权的客体",
        full_name="《以案说法：专利复审、无效典型案例指引》第一章 不授予专利权的客体",
        category="书籍",
        domain="专利",
        legal_level="书籍",
        status="现行有效",
        source_date="2018-09-01",
        promulgated_date="2018-09-01",
    )
    doc.articles = [
        LawArticle(number="0", text="本章引言……", title="本章引言", level=0,
                   part="一", chapter="不授予专利权的客体", parent_number="",
                   kind="introduction"),
        LawArticle(number="1", text="《专利法》第2条所称的发明创造……",
                   title="《专利法》第2条所称的发明创造", level=1, part="一",
                   chapter="不授予专利权的客体", parent_number="", kind="book_section"),
        LawArticle(number="1.1", text="技术方案的判断……", title="技术方案的判断",
                   level=2, part="一", chapter="不授予专利权的客体", parent_number="1",
                   kind="book_section"),
        LawArticle(number="1.2.2", text="包括方法特征的产品权利要求……",
                   title="包括方法特征的产品权利要求", level=3, part="一",
                   chapter="不授予专利权的客体", parent_number="1.2", kind="book_section"),
    ]
    return doc


def test_import_plan_book_single_category():
    plan = build_import_plan([_chapter_doc()])
    assert len(plan.nodes) == 1
    assert plan.categories == ["书籍"]
    assert plan.belongs == [(plan.nodes[0]["key"], "书籍")]
    assert plan.supersedes == []
    n = plan.nodes[0]
    assert n["full_name"].startswith("《以案说法")
    assert n["categories"] == ["书籍"]
    assert n["domain"] == "专利"
    assert n["legal_level"] == "书籍"
    assert n["status"] == "现行有效"
    assert n["source_date"] == "2018-09-01"
    assert n["promulgated_date"] == "2018-09-01"


def test_article_plan_preserves_book_hierarchy():
    records = build_article_plan([_chapter_doc()])
    by_num = {r["number"]: r for r in records}
    assert set(by_num) == {"0", "1", "1.1", "1.2.2"}
    assert [r["order"] for r in records] == [0, 1, 2, 3]

    intro = by_num["0"]
    assert intro["kind"] == "introduction"
    assert intro["level"] == 0

    s11 = by_num["1.1"]
    assert s11["kind"] == "book_section"
    assert s11["level"] == 2
    assert s11["parent_number"] == "1"
    assert s11["part"] == "一"
    assert s11["chapter"] == "不授予专利权的客体"
    assert s11["full_name"].startswith("《以案说法")
    assert s11["source_date"] == "2018-09-01"

    s122 = by_num["1.2.2"]
    assert s122["level"] == 3
    assert s122["parent_number"] == "1.2"
