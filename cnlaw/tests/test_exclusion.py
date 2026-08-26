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


def test_national_regulations_not_misflagged_as_local():
    # 全国性法规会提及省/市/县/区，但并非地方性法规（回归：避免被误排除出库）
    assert not is_local_regulation("城市公共交通条例")
    assert not is_local_regulation("行政区划管理条例")
    assert not is_local_regulation("行政区域边界争议处理条例")
    assert not is_local_regulation("风景名胜区条例")
    assert not is_local_regulation("蓄滞洪区运用补偿暂行办法")
    assert not is_local_regulation("人力资源市场暂行条例")
    assert not is_local_regulation("中华人民共和国市场主体登记管理条例")
    assert not is_local_regulation("中华人民共和国自然保护区条例")
    assert not is_local_regulation("国务院关于股份有限公司境内上市外资股的规定")
    assert not is_local_regulation("国务院关于禁止在市场经济活动中实行地区封锁的规定")
    assert not is_local_regulation("最高人民法院关于审理证券市场虚假陈述侵权民事赔偿案件的若干规定")
    assert not is_local_regulation("最高人民法院关于认可和执行台湾地区法院民事判决的规定")
    assert not is_local_regulation("全国人民代表大会常务委员会关于在沿海港口城市设立海事法院的决定")
    assert not is_local_regulation("中国人民解放军选举全国人民代表大会和县级以上地方各级人民代表大会代表的办法")
    # 具体地名为主语的地方性法规仍应命中
    assert is_local_regulation("中国（上海）自由贸易试验区条例")
    assert is_local_regulation("河南省土地监察条例")
    assert is_local_regulation("深圳经济特区规划土地监察条例")


def test_exclude_junk_from_other():
    reason = should_exclude("劳动仲裁和劳动诉讼的攻略.md", "劳动仲裁和劳动诉讼的攻略", "其他")
    assert reason is not None
    assert "攻略" in reason


def test_exclude_index():
    assert should_exclude("_index.md", "_index", "刑法") is not None


def test_keep_real_law():
    assert should_exclude("刑法(2020-12-26).md", "刑法", "刑法") is None
    assert should_exclude("中华人民共和国民法典.md", "中华人民共和国民法典", "民法典") is None
