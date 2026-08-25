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


def test_extract_source_date_compact_filename():
    # 专利/地方法规的 md 用 _YYYYMMDD 紧凑日期（无横杠）
    assert extract_source_date("专利法实施细则_20231211.md") == "2023-12-11"
    assert extract_source_date("最高人民法院…规定（一）_20200910.md") == "2020-09-10"
    assert extract_source_date("专利法.md") is None


def test_extract_articles_bold_number():
    # 2026 惩罚性赔偿解释用 **第X条** 粗体条号
    body = textwrap.dedent(
        """\
        **第一条**　原告主张被告故意侵害其依法享有的知识产权且情节严重，请求判令被告承担惩罚性赔偿责任的，人民法院应当依法审理。

        **第二条**　原告请求惩罚性赔偿的，应当提出明确的赔偿数额、计算方法以及所依据的事实和理由。
        """
    )
    arts = extract_articles(body)
    assert [a.number for a in arts] == ["第一条", "第二条"]
    assert "人民法院应当依法审理" in arts[0].text


def test_extract_articles_strips_blockquote_and_rule():
    # 正文里的引用块（> （一）…）与 Markdown 分隔线应被清理，不污染条文
    body = textwrap.dedent(
        """\
        **第一条**　被告有下列情形之一的，人民法院可以认定其具有侵害知识产权的故意：

        ---

        > （一）经原告有效通知后，仍继续实施侵权行为的；

        > （二）实施盗版、假冒注册商标、假冒他人专利行为的。

        第二条　原告还主张**应当**从重处理。
        """
    )
    arts = extract_articles(body)
    assert len(arts) == 2
    assert arts[0].number == "第一条"
    assert "（一）经原告有效通知后" in arts[0].text
    assert "（二）实施盗版" in arts[0].text
    assert "---" not in arts[0].text
    # 正文行内 ** 加粗标记被清理
    assert "应当" in arts[1].text
    assert "**" not in arts[1].text


FLAT_MD = textwrap.dedent(
    """\
    # 最高人民法院关于审理侵犯专利权纠纷案件应用法律若干问题的解释

    > 法释〔2009〕21号 （2009年12月21日最高人民法院审判委员会第1480次会议通过 2009年12月28日最高人民法院公告公布 自2010年1月1日起施行） 为正确审理侵犯专利权纠纷案件，根据《中华人民共和国专利法》、《中华人民共和国民事诉讼法》等有关法律规定，结合审判实际，制定本解释。

    <!-- INFO END -->

    第一条 人民法院应当根据权利人主张的权利要求，依据专利法第五十九条第一款的规定确定专利权的保护范围。

    第二条 人民法院应当根据权利要求的记载，结合本领域普通技术人员阅读说明书及附图后对权利要求的理解，确定专利法第五十九条第一款规定的权利要求的内容。
    """
)


def test_parse_flat_document_with_sentinel(tmp_path):
    # 司法解释：INFO END 后无任何 # 标题（扁平结构），需正确切出正文而非整段当沿革
    p = tmp_path / "最高法院解释_20091228.md"
    p.write_text(FLAT_MD, encoding="utf-8")
    doc = parse_law_markdown(str(p), category="司法解释")
    assert doc.full_name == "最高人民法院关于审理侵犯专利权纠纷案件应用法律若干问题的解释"
    # 文件名紧凑日期
    assert doc.source_date == "2009-12-28"
    # 颁布日期取 blockquote 中最早的合法日期
    assert doc.promulgated_date == "2009-12-21"
    assert len(doc.articles) == 2
    assert doc.articles[0].number == "第一条"
    assert "专利法第五十九条第一款" in doc.articles[0].text


NO_SENTINEL_MD = textwrap.dedent(
    """\
    # 最高人民法院关于审理侵害知识产权民事纠纷案件适用惩罚性赔偿的解释

    **法释〔2026〕7号**

    （2026年4月7日最高人民法院审判委员会第1972次会议通过，自2026年5月1日起施行）

    ---

    为依法惩处严重侵害知识产权行为，严格落实知识产权惩罚性赔偿制度，根据《中华人民共和国民法典》、《中华人民共和国著作权法》、《中华人民共和国商标法》、《中华人民共和国专利法》等法律规定，制定本解释。

    ---

    **第一条**　原告主张被告故意侵害其依法享有的知识产权且情节严重，请求判令被告承担惩罚性赔偿责任的，人民法院应当依法审理。

    **第二条**　原告请求惩罚性赔偿的，应当提出明确的赔偿数额、计算方法以及所依据的事实和理由。
    """
)


def test_parse_document_without_sentinel(tmp_path):
    # 无 <!-- INFO END -->：前言/文号在正文前，正文从第一条开始，需正确切分
    p = tmp_path / "惩罚性赔偿解释（法释〔2026〕7号）.md"
    p.write_text(NO_SENTINEL_MD, encoding="utf-8")
    doc = parse_law_markdown(str(p), category="司法解释", domain="专利")
    assert doc.domain == "专利"
    assert doc.promulgated_date == "2026-04-07"
    assert doc.source_date is None  # 文件名无日期 → 现行有效（无日期版口径）
    assert len(doc.articles) == 2
    assert doc.articles[0].number == "第一条"
    assert "惩罚性赔偿责任" in doc.articles[0].text
