"""Tests for the patent invalidation / reexamination decision parser."""

import textwrap

from cnlaw.ingest.parse_decision import (
    PatentDecision,
    _normalize_date,
    merge_multipart,
    parse_decision_markdown,
)

A_FORMAT_MD = textwrap.dedent(
    """\
    # 专利无效复审决定 WX9999

    中华人民共和国国家知识产权局专利复审委员会
    无效宣告请求审查决定
    |决   定   号    |第         9999号                              |
    |决   定   日    |2004年01月29日                                |
    |发明创造名称    |一种钢管束内外壁防腐方法                      |
    |国际分类号      |F28F 19/04                                    |
    |专 利 权 人     |许文庆                                        |
    |专   利   号    |88103519.X                                    |
    |申   请   日    |1988年6月8日                                  |
    |授权公告日      |1991年3月6日                                  |
    |法 律  依  据   |专利法第22条第2款、第3款， 第33条             |

    一、案由
    本无效宣告请求涉及中华人民共和国国家知识产权局于1991年3月6日审定公告的发明专利权。

    二、决定的理由
    权利要求1与对比文件1相比存在区别技术特征。

    三、决定
    维持第88103519.X号发明专利权有效。
    """
)

B_FORMAT_MD = textwrap.dedent(
    """\
    # 专利无效复审决定 008073341

    无效宣告请求审查决定书

    （第566693号）

    根据专利法第46条第1款的规定，国家知识产权局对无效宣告请求人就上述专利权所
    提出的无效宣告请求进行了审查，现决定如下：

    宣告专利权全部无效。

    宣告专利权部分无效。

    维持专利权有效。

    根据专利法第46条第2款的规定，对本决定不服的，可以在收到本通知之日起3个月
    内向北京知识产权法院起诉，对方当事人作为第三人参加诉讼。

    国家知识产权局

    无效宣告请求审查决定（第566693号）

    一、案由
    ...

    ## 决定详情

    | {{gg_fawenr}} | 发文日：   {{gg_fawenr}} |
    | 申请号或专利号：00807334.1 | 申请号或专利号：00807334.1 |
    | 案件编号： | 4W116319 | 4W116319 |

    ## 附件表格 3

    | 案件编号 | 第4W116319号 |
    | 决定日 | 2024年01月29日 |
    | 发明创造名称 | 将管道分成多个分隔间的方法和装置 |
    | 国际分类号 | H02G 3/00 |
    | 无效宣告请求人 | 张青芳 |
    | 专利权人 | 威斯克伊奎缇公司 |
    | 专利号 | 00807334.1 |
    | 申请日 | 2000年06月21日 |
    | 优先权日 | 1999年06月23日 |
    | 授权公告日 | 2004年01月21日 |
    | 无效宣告请求日 | 2023年06月16日 |
    | 法律依据 | 专利法实施细则第20条第1款，专利法第22条第2、3款 |

    三、决定

    维持00807334.1号发明专利权有效。
    """
)

REEXAM_MD = textwrap.dedent(
    """\
    # 专利无效复审决定 1F101201_31834

    |案件编号 |1F101201                    |
    |决定日   |2011年04月22日              |
    |发明创造名称|脉冲波形生成方法          |
    |国际分类号  |H04L 25/49               |
    |复审请求人  |横滨TLO株式会社          |
    |申请号      |200380109882.5           |
    |申请日      |2003年12月16日           |
    |优先权日    |2003年02月25日           |
    |公开日      |2006年03月29日           |
    |复审请求日  |2009年12月24日           |
    |法律依据    |专利法第22条第2款        |

    复 审 决 定 书

    （第31834号）

    一、案由
    本复审请求涉及名称为“脉冲波形生成方法”的发明专利申请。

    二、决定的理由
    复审请求人已删除存在缺陷的权利要求，克服了驳回决定的缺陷。

    三、决定

    撤销国家知识产权局于2009年09月11日对本申请作出的驳回决定。
    """
)


def test_parse_a_format_table_header(tmp_path):
    p = tmp_path / "WX9999.md"
    p.write_text(A_FORMAT_MD, encoding="utf-8")
    d = parse_decision_markdown(p)
    assert d.case_type == "无效"
    assert d.decision_id == "9999"
    assert d.case_number == "WX9999"
    assert d.decision_date == "2004-01-29"
    assert d.invention_name == "一种钢管束内外壁防腐方法"
    assert d.ipc == "F28F 19/04"
    assert d.patent_holder == "许文庆"
    assert d.application_number == "88103519.X"
    assert d.application_date == "1988-06-08"
    assert d.grant_date == "1991-03-06"
    assert d.legal_basis == "专利法第22条第2款、第3款， 第33条"
    assert d.decision_result == "维持专利权有效"
    assert d.domain == "专利复审无效"
    assert d.confidence == "parsed"


