"""Unit tests for the graph_api ``ground`` pagination (mock the Neo4j store)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cnlaw.ingest import graph_api
from cnlaw.ingest.graph_api import router


class FakeStore:
    """Minimal store doubling as a Cypher result source.

    Distinguishes count(*) queries from page queries by the query text and
    returns ``total_d`` / ``total_j`` virtual hit counts so pagination bounds
    and ``has_more`` can be asserted without a live Neo4j.
    """

    def __init__(self, total_d=0, total_j=0):
        self.total_d = total_d
        self.total_j = total_j
        self.last_params = None

    def execute_query(self, q, params):
        self.last_params = params
        if "count(DISTINCT d)" in q:
            return {"records": [{"n": self.total_d}]}
        if "count(DISTINCT j)" in q:
            return {"records": [{"n": self.total_j}]}
        is_jdg = "PatentJudgment" in q
        total = self.total_j if is_jdg else self.total_d
        n = max(0, min(params["k"], total - params["offset"]))
        base = {"case_number": "", "id": "", "case_type": "", "decision_result": "",
                "law": "", "article": "", "source_path": "", "source_file": "", "court": ""}
        return {"records": [dict(base) for _ in range(n)]}


@pytest.fixture
def client(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(graph_api, "_get_store", lambda: store)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), store


def test_ground_total_and_has_more(client):
    c, store = client
    store.total_d, store.total_j = 100, 40
    r = c.get("/api/cnlaw/graph/ground", params={"article": "专利法第22条第3款", "k": 30})
    body = r.json()
    assert body["total_decisions"] == 100
    assert body["total_judgments"] == 40
    assert len(body["hits"]) == 60  # 30 decisions + 30 judgments
    assert body["has_more"] is True


def test_ground_offset_skips(client):
    c, store = client
    store.total_d, store.total_j = 100, 40
    r = c.get("/api/cnlaw/graph/ground",
              params={"article": "专利法第22条第3款", "k": 30, "offset": 60})
    body = r.json()
    # decisions page: 30; judgments page: 0 (offset 60 > total_j = 40)
    assert len(body["hits"]) == 30
    assert all(h["kind"] == "decision" for h in body["hits"])
    assert body["has_more"] is True
    assert store.last_params["offset"] == 60


def test_ground_single_page_when_small(client):
    c, store = client
    store.total_d, store.total_j = 5, 3
    r = c.get("/api/cnlaw/graph/ground", params={"article": "专利法第二十二条第三款", "k": 30})
    body = r.json()
    assert body["total_decisions"] == 5
    assert body["total_judgments"] == 3
    assert len(body["hits"]) == 8
    assert body["has_more"] is False
    assert store.last_params["offset"] == 0


def test_ground_ipc_excludes_judgments(client):
    c, store = client
    store.total_d, store.total_j = 100, 40
    r = c.get("/api/cnlaw/graph/ground",
              params={"article": "专利法第22条第3款", "ipc": "B05C", "k": 30})
    body = r.json()
    assert body["total_decisions"] == 100
    assert body["total_judgments"] == 0
    assert len(body["hits"]) == 30
    assert all(h["kind"] == "decision" for h in body["hits"])


def test_ground_bad_article_400(client):
    c, _ = client
    r = c.get("/api/cnlaw/graph/ground", params={"article": "没有条号的引用"})
    assert r.status_code == 400
