"""Tests for the local-regulation / junk exclusion rules (exclusion.py)."""

from cnlaw.ingest.exclusion import (
    is_index_file,
    is_local_regulation,
    should_exclude,
)


def test_is_index_file():
    assert is_index_file("_index.md")
    assert not is_index_file("刑法.md")


def test_local_regulation_names():
    # 混入行政法规目录的自治县条例 -> 应命中地方性法规特征
    assert is_local_regulation("三都水族自治县都柳江渔业条例")
    assert is_local_regulation("三江侗族自治县茶产业发展条例")
    assert is_local_regulation("上海市不动产登记若干规定")
    # 真行政法规不误伤
    assert not is_local_regulation("中华人民共和国刑法")
    assert not is_local_regulation("上海航运交易所管理规定")  # 国务院批准的部委规章
    assert not is_local_regulation("人民检察院刑事诉讼规则")


def test_exclude_junk_from_other():
    reason = should_exclude("劳动仲裁和劳动诉讼的攻略.md", "劳动仲裁和劳动诉讼的攻略", "其他")
    assert reason is not None
    assert "攻略" in reason


def test_exclude_index():
    assert should_exclude("_index.md", "_index", "刑法") is not None


def test_keep_real_law():
    assert should_exclude("刑法(2020-12-26).md", "刑法", "刑法") is None
    assert should_exclude("中华人民共和国民法典.md", "中华人民共和国民法典", "民法典") is None
