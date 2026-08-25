"""Tests for M3 vectorization planning helpers (vectorize_articles.py)."""

import json

from cnlaw.ingest.vectorize_articles import (
    build_metadata,
    chunk,
    dedupe_by_id,
    load_done_ids,
    make_id,
)


def _rec(**overrides):
    base = {
        "full_name": "中华人民共和国刑法",
        "source_date": "2020-12-26",
        "number": "第一条",
        "text": "为了惩罚犯罪…",
        "category": "刑法",
        "status": "现行有效",
    }
    base.update(overrides)
    return base


def test_make_id_stable_and_unique():
    assert make_id(_rec()) == "中华人民共和国刑法@2020-12-26~第一条"
    assert make_id(_rec(number="第二条")) != make_id(_rec(number="第一条"))


def test_make_id_handles_missing_source_date():
    assert make_id(_rec(source_date=None)) == "中华人民共和国刑法@~第一条"


def test_build_metadata_keeps_fields():
    meta = build_metadata(_rec())
    assert set(meta) == {"full_name", "source_date", "number", "category", "status"}
    assert meta["number"] == "第一条"


def test_chunk_sizes():
    rows = list(range(5))
    assert [list(b) for b in chunk(rows, 2)] == [[0, 1], [2, 3], [4]]
    assert [list(b) for b in chunk([], 2)] == []


def test_dedupe_by_id():
    rows = [_rec(), _rec(), _rec(number="第二条")]
    dedup = dedupe_by_id(rows)
    assert len(dedup) == 2  # 同 id 的重复只留一个


def test_load_done_ids_from_sidecar(tmp_path):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({"done": ["a", "b"]}), encoding="utf-8")
    assert load_done_ids(p) == {"a", "b"}


def test_load_done_ids_missing_file(tmp_path):
    assert load_done_ids(tmp_path / "none.json") == set()
