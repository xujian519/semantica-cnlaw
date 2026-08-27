"""Resident semantic-search service (M4, step 2).

Runs in its own process so bge-m3 / torch load does not segfault the Explorer
uvicorn process, and keeps the model in memory so every query is fast after a
one-time cold start. Start it, then point the Explorer endpoint here.

Run with: ./.venv/bin/uvicorn cnlaw.ingest.search_service:app --port 8100
"""

from __future__ import annotations

import os

# Set before anything imports torch (via search_worker) to avoid the OpenMP
# thread-count segfault on macOS, and to use the Apple Silicon GPU.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("CNLAW_EMBED_DEVICE", "mps")

from typing import List

from fastapi import FastAPI, Query
from pydantic import BaseModel

from .search_worker import (
    Backend,
    load_backend,
    load_decision_backend,
    load_judgment_backend,
    query_decisions,
    query_with_backend,
    query_judgments,
)

app = FastAPI(title="cnlaw semantic search")
_backend: Backend | None = None
_decision_backend: Backend | None = None
_judgment_backend: Backend | None = None


class SemHit(BaseModel):
    full_name: str
    source_date: str
    number: str
    text: str
    status: str
    domain: str = ""
    category: str = ""
    tier: int = 0
    source_path: str
    score: float
    citation_verified: bool = False


class SemResponse(BaseModel):
    query: str
    results: List[SemHit]


class DecisionHit(BaseModel):
    decision_id: str
    case_number: str = ""
    case_type: str = ""
    decision_result: str = ""
    decision_points: str = ""
    legal_basis: str = ""
    application_number: str = ""
    invention_name: str = ""
    source_path: str = ""
    source_file: str = ""
    ipc: str = ""
    text: str
    score: float
    citation_verified: bool = False


class DecisionResponse(BaseModel):
    query: str
    results: List[DecisionHit]


class JudgmentHit(BaseModel):
    judgment_id: str
    case_number: str = ""
    case_type: str = ""
    cause: str = ""
    court: str = ""
    decision_result: str = ""
    legal_basis: str = ""
    invention_name: str = ""
    application_number: str = ""
    source_path: str = ""
    source_file: str = ""
    text: str
    score: float
    citation_verified: bool = False


class JudgmentResponse(BaseModel):
    query: str
    results: List[JudgmentHit]


@app.on_event("startup")
def _load_backend() -> None:
    global _backend, _decision_backend, _judgment_backend
    _backend = load_backend()
    _decision_backend = load_decision_backend()
    _judgment_backend = load_judgment_backend()


@app.get("/search", response_model=SemResponse)
def search(q: str = Query(...), k: int = 8,
           hybrid: bool = Query(True, description="dense+BM25 混合召回；false=纯语义")) -> SemResponse:
    if _backend is None:
        raise RuntimeError("backend not loaded")
    return SemResponse(query=q, results=[SemHit(**h) for h in query_with_backend(q, k, _backend, hybrid=hybrid)])


@app.get("/search/decisions", response_model=DecisionResponse)
def search_dec(q: str = Query(...), k: int = 8,
               ground: str | None = Query(None), ipc: str | None = Query(None),
               result: str | None = Query(None), case_type: str | None = Query(None),
               rerank: bool = Query(True, description="交叉编码重排；false=融合后原序")) -> DecisionResponse:
    if _decision_backend is None:
        raise RuntimeError("decision backend not loaded")
    return DecisionResponse(query=q, results=[DecisionHit(**h) for h in query_decisions(
        q, k, _decision_backend, ground=ground, ipc=ipc, result=result, case_type=case_type, rerank=rerank)])


@app.get("/search/judgments", response_model=JudgmentResponse)
def search_jug(q: str = Query(...), k: int = 8,
               ground: str | None = Query(None), ipc: str | None = Query(None),
               result: str | None = Query(None), case_type: str | None = Query(None),
               rerank: bool = Query(True, description="交叉编码重排；false=融合后原序")) -> JudgmentResponse:
    if _judgment_backend is None:
        raise RuntimeError("judgment backend not loaded")
    return JudgmentResponse(query=q, results=[JudgmentHit(**h) for h in query_judgments(
        q, k, _judgment_backend, ground=ground, ipc=ipc, result=result, case_type=case_type, rerank=rerank)])


@app.get("/health")
def health() -> dict:
    return {
        "ready": _backend is not None,
        "decisions_ready": _decision_backend is not None,
        "judgments_ready": _judgment_backend is not None,
    }
