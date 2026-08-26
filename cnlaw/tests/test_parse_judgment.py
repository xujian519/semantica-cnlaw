"""Tests for the patent / IP judgment parser."""

import textwrap

from cnlaw.ingest.parse_judgment import (
    PatentJudgment,
    _extract_patent_numbers,
    _normalize_case_number,
    merge_part_judgments,
    parse_judgment_markdown,
)

# A-format (专利判决/): a 案件信息 block of **field**: value lines + 判决书正文.
A_MD = textwrap.dedent(
    """\
    # (2011)沪一中民五(知)初字第47号

    ---
    ## 案件信息
    **审理法院**: 上海市第一中级人民法院
    **案号**: (2011)沪一中民五(知)初字第47号
    **裁判日期**: 2013.06.21
    **案由**: 民事>知识产权与竞争纠纷>知识产权权属、侵权纠纷>专利权权属、侵权纠纷>侵害发明专利权纠纷【侵犯发明专利权纠纷】
    **被告**: 上海华勤通讯技术有限公司
    ---

    ## 判决书正文
    原告诺基亚公司。
    授权代表尼可拉斯•乌斯曼，该公司专利许可经理。

    被告上海华勤通讯技术有限公司。
    法定代表人邱文生，该公司董事长。

    原告诺基亚公司诉被告上海华勤通讯技术有限公司侵害发明专利权纠纷一案，本院于2011年1月10日受理后，依法组成合议庭，公开开庭进行了审理。

    原告诺基亚公司系名称为“选择数据传送方法”发明专利（专利号为：ZL200480001590.4）的专利权人。其主张专利权保护范围以权利要求7为准。

    本院认为，本案的争议焦点在于被诉侵权产品是否落入涉案专利权的保护范围。……

    据此，依照《中华人民共和国专利法》第十一条第一款、第五十九条第一款，《最高人民法院关于审理侵犯专利权纠纷案件应用法律若干问题的解释》第四条、第七条之规定，判决如下：

    驳回原告诺基亚公司全部诉讼请求。

    审判长：陈惠珍
    审判员：胡 瑜
    书记员：王 蕾
    """
)

# B-format (指导性专利判决文书_md/): newline-separated label ： value header, no section markers.
B_MD = textwrap.dedent(
    """\
    株式会社岛野与宁波市日骋工贸有限公司侵犯发明专利权纠纷再审民事判决书

    审理法院
    ：
    最高人民法院
    案号
    ：
    (2012)民提字第1号
    裁判日期
    ：
    2012.12.11
    案由
    ：
    民事>知识产权与竞争纠纷★>知识产权权属、侵权纠纷>专利权权属、侵权纠纷>侵害发明专利权纠纷【侵犯发明专利权纠纷】

    最高人民法院
    民事判决书
    (2012)民提字第1号

    申请再审人（一审原告、二审上诉人、原申请再审人）：株式会社岛野。
    被申请人（一审被告、二审被上诉人、原被申请人）：宁波市日骋工贸有限公司。

    申请再审人株式会社岛野系专利号为ZL94102612.4、发明名称为“后换档器支架”的中国发明专利的专利权人。……

    本院认为，本案的争议焦点为被诉侵权产品是否落入本案专利保护范围。……

    依照《中华人民共和国民事诉讼法》第一百八十条之规定，判决如下：驳回上诉，维持原判。

    审判长：王 闯
    审判员：罗 霞
    审判员：朱 理
    """
)


def test_parse_a_format(tmp_path):
    p = tmp_path / "nokia.md"
    p.write_text(A_MD, encoding="utf-8")
    j = parse_judgment_markdown(p)
    assert j.case_number == "(2011)沪一中民五(知)初字第47号"
    assert j.court == "上海市第一中级人民法院"
    assert j.decision_date == "2013-06-21"
    assert j.cause.startswith("民事")
    assert j.case_type == "民事"
    assert j.plaintiff == "诺基亚公司"
    assert j.defendant == "上海华勤通讯技术有限公司"
    assert j.application_number == "200480001590.4"
    assert j.patent_numbers == ["200480001590.4"]
    assert j.invention_name == "选择数据传送方法"
    assert "专利法》第十一条第一款" in j.legal_basis
    assert "驳回原告诺基亚公司" in j.decision_result
    assert j.domain == "专利判决"
    assert j.judgment_id == j.case_number


def test_parse_b_format(tmp_path):
    p = tmp_path / "shimano.md"
    p.write_text(B_MD, encoding="utf-8")
    j = parse_judgment_markdown(p)
    assert j.case_number == "(2012)民提字第1号"
    assert j.court == "最高人民法院"
    assert j.decision_date == "2012-12-11"
    assert j.case_type == "民事"
    assert j.plaintiff == "株式会社岛野"
    assert j.defendant == "宁波市日骋工贸有限公司"
    assert j.application_number == "94102612.4"
    assert j.patent_holder == "株式会社岛野"
    assert j.invention_name == "后换档器支架"
    assert "驳回上诉，维持原判" in j.decision_result


def test_normalize_case_number():
    assert _normalize_case_number("（2010）浦民三（知）初字第249 号") == "(2010)浦民三(知)初字第249号"
    assert _normalize_case_number("(2012)民提字第1号") == "(2012)民提字第1号"
    assert _normalize_case_number("") == ""


def test_extract_patent_numbers_zl_and_label():
    text = "原告系ZL200480001590.4号专利的专利权人。该专利申请号为200480001590.4。"
    primary, nums = _extract_patent_numbers(text)
    assert primary == "200480001590.4"
    assert nums == ["200480001590.4"]


def test_merge_part_judgments_dedup():
    a = PatentJudgment(case_number="(2012)民提字第1号", judgment_id="(2012)民提字第1号",
                       full_text="A", patent_numbers=["94102612.4"])
    b = PatentJudgment(case_number="(2012)民提字第1号", judgment_id="(2012)民提字第1号",
                       full_text="B更长的正文", patent_numbers=["94102612.4", "200480001590.4"])
    merged = merge_part_judgments([a, b])
    assert len(merged) == 1
    assert merged[0].full_text == "B更长的正文"
    assert merged[0].patent_numbers == ["94102612.4", "200480001590.4"]


def test_merge_part_judgments_distinct_kept():
    a = PatentJudgment(case_number="(2012)民提字第1号", judgment_id="(2012)民提字第1号", full_text="A")
    b = PatentJudgment(case_number="(2012)民提字第2号", judgment_id="(2012)民提字第2号", full_text="B")
    assert len(merge_part_judgments([a, b])) == 2
