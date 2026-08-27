"""Tests for the oMLX reranker client (rerank_client.py).

Stubs the HTTP layer (``OmlxReranker._post``) so the index->score mapping and
descending sort are verified without talking to the oMLX server. The real
network path is exercised by the end-to-end verification, not by unit tests.
"""

from cnlaw.ingest.rerank_client import OmlxReranker


def _reranker(response):
    r = OmlxReranker(base_url="http://127.0.0.1:8000")
    r._post = lambda payload: response
    return r


def test_rerank_maps_scores_by_index_and_sorts_desc():
    r = _reranker({
        "results": [
            {"index": 1, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.4},
            {"index": 2, "relevance_score": 0.99},
        ]
    })
    ranked = r.rerank("q", [("a", "A"), ("b", "B"), ("c", "C")])
    assert [vid for vid, _ in ranked] == ["c", "b", "a"]
    assert [sc for _, sc in ranked] == [0.99, 0.9, 0.4]


def test_rerank_empty_candidates_short_circuits():
    r = _reranker({"results": []})
    assert r.rerank("q", []) == []


def test_rerank_missing_index_treated_as_zero():
    # A result entry with an out-of-range index is ignored, mapped to 0.
    r = _reranker({"results": [{"index": 99, "relevance_score": 0.5}]})
    ranked = r.rerank("q", [("a", "A"), ("b", "B")])
    assert [sc for _, sc in ranked] == [0.0, 0.0]


def test_rerank_payload_posts_query_and_documents():
    captured = {}

    class _Reranker(OmlxReranker):
        def _post(self, payload):
            captured.update(payload)
            return {"results": [{"index": 0, "relevance_score": 1.0}]}

    r = _Reranker(base_url="http://127.0.0.1:8000")
    ranked = r.rerank("锂电池负极", [("a", "一种锂电池负极材料")])
    assert captured["query"] == "锂电池负极"
    assert captured["documents"] == ["一种锂电池负极材料"]
    assert len(ranked) == 1 and ranked[0][0] == "a"