def test_parse_b_format_patent_number(tmp_path):
    p = tmp_path / "008073341.md"
    p.write_text(B_FORMAT_MD, encoding="utf-8")
    d = parse_decision_markdown(p)
    assert d.case_type == "无效"
    # decision number comes from the inline （第566693号）
    assert d.decision_id == "566693"
    assert d.case_number == "4W116319"
    assert d.decision_date == "2024-01-29"
    assert d.invention_name == "将管道分成多个分隔间的方法和装置"
    assert d.ipc == "H02G 3/00"
    assert d.requesting_party == "张青芳"
    assert d.patent_holder == "威斯克伊奎缇公司"
    assert d.application_number == "00807334.1"
    assert d.application_date == "2000-06-21"
    assert d.priority_date == "1999-06-23"
    assert d.grant_date == "2004-01-21"
    assert d.requester_date == "2023-06-16"
    assert "专利法实施细则第20条第1款" in d.legal_basis
    # the leading boilerplate "维持专利权有效。" must NOT win over the real outcome
    assert d.decision_result == "维持专利权有效"


def test_duplicate_column_header_not_swallowed(tmp_path):
    # B-format noisy header repeats the label across columns; the value must not
    # be captured as the label text itself.
    md = textwrap.dedent(
        """\
        # 专利无效复审决定 008073341

        无效宣告请求审查决定书

        （第566693号）

        | 发明创造名称： | 发明创造名称： | 将管道分成多个分隔间的方法和装置 | 发明创造名称： | 发明创造名称： | 将管道分成多个分隔间的方法和装置 |
        | 申请号或专利号：00807334.1 | 申请号或专利号：00807334.1 |

        ## 附件表格 3

        | 案件编号 | 第4W116319号 |
        | 发明创造名称 | 将管道分成多个分隔间的方法和装置 |
        | 专利号 | 00807334.1 |

        三、决定

        维持00807334.1号发明专利权有效。
        """
    )
    p = tmp_path / "008073341.md"
    p.write_text(md, encoding="utf-8")
    d = parse_decision_markdown(p)
    assert d.invention_name == "将管道分成多个分隔间的方法和装置"
    assert d.application_number == "00807334.1"
    assert d.decision_result == "维持专利权有效"


def test_parse_reexamination(tmp_path):
    p = tmp_path / "1F101201_31834_20110422_2003801098825.md"
    p.write_text(REEXAM_MD, encoding="utf-8")
    d = parse_decision_markdown(p)
    assert d.case_type == "复审"
    assert d.decision_id == "31834"
    assert d.case_number == "1F101201"
    assert d.decision_date == "2011-04-22"
    assert d.invention_name == "脉冲波形生成方法"
    assert d.ipc == "H04L 25/49"
    assert d.requesting_party == "横滨TLO株式会社"
    assert d.application_number == "200380109882.5"
    assert d.application_date == "2003-12-16"
    assert d.priority_date == "2003-02-25"
    assert d.publication_date == "2006-03-29"
    assert d.requester_date == "2009-12-24"
    assert d.decision_result == "撤销驳回决定"


def test_normalize_date_garbled_and_valid():
    assert _normalize_date("20096年412月 月16日") == ""
    assert _normalize_date("2024年01月29日") == "2024-01-29"
    assert _normalize_date("1988年6月8日") == "1988-06-08"
    assert _normalize_date("") == ""


def test_merge_multipart_same_case():
    a = PatentDecision(decision_id="1", case_number="4W1", full_text="部分A", claims_original="1. 权利要求一")
    b = PatentDecision(decision_id="1", case_number="4W1", full_text="部分B较长的正文", claims_original="2. 权利要求二")
    merged = merge_multipart([a, b])
    assert len(merged) == 1
    assert merged[0].full_text == "部分B较长的正文"
    # both claim parts kept, deduped, in order
    assert "权利要求一" in merged[0].claims_original
    assert "权利要求二" in merged[0].claims_original


def test_merge_multipart_distinct_cases_kept():
    a = PatentDecision(decision_id="1", case_number="4W1", full_text="A")
    b = PatentDecision(decision_id="2", case_number="4W2", full_text="B")
    assert len(merge_multipart([a, b])) == 2


def test_json_backfill(tmp_path):
    p = tmp_path / "missing_points.md"
    p.write_text(A_FORMAT_MD, encoding="utf-8")
    record = {
        "source_file": "missing_points.md",
        "metadata": {
            "decision_no": "9999",
            "decision_points": "发明有突出的实质性特点，是指……",
            "legal_basis": ["专利法第22条第3款"],
        },
        "decision_result": "维持专利权有效",
        "claims_original": "1. 一种钢管束内外壁防腐方法……",
    }
    d = parse_decision_markdown(p, json_record=record)
    # fields the md already extracted stay 'parsed' values
    assert d.decision_id == "9999"
    # backfilled fields are present and confidence flagged
    assert d.decision_points == "发明有突出的实质性特点，是指……"
    assert d.confidence == "json_backfilled"
