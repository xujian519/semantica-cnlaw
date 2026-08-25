"""Tests for the Chinese legal Markdown parser (cnlaw/ingest/parse_laws.py)."""

import textwrap

import pytest

from cnlaw.ingest.parse_laws import (
    LawArticle,
    LawDocument,
    classify_legal_level,
    compute_effective_status,
    extract_articles,
    extract_dates,
    extract_source_date,
    parse_law_markdown,
)

# 无日期版结构：# 标题 -> 逐行沿革 -> <!-- INFO END --> -> 正文（半角空格分隔）
UNDATED_MD = textwrap.dedent(
    """\
    # 中华人民共和国刑法

    1979年7月1日 第五届全国人民代表大会第二次会议通过

    1997年3月14日 第八届全国人民代表大会第五次会议修订

    2020年12月26日 第十三届全国人民代表大会常务委员会第二十四次会议通过的《中华人民共和国刑法修正案（十一）》

    <!-- INFO END -->

    ## 第一编 总则

    ### 第一章 刑法的任务、基本原则和适用范围

    第一条 为了惩罚犯罪，保护人民，根据宪法，结合我国同犯罪作斗争的具体经验及实际情况，制定本法。

    第二条 中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争，以保卫国家安全，保卫人民民主专政的政权和社会主义制度。
    """
)

# 带日期版结构：# 标题 -> 单个日期行 -> <!-- INFO END --> -> 沿革括弧段 -> 目录 -> 编/章标题 -> 正文（全角空格分隔）
DATED_MD = textwrap.dedent(
    """\
    # 中华人民共和国刑法

    2020年12月26日

    <!-- INFO END -->

    中华人民共和国刑法

    （1979年7月1日第五届全国人民代表大会第二次会议通过　2020年12月26日第十三届全国人民代表大会常务委员会第二十四次会议通过的《中华人民共和国刑法修正案（十一）》修正）

    ## 目录

    - 第一编　总　　则

    ## 第一编 总则

    ### 第一章 刑法的任务、基本原则和适用范围

    第一条　为了惩罚犯罪，保护人民，根据宪法，结合我国同犯罪作斗争的具体经验及实际情况，制定本法。

    第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争，以保卫国家安全。
    """
)


def test_extract_source_date():
    assert extract_source_date("刑法.md") is None
    assert extract_source_date("刑法(2020-12-26).md") == "2020-12-26"
    assert extract_source_date("会计法(2024-06-28).md") == "2024-06-28"


def test_extract_dates_undated():
    dates = extract_dates(UNDATED_MD.split("<!-- INFO END -->")[0])
    assert dates[0] == "1979-07-01"
    assert dates == ["1979-07-01", "1997-03-14", "2020-12-26"]


def test_extract_articles_undated():
    body = UNDATED_MD.split("<!-- INFO END -->")[1]
    arts = extract_articles(body)
    assert len(arts) == 2
    assert arts[0].number == "第一条"
    assert "制定本法" in arts[0].text
    assert arts[1].number == "第二条"
    assert "保卫国家安全" in arts[1].text


def test_extract_articles_subarticle_number():
    body = "第一百二十条 组织、领导恐怖活动组织的，…\n第一百二十条之一 资助恐怖活动组织、实施恐怖活动的个人的，…\n"
    arts = extract_articles(body)
    assert [a.number for a in arts] == ["第一百二十条", "第一百二十条之一"]


def test_extract_articles_dated_fullwidth_space():
    body = DATED_MD.split("<!-- INFO END -->")[1]
    arts = extract_articles(body)
    assert len(arts) == 2
    assert arts[0].number == "第一条"
    assert "制定本法" in arts[0].text


def test_parse_undated_document(tmp_path):
    p = tmp_path / "刑法.md"
    p.write_text(UNDATED_MD, encoding="utf-8")
    doc = parse_law_markdown(str(p), category="刑法")
    assert isinstance(doc, LawDocument)
    assert doc.full_name == "中华人民共和国刑法"
    assert doc.name == "刑法"
    assert doc.category == "刑法"
    assert doc.promulgated_date == "1979-07-01"
    assert doc.amended_dates == ["1997-03-14", "2020-12-26"]
    assert doc.source_date is None
    assert doc.legal_level == "法律"
    assert len(doc.articles) == 2


def test_parse_dated_document(tmp_path):
    p = tmp_path / "刑法(2020-12-26).md"
    p.write_text(DATED_MD, encoding="utf-8")
    doc = parse_law_markdown(str(p), category="刑法")
    assert doc.source_date == "2020-12-26"
    # 颁布日期取最早（1979 通过），历次修正含文件名日期
    assert doc.promulgated_date == "1979-07-01"
    assert "2020-12-26" in doc.amended_dates
    assert len(doc.articles) == 2


def test_classify_legal_level():
    assert classify_legal_level("宪法", "中华人民共和国宪法") == "宪法"
    assert classify_legal_level("刑法", "中华人民共和国刑法") == "法律"
    assert classify_legal_level("民法典", "中华人民共和国民法典") == "法律"
    assert classify_legal_level("行政法规", "中华人民共和国民法典") == "行政法规"
    assert classify_legal_level("司法解释", "人民检察院刑事诉讼规则") == "司法解释"
    assert classify_legal_level("部门规章", "汽车贷款管理办法") == "部门规章"


def test_compute_effective_status_undated_is_current():
    # 同一法律的三个版本：无日期 + 最新日期版 + 历史日期版
    docs = [
        LawDocument(name="刑法", full_name="中华人民共和国刑法", category="刑法", source_date=None),
        LawDocument(name="刑法", full_name="中华人民共和国刑法", category="刑法", source_date="2020-12-26"),
        LawDocument(name="刑法", full_name="中华人民共和国刑法", category="刑法", source_date="1997-03-14"),
    ]
    status = compute_effective_status(docs)
    # 无日期版 = 现行有效（口径已确认），最新日期版 = 现行有效，历史版 = 已被修订
    assert status[id(docs[0])] == "现行有效"
    assert status[id(docs[1])] == "现行有效"
    assert status[id(docs[2])] == "已被修订"
