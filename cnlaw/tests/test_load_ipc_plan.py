"""Tests for the IPC import plan (cnlaw/ingest/load_ipc_neo4j.py)."""

from cnlaw.ingest.load_ipc_neo4j import build_ipc_plan
from cnlaw.ingest.parse_ipc import IpcNode


def _node(code, level, title="t"):
    return IpcNode(code=code, title=title, level=level)


def test_build_plan_keeps_nodes_and_parents():
    nodes = [
        _node("A", "section", "人类生活必需"),
        _node("A01", "class", "农业"),
        _node("A01B", "subclass", "整地"),
        _node("A01B1/00", "group", "犁"),
        _node("A01B1/02", "subgroup", "锹"),
    ]
    plan = build_ipc_plan(nodes)
    assert len(plan.nodes) == 5
    assert plan.nodes[0]["version"] == "2026.01"
    parent_map = dict(plan.parents)
    assert parent_map["A01"] == "A"
    assert parent_map["A01B1/00"] == "A01B"
    assert parent_map["A01B1/02"] == "A01B1/00"


def test_build_plan_dedupes_by_code():
    nodes = [
        _node("A01", "class", "农业"),
        _node("A01", "class", "农业；林业"),  # duplicate should be dropped
        _node("A01B", "subclass", "整地"),
    ]
    plan = build_ipc_plan(nodes)
    assert len(plan.nodes) == 2
    assert {n["code"] for n in plan.nodes} == {"A01", "A01B"}


def test_orphan_subgroup_without_parent_dropped():
    # A09B has no class node, so its parent edge is dropped (no invented node).
    nodes = [_node("A09B1/02", "subgroup", "x"), _node("A09B", "subclass", "y")]
    plan = build_ipc_plan(nodes)
    assert plan.nodes
