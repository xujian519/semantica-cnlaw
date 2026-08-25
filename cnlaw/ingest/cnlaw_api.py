"""cnlaw API router for the Explorer (semantic search over law articles)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .semantic_search import search_law

router = APIRouter(prefix="/api/cnlaw", tags=["cnlaw"])


class LawHit(BaseModel):
    full_name: str
    source_date: str
    number: str
    text: str
    status: str
    source_path: str
    score: float


class LawSearchResponse(BaseModel):
    query: str
    results: List[LawHit]


@router.get("/search", response_model=LawSearchResponse)
def law_search(q: str = Query(..., description="自然语言查询"), k: int = 8) -> LawSearchResponse:
    return LawSearchResponse(query=q, results=[LawHit(**hit) for hit in search_law(q, k)])
