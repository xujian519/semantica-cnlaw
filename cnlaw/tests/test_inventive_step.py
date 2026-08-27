"""Tests for the inventive-step evidence orchestration (inventive_step.py).

Injects fake retrievers so the four-step bundle structure and citation plumbing
are verified without the resident search service, Neo4j, or oMLX. The real path
(real retrieval + graph based_on) is exercised by end-to-end verification.
"""

from cnlaw.ingest.inventive_step import build_inventive_bundle


def _dec(query, k, **kw):
    return [{
        "decision_id": "d0", "case_number": "5W000001", "invention_name": "一种锂电池负极材料",
        "legal_basis": "专利法第22条第3款", "source_path": "/tmp/dec.md", "text": "复审委认为……",
        "score": 0.9, "citation_verified": True,
    }]


def _law(query, k, **kw):
    return [{
        "full_name": "专利审查指南", "number": "第二部分第四章", "source_path": "/tmp/guide.md",
        "text": "发明……技术效果……", "score": 0.8, "citation_verified": True,
    }]


def _ground(article, **kw):
    return {"hits": [{
        "kind": "decision", "id": "d1", "case_number": "5W000002", "case_type": "无效",
        "decision_result": "维持专利权有效", "source_path": "/tmp/g.md",
        "law": "专利法", "article": "第22条第3款",
    }]}


def _retrievers():
    return {"search_decisions": _dec, "search_law": _law, "graph_ground": _ground}


def test_bundle_has_four_steps_sourced():
    bundle = build_inventive_bundle("一种锂电池负极材料", field="H01M", k=2, retrievers=_retrievers())
    steps = bundle["steps"]
    assert set(steps) == {"closest_prior_art", "distinguishing", "technical_problem", "inventive_step"}
    for name, step in steps.items():
        assert step["citations"], f"{name} 步无引用"
        assert all(c["source_path"] for c in step["citations"]), f"{name} 缺 source_path"
    # 每步引用都应可溯源（citation_verified 在判例路径为 True）
    for step in steps.values():
        for c in step["citations"]:
            if c["kind"].startswith("decision"):
                assert c["citation_verified"] is True


def test_bundle_carries_metadata():
    bundle = build_inventive_bundle("一种锂电池负极材料", field="H01M", k=2, retrievers=_retrievers())
    assert bundle["claim"] == "一种锂电池负极材料"
    assert bundle["field"] == "H01M"
    assert "第二部分第四章" in bundle["guide_basis"]
    assert bundle["analyze"] == "cnlaw_inventive_step"


def test_bundle_handles_empty_retrievals_gracefully():
    # Retrievers that return nothing must still yield a well-formed bundle with
    # empty (non-None) citation lists per step.
    empty = {
        "search_decisions": lambda q, k, **kw: [],
        "search_law": lambda q, k, **kw: [],
        "graph_ground": lambda article, **kw: {"hits": []},
    }
    bundle = build_inventive_bundle("一种锂电池负极材料", retrievers=empty)
    for step in bundle["steps"].values():
        assert step["citations"] == []


def test_ground_hits_accept_pydantic_model():
    # graph_api.ground returns a Pydantic GroundResponse (attribute access), NOT a
    # dict. Regression: the graph leg must resolve in production, not only under
    # the fake-retriever dict path.
    from types import SimpleNamespace

    from cnlaw.ingest.inventive_step import _ground_hits

    class _Resp:
        hits = [
            SimpleNamespace(kind="decision", id="g1", case_number="5W000003",
                            case_type="无效", decision_result="维持专利权有效",
                            law="专利法", article="第22条第3款", source_path="/tmp/g.md"),
        ]

    hits = _ground_hits(lambda **kw: _Resp(), "专利法第22条第3款", "H01M", 5)
    assert hits and hits[0]["case_number"] == "5W000003"
    assert hits[0]["source_path"] == "/tmp/g.md"
    assert "第22条第3款" in hits[0]["reference"]
