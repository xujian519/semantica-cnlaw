"""Unit tests for the precedent metadata post-filter (field-filtered search).

Covers the pure helper `_field_filter` in search_worker: ground (legal-basis
substring), IPC prefix, exact result / case_type, combined filters, and the
honest no-match for fields the corpus did not populate.
"""

from cnlaw.ingest.search_worker import (_authority_tier, _cn_num_to_int,
                                        _cn_numerals_to_arabic, _field_filter, _rank_hits)


def _hit(**kw):
    base = {
        "decision_id": "d1",
        "legal_basis": "",
        "ipc": "",
        "decision_result": "",
        "case_type": "",
    }
    base.update(kw)
    return base


def test_no_filter_passthrough():
    hits = [_hit(decision_id="a"), _hit(decision_id="b")]
    assert _field_filter(hits) == hits


def test_ground_substring_match():
    hits = [
        _hit(decision_id="a", legal_basis="专利法第22条第3款"),
        _hit(decision_id="b", legal_basis="专利法第26条第4款"),
    ]
    out = _field_filter(hits, ground="第22条第3款")
    assert [h["decision_id"] for h in out] == ["a"]


def test_ground_none_is_no_match():
    hits = [_hit(decision_id="a", legal_basis="")]
    assert _field_filter(hits, ground="第22条") == []


def test_ipc_prefix_match_handles_separators():
    # 「、」和「/」都是代码分隔符；前缀应按其中一个代码匹配。
    hits = [
        _hit(decision_id="a", ipc="B05C11/04、B05C1/12"),
        _hit(decision_id="b", ipc="H01M10/052"),
        _hit(decision_id="c", ipc=""),
    ]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="B05C")] == ["a"]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="H01M")] == ["b"]
    assert _field_filter(hits, ipc="B05C3") == []


def test_ipc_prefix_is_case_insensitive():
    hits = [_hit(decision_id="a", ipc="b05c11/04")]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="B05C")] == ["a"]


def test_result_exact_after_strip():
    hits = [
        _hit(decision_id="a", decision_result="维持专利权有效"),
        _hit(decision_id="b", decision_result="宣告专利权全部无效"),
    ]
    assert [h["decision_id"] for h in _field_filter(hits, result="维持专利权有效")] == ["a"]


def test_case_type_exact():
    hits = [
        _hit(decision_id="a", case_type="无效"),
        _hit(decision_id="b", case_type="复审"),
    ]
    assert [h["decision_id"] for h in _field_filter(hits, case_type="无效")] == ["a"]


def test_combined_filters_are_conjunctions():
    hits = [
        _hit(decision_id="a", legal_basis="专利法第22条第3款", ipc="B05C11/04",
             decision_result="维持专利权有效", case_type="无效"),
        _hit(decision_id="b", legal_basis="专利法第22条第3款", ipc="H01M10/052",
             decision_result="维持专利权有效", case_type="无效"),
        _hit(decision_id="c", legal_basis="专利法第22条第3款", ipc="B05C11/04",
             decision_result="宣告专利权全部无效", case_type="无效"),
    ]
    out = _field_filter(hits, ground="第22条第3款", ipc="B05C",
                        result="维持专利权有效", case_type="无效")
    assert [h["decision_id"] for h in out] == ["a"]


def test_ipc_filter_is_honest_for_fields_the_corpus_lacks():
    # 判决侧车不含 ipc：给了 ipc 过滤应返回空，而非误报。
    hits = [_hit(decision_id="a")]  # ipc 为空
    assert _field_filter(hits, ipc="B05C") == []


def test_cn_num_to_int():
    assert _cn_num_to_int("十") == 10
    assert _cn_num_to_int("二十") == 20
    assert _cn_num_to_int("二十二") == 22
    assert _cn_num_to_int("一百二十四") == 124
    assert _cn_num_to_int("九十九") == 99


def test_cn_numerals_to_arabic():
    assert _cn_numerals_to_arabic("第二十二条第三款") == "第22条第3款"
    assert _cn_numerals_to_arabic("第九十九条第二款") == "第99条第2款"
    assert _cn_numerals_to_arabic("第五条") == "第5条"


def test_ground_handles_chinese_numerals():
    # 决定用阿拉伯数字，判决用中文数字；ground 查询都应命中。
    hits = [
        _hit(decision_id="a", legal_basis="依照《中华人民共和国专利法》第二十二条第三款之规定"),
        _hit(decision_id="b", legal_basis="专利法第22条第3款"),
    ]
    out = _field_filter(hits, ground="第22条第3款")
    assert [h["decision_id"] for h in out] == ["a", "b"]


def test_ipc_predicate_handles_fullwidth_separators():
    # `；`（全角分号）和 `，`（全角逗号）都是代码分隔符，前缀匹配应奏效。
    hits = [
        _hit(decision_id="a", ipc="G01S 7/481； G01S 17/08"),
        _hit(decision_id="b", ipc="H02K 5/04，H02K 3/00"),
        _hit(decision_id="c", ipc="B05C11/04、B05C1/12"),
    ]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="G01S")] == ["a"]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="H02K")] == ["b"]
    assert [h["decision_id"] for h in _field_filter(hits, ipc="B05C")] == ["c"]


def _article_hit(**kw):
    base = {"full_name": "", "status": "现行有效", "category": "", "score": 0.0}
    base.update(kw)
    return base


def test_authority_tier():
    assert _authority_tier("行政法规") == 1
    assert _authority_tier("司法解释") == 1
    assert _authority_tier("") == 1
    assert _authority_tier("审查指南") == 2
    assert _authority_tier("书籍") == 4


def test_rank_hits_by_authority_tier():
    # 法律法规 > 审查指南 > 书籍，不论 embedding 分数。
    hits = [
        _article_hit(full_name="书", category="书籍", score=0.99),
        _article_hit(full_name="指南", category="审查指南", score=0.55),
        _article_hit(full_name="法", category="行政法规", score=0.40),
    ]
    ranked = _rank_hits(hits, k=3)
    assert [h["full_name"] for h in ranked] == ["法", "指南", "书"]


def test_rank_hits_current_version_first_within_same_tier():
    hits = [
        _article_hit(full_name="旧版", category="行政法规", status="已被修订", score=0.95),
        _article_hit(full_name="现行", category="行政法规", status="现行有效", score=0.60),
    ]
    ranked = _rank_hits(hits, k=2)
    assert [h["full_name"] for h in ranked] == ["现行", "旧版"]
