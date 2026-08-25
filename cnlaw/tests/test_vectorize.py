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
        "source_path": "/raw/刑法(2020-12-26).md",
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
    assert set(meta) == {"full_name", "source_date", "number", "category", "status", "text", "source_path"}
    assert meta["number"] == "第一条"
    assert meta["text"].startswith("为了惩罚犯罪")
    assert meta["source_path"] == "/raw/刑法(2020-12-26).md"


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


class _FakeIndex:
    def __init__(self, ids):
        self.vector_ids = list(ids)

    def save(self, path):
        self.saved = path


class _FakeStore:
    def __init__(self, ids):
        self.index = _FakeIndex(ids)


def test_persist_writes_meta_and_merges(tmp_path):
    from cnlaw.ingest.vectorize_articles import persist
    meta_path = tmp_path / "meta.json"
    faiss_path = tmp_path / "idx.faiss"
    store = _FakeStore(["a"])
    # 模拟断点续跑前已有的存量 meta
    meta_path.write_text(
        json.dumps({"ids": ["a"], "done": ["a"], "meta": {"a": {"number": "第a条"}}}),
        encoding="utf-8",
    )
    persist(store, meta_path, faiss_path, {"a", "b"}, {"b": {"number": "第b条", "text": "B正文"}})
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["meta"]["a"]["number"] == "第a条"   # 旧 meta 被合并保留
    assert data["meta"]["b"]["text"] == "B正文"      # 新增 meta 写入
    assert data["done"] == ["a", "b"]
    assert data["ids"] == ["a"]
    assert store.index.saved == str(faiss_path)


def test_backfill_meta_writes_text(tmp_path, monkeypatch):
    import cnlaw.ingest.vectorize_articles as va
    rows = [_rec(), _rec(number="第二条")]
    monkeypatch.setattr(va, "make_store", lambda: object())
    monkeypatch.setattr(va, "fetch_articles", lambda store, status=None: rows)
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps({"ids": [make_id(_rec()), make_id(_rec(number="第二条"))], "done": []}),
        encoding="utf-8",
    )
    result = va.backfill_meta(str(meta_path))
    assert result["articles"] == 2
    assert result["meta"] == 2
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["meta"][make_id(_rec())]["text"].startswith("为了惩罚犯罪")
    assert data["meta"][make_id(_rec())].get("status") == "现行有效"
