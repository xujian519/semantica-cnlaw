"""Tests for search hit ranking (search_worker.py)."""

from cnlaw.ingest.search_worker import DOWNWEIGHT_REVISED, _rank_hits


def _hit(status, score, full_name="某法"):
    return {"status": status, "score": score, "full_name": full_name}


def test_rank_current_before_revised():
    hits = [
        _hit("已被修订", 0.95, "旧法"),
        _hit("现行有效", 0.40, "新法"),
    ]
    ranked = _rank_hits(hits, 2)
    assert [h["full_name"] for h in ranked] == ["新法", "旧法"]


def test_rank_orders_by_score_within_status():
    hits = [
        _hit("现行有效", 0.50, "甲"),
        _hit("现行有效", 0.70, "乙"),
    ]
    ranked = _rank_hits(hits, 2)
    assert [h["full_name"] for h in ranked] == ["乙", "甲"]


def test_rank_truncates_to_k():
    hits = [_hit("现行有效", s) for s in (0.9, 0.8, 0.7)]
    assert len(_rank_hits(hits, 2)) == 2


def test_rank_keeps_revised_but_never_outranks_current():
    # 多个被修订高分也被现行有效低压住
    hits = [
        _hit("已被修订", 0.98, "旧一"),
        _hit("已被修订", 0.96, "旧二"),
        _hit("现行有效", 0.30, "新"),
    ]
    ranked = _rank_hits(hits, 3)
    assert ranked[0]["full_name"] == "新"
    assert [h["full_name"] for h in ranked[1:]] == ["旧一", "旧二"]


def test_downweight_revised_constant():
    assert isinstance(DOWNWEIGHT_REVISED, float)
    assert 0.0 < DOWNWEIGHT_REVISED < 1.0
