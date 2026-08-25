"""Tests for the M1 Neo4j import plan (cnlaw/ingest/load_laws_neo4j.py).

These exercise the pure planning logic (dedup, status, category, supersedes)
without touching a live database.
"""

from cnlaw.ingest.load_laws_neo4j import build_article_plan, build_import_plan
from cnlaw.ingest.parse_laws import LawArticle, LawDocument


def _doc(full_name, category, source_date=None, name=None):
    return LawDocument(
        name=name or full_name,
        full_name=full_name,
        category=category,
        legal_level="法律",
        promulgated_date="1979-07-01",
        source_date=source_date,
    )


def test_dedups_same_document_across_categories():
    # 专利法同一版本（同 full_name+source_date）出现在两个部门目录 -> 应去重为一个节点
    docs = [
        _doc("中华人民共和国专利法", "行政法", "2020-10-17"),
        _doc("中华人民共和国专利法", "民法商法", "2020-10-17"),
    ]
    plan = build_import_plan(docs)
    assert len(plan.nodes) == 1
    node = plan.nodes[0]
    # 两个来源类别都应保留
    assert set(node["categories"]) == {"行政法", "民法商法"}


def test_versions_separate_nodes_and_status():
    docs = [
        _doc("中华人民共和国刑法", "刑法", "2020-12-26"),
        _doc("中华人民共和国刑法", "刑法", "1997-03-14"),
        _doc("中华人民共和国刑法", "刑法", None),
    ]
    plan = build_import_plan(docs)
    # 三个版本 -> 三个节点
    assert len(plan.nodes) == 3
    status_by_key = {n["key"]: n["status"] for n in plan.nodes}
    # 无日期版=现行有效，最新日期版=现行有效，历史版=已被修订
    assert status_by_key["中华人民共和国刑法@"] == "现行有效"
    assert status_by_key["中华人民共和国刑法@2020-12-26"] == "现行有效"
    assert status_by_key["中华人民共和国刑法@1997-03-14"] == "已被修订"


def test_supersedes_between_versions():
    docs = [
        _doc("中华人民共和国刑法", "刑法", "2020-12-26"),
        _doc("中华人民共和国刑法", "刑法", "1997-03-14"),
    ]
    plan = build_import_plan(docs)
    assert ("中华人民共和国刑法@1997-03-14", "中华人民共和国刑法@2020-12-26") in plan.supersedes


def test_category_membership_recorded():
    docs = [_doc("中华人民共和国民法典", "民法典")]
    plan = build_import_plan(docs)
    assert "民法典" in plan.categories
    assert ("中华人民共和国民法典@", "民法典") in plan.belongs


def test_current_version_has_no_supersedes():
    # 只有现行版本时，不应产生 supersedes
    docs = [_doc("中华人民共和国刑法", "刑法", "2020-12-26")]
    plan = build_import_plan(docs)
    assert plan.supersedes == []


def test_article_plan_dedups_and_counts():
    # 同一法律同版本出现在两个目录 -> 条文只取一份
    d1 = _doc("中华人民共和国刑法", "刑法", "2020-12-26")
    d1.articles = [LawArticle("第一条", "为了惩罚犯罪…"), LawArticle("第一百二十条之一", "资助恐怖活动…")]
    d2 = _doc("中华人民共和国刑法", "刑法", "2020-12-26")
    d2.articles = [LawArticle("第一条", "第二条重复目录应被跳过…")]
    plan = build_article_plan([d1, d2])
    assert len(plan) == 2
    assert plan[0] == {
        "full_name": "中华人民共和国刑法",
        "source_date": "2020-12-26",
        "number": "第一条",
        "text": "为了惩罚犯罪…",
        "order": 0,
    }
    assert plan[1]["number"] == "第一百二十条之一"
    assert plan[1]["order"] == 1
