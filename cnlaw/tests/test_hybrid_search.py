"""Tests for the hybrid / rerank / citation additions in search_worker.

Covers the pure helpers (``_fuse_vids``, ``_citation_verifiable``) with no I/O
and the ``_query_precedent`` orchestration against a tiny fake backend + fake
reranker, so the dense-dominant, field-filter, cross-encoder reorder and
lexical-inclusion paths all work without touching the real FAISS index, the
BM25 pickle, or the oMLX server.
"""

from types import SimpleNamespace
from pathlib import Path

import numpy as np

from cnlaw.ingest import search_worker as sw


# +-- helpers ---------------------------------------------------------------

_FIELDS = {
    "decision_id": "decision_id", "case_number": "case_number",
    "case_type": "case_type", "decision_result": "decision_result",
    "legal_basis": "legal_basis", "ipc": "ipc",
    "source_path": "source_path", "text": "text",
}


def _backend(ids):
    """A (embedder, store) pair whose FAISS returns ids best-first, then -1 pad."""
    class _Emb:
        def embed_batch(self, texts):
            return np.ones((len(texts), 4), dtype=np.float32)

    class _Faiss:
        def search(self, _vec, k):
            n = min(k, len(ids))
            dist = [[float(n - i) for i in range(n)]]
            idx = [list(range(n)) + [-1] * (k - n)]
            return np.array(dist, dtype=np.float32), np.array(idx)

    store = SimpleNamespace(index=SimpleNamespace(index=_Faiss()))
    return _Emb(), store


def _meta():
    return {
        "d1": {"decision_id": "d1", "case_number": "c1", "case_type": "无效",
               "decision_result": "维持", "legal_basis": "专利法第22条第3款",
               "ipc": "H01M", "source_path": "/tmp/nonexistent_cnlaw", "text": "一"},
        "d2": {"decision_id": "d2", "case_number": "c2", "case_type": "无效",
               "decision_result": "无效", "legal_basis": "",
               "ipc": "H01M", "source_path": "", "text": "二"},
        "d3": {"decision_id": "d3", "case_number": "c3", "case_type": "复审",
               "decision_result": "维持", "legal_basis": "专利法第26条第4款",
               "ipc": "B05C", "source_path": "/tmp/nonexistent_cnlaw", "text": "三"},
        "d4": {"decision_id": "d4", "case_number": "c4", "case_type": "无效",
               "decision_result": "维持", "legal_basis": "专利法第22条第3款",
               "ipc": "H01M", "source_path": "/tmp/nonexistent_cnlaw", "text": "四"},
    }


def _run(k, ids, ground=None, rerank=False, reranker=None, corpus=None, monkeypatch=None):
    """Call _query_precedent against the fake backend + metadata."""
    backend = _backend(ids)
    return sw._query_precedent(
        "q", k, backend, ids_loader=lambda: ids, meta_loader=_meta, fields=_FIELDS,
        ground=ground, rerank=rerank, reranker=reranker, corpus=corpus)


# +-- RRF fuse --------------------------------------------------------------

def test_fuse_promotes_item_present_in_both_arms():
    # d1 ranks top in both -> must outrank d2 (dense-first) and d3 (lexical-first)
    out = sw._fuse_vids(["d1", "d2"], ["d3", "d1"], window=5)
    assert out[0] == "d1"
    assert set(out) == {"d1", "d2", "d3"}


def test_fuse_includes_lexical_only():
    out = sw._fuse_vids(["d1"], ["d2"], window=5)
    assert "d2" in out


def test_fuse_tie_breaks_to_dense_first():
    # Equal RRF score (both rank 0). Dense list is emitted first, so d2 leads.
    out = sw._fuse_vids(["d2"], ["d3"], window=5)
    assert out[0] == "d2"


# +-- citation_verified -----------------------------------------------------

def test_citation_min_verified_false_when_no_path():
    assert sw._citation_verifiable({"source_path": ""}) is False


def test_citation_verified_true_for_existing_file(tmp_path):
    f = tmp_path / "case.md"
    f.write_text("x", encoding="utf-8")
    assert sw._citation_verifiable({"source_path": str(f)}) is True


def test_citation_verified_relative_resolves_against_root(tmp_path):
    f = tmp_path / "sub" / "case.md"
    f.parent.mkdir()
    f.write_text("x", encoding="utf-8")
    assert sw._citation_verifiable({"source_path": "sub/case.md"}, source_root=str(tmp_path)) is True


# +-- _query_precedent orchestration ---------------------------------------

def test_precedent_field_filter_still_works():
    # ground=第22条第3款 -> only d1 survives (dense order, no rerank).
    hits = _run(k=5, ids=["d1", "d2", "d3"], ground="第22条第3款")
    assert [h["decision_id"] for h in hits] == ["d1"]
    assert hits[0]["citation_verified"] is False  # /tmp/nonexistent_cnlaw


def test_precedent_rerank_reorders_top_window():
    # A fake reranker that pushes d3 (score 1.0) above the dense-favored d1/d2.
    class _Rerank:
        def rerank(self, _query, candidates):
            return [(vid, 1.0 if vid == "d3" else 0.0) for vid, _ in candidates]

    hits = _run(k=3, ids=["d1", "d2", "d3"], rerank=True, reranker=_Rerank())
    assert hits[0]["decision_id"] == "d3"


def test_precedent_hybrid_includes_lexical_only(monkeypatch):
    # Lexical index "sees" a doc the dense window missed (d4); fusion pulls it in.
    def _fake_load(corpus):
        assert corpus == "decisions"
        return (["d4", "d3"], object())  # (ids, bm25) — bm25 unused because query is stubbed

    monkeypatch.setattr(sw, "_load_lexical", _fake_load)

    def _fake_lex_query(_bm25, _ids, _q, n):
        return [("d4", 3.0), ("d3", 2.0)]

    monkeypatch.setattr(sw.lexical_search, "query", _fake_lex_query)

    hits = _run(k=5, ids=["d1", "d2"], corpus="decisions", rerank=False)
    # d4 entered via the lexical arm even though it was never in the FAISS window.
    assert {h["decision_id"] for h in hits} >= {"d1", "d2", "d4"}


def test_precedent_rerank_skips_when_reranker_errors(monkeypatch):
    class _Bad:
        def rerank(self, _query, _candidates):
            raise RuntimeError("oMLX down")

    monkeypatch.setattr(sw, "log", SimpleNamespace(warning=lambda *a, **k: None))
    hits = _run(k=3, ids=["d1", "d2", "d3"], rerank=True, reranker=_Bad())
    # Fall-back keeps fused/dense order; result still returned with scores.
    assert len(hits) == 3
    assert all("score" in h for h in hits)
