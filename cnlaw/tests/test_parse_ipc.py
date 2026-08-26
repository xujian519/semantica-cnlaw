"""Tests for the IPC classification parser (cnlaw/ingest/parse_ipc.py)."""

from cnlaw.ingest.parse_ipc import (
    build_ipc_index,
    build_ipc_tree,
    normalize_ipc_codes,
    parse_ipc_file,
    resolve_ipc,
    resolve_ipc_in_index,
)

SAMPLE = """\
            2026.01版IPC分类表-A部

A                A部——人类生活必需
                 分部：农业
A01              农业；林业；畜牧业；狩猎；诱捕；捕鱼
A01B             农业或林业的整地；一般农业机械或农具的部件、零件或附件
A01B1/00         手动工具（草坪修整机入A01G3/06）[2006.01]
A01B1/02   .     锹；铲[2006.01]
A01B1/04   ..    带齿的[2006.01]
A01B1/06   .     锄；手动中耕机[2006.01]
A01B3/00         装有固定式犁铧的犁[2006.01]
A01B3/02   .     人力犁[2006.01]
A01B3/421  ....  带有单体式悬挂架的[2006.01]
                 缩进续行不应被当作条目
"""


def test_parse_levels_and_codes(tmp_path):
    f = tmp_path / "IPC_A部_2026.01.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    nodes = parse_ipc_file(f)
    by = {n.code: n for n in nodes}
    assert by["A"].level == "section"
    assert by["A01"].level == "class"
    assert by["A01B"].level == "subclass"
    assert by["A01B1/00"].level == "group"
    assert by["A01B1/02"].level == "subgroup"
    # 缩进续行不产生额外节点
    assert len(nodes) == len(by)


def test_title_clean_and_version_stripped(tmp_path):
    f = tmp_path / "IPC_A部_2026.01.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    by = {n.code: n for n in parse_ipc_file(f)}
    assert by["A01B1/00"].title == "手动工具（草坪修整机入A01G3/06）"
    assert by["A01B1/02"].title == "锹；铲"
    assert by["A"].title == "人类生活必需"  # 部标题去掉破折号


def test_parent_edges_from_code(tmp_path):
    f = tmp_path / "IPC_A部_2026.01.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    nodes = parse_ipc_file(f)
    _, edges = build_ipc_tree(nodes)
    edge_map = dict(edges)
    assert edge_map.get("A01") == "A"
    assert edge_map.get("A01B") == "A01"
    assert edge_map.get("A01B1/00") == "A01B"
    assert edge_map.get("A01B1/02") == "A01B1/00"
    # 嵌套小组挂到最近上位小组
    assert edge_map.get("A01B3/421") == "A01B3/42" or edge_map.get("A01B3/421") == "A01B3/02"
    assert edge_map.get("A01B3/02") == "A01B3/00"


def test_resolve_falls_back_hierarchy(tmp_path):
    f = tmp_path / "IPC_A部_2026.01.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    nodes = parse_ipc_file(f)
    index = build_ipc_index(nodes)
    # 精确命中小组
    assert resolve_ipc_in_index("A01B1/02", index) == "A01B1/02"
    # 不存在的小组回退到大组
    assert resolve_ipc_in_index("A01B1/99", index) == "A01B1/00"
    # 未知小类（类存在）回退到类
    assert resolve_ipc_in_index("A01X1/02", index) == "A01"
    # 未知类回退到部
    assert resolve_ipc_in_index("A09X1/02", index) == "A"
    assert resolve_ipc("A01B1/02", nodes) == "A01B1/02"


def test_normalize_ipc_codes_cleans_dirty_field():
    assert normalize_ipc_codes("H04L 25/49") == ["H04L25/49"]
    assert normalize_ipc_codes("F28F 19/04；B23K10/00") == ["F28F19/04", "B23K10/00"]
    assert normalize_ipc_codes("H04L25/49(2006.01)、H04L25/00") == ["H04L25/49", "H04L25/00"]
    assert normalize_ipc_codes("") == []
