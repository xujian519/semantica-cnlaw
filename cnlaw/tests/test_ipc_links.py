"""Tests for the IPC classified_in link planner (cnlaw/ingest/ipc_links.py)."""

from cnlaw.ingest.ipc_links import build_ipc_link_plan
from cnlaw.ingest.parse_ipc import IpcNode


def _nodes():
    return [
        IpcNode(code="A", title="人类生活必需", level="section"),
        IpcNode(code="A01", title="农业", level="class"),
        IpcNode(code="A01B", title="整地", level="subclass"),
        IpcNode(code="A01B1/00", title="犁", level="group"),
        IpcNode(code="A01B1/02", title="锹", level="subgroup"),
        IpcNode(code="H04", title="电通信", level="class"),
        IpcNode(code="H04L", title="传输数字信息", level="subclass"),
    ]


def test_decision_links_resolve_and_dedupe():
    records = _nodes()
    dec_rows = [
        ("4W1", "1", "A01B1/02"),        # exact subgroup
        ("4W2", "2", "A01B1/99"),        # missing subgroup -> main group
        ("4W1", "1", "A01B1/02"),        # duplicate -> skipped
        ("4W3", "3", "H04L 25/49"),      # subclass H04L resolves to H04L
    ]
    dec_edges, pat_edges = build_ipc_link_plan(dec_rows, [], records)
    assert ("4W1", "1", "A01B1/02") in dec_edges
    assert ("4W2", "2", "A01B1/00") in dec_edges
    assert ("4W3", "3", "H04L") in dec_edges
    assert sum(1 for e in dec_edges if e[0] == "4W1") == 1  # deduped
    assert pat_edges == []


def test_unresolvable_code_dropped():
    records = _nodes()
    dec_edges, _ = build_ipc_link_plan([("4W1", "1", "ZZ9")], [], records)
    assert dec_edges == []


def test_patent_links():
    records = _nodes()
    _, pat_edges = build_ipc_link_plan([], [("00807334.1", "A01B1/02"), ("00807334.2", "x")], records)
    assert ("00807334.1", "A01B1/02") in pat_edges
    # unresolvable patent code dropped
    assert len(pat_edges) == 1
