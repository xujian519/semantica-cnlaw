"""Tests for the decision vectorizer (cnlaw/ingest/vectorize_decisions.py)."""

import numpy as np

from cnlaw.ingest.parse_decision import PatentDecision
from cnlaw.ingest.vectorize_decisions import (
    build_faiss_store,
    build_metadata,
    build_text,
    make_id,
    vectorize,
)


class FakeEmbedder:
    """Stub embedder returning a zero vector per input."""

    def embed_batch(self, texts):
        return np.zeros((len(list(texts)), 1024), dtype=np.float32)


def _decision(**kw):
    base = dict(decision_id="1", case_number="4W1", case_type="无效",
                decision_result="维持专利权有效", invention_name="一种装置",
                legal_basis="专利法第22条第3款", application_number="00807334.1",
                decision_points="区别技术特征……", full_text="决定正文……")
    base.update(kw)
    return PatentDecision(**base)


def test_make_id_and_text_and_meta():
    d = _decision()
    assert make_id(d) == "4W1::1"
    text = build_text(d)
    assert "发明名称：一种装置" in text
    assert "结论：维持专利权有效" in text
    assert "决定要点：区别技术特征……" in text
    assert "决定正文……" in text
    meta = build_metadata(d)
    assert meta["text"] == text
    assert meta["domain"] == "专利复审无效"
    assert meta["application_number"] == "00807334.1"


def test_vectorize_and_resume(tmp_path):
    faiss_path = str(tmp_path / "dec.faiss")
    meta_path = str(tmp_path / "dec.json")
    store = build_faiss_store(faiss_path, meta_path)
    embedder = FakeEmbedder()

    rows = [_decision(decision_id=f"{i}", case_number=f"4W{i}", full_text=f"正文{i}") for i in range(5)]
    r1 = vectorize(rows, embedder, store, meta_path, faiss_path, batch_size=2)
    assert r1["new"] == 5
    assert r1["done"] == 5

    # resume: same rows again should not re-embed
    store2 = build_faiss_store(faiss_path, meta_path)
    r2 = vectorize(rows, embedder, store2, meta_path, faiss_path, batch_size=2)
    assert r2["new"] == 0
    assert r2["done"] == 5

    # a genuinely new row is embedded incrementally
    store3 = build_faiss_store(faiss_path, meta_path)
    rows_plus = rows + [_decision(decision_id="99", case_number="4W99", full_text="新正文")]
    r3 = vectorize(rows_plus, embedder, store3, meta_path, faiss_path, batch_size=2)
    assert r3["new"] == 1
    assert r3["done"] == 6
