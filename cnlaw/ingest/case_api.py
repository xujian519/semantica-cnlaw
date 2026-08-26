"""Case-level decision-chain ledger for the patent mode (Stage D).

Records each step of a multi-step patent analysis (检索 -> 最接近现有技术 ->
区别特征 -> 实际解决的技术问题 -> 技术启示 -> 创造性结论 …) as a durable
``CaseDecision`` node in the cnlaw Neo4j graph, chained with ``:next`` edges, so
a whole case is a queryable, auditable decision chain. Durable across restarts
(unlike the in-memory generic ContextGraph), and consistent with the cnlaw graph
models. Endpoints, served from :8001, reuse the resident Neo4j store.

Endpoints
---------
``POST /api/cnlaw/case/{case_id}/decision``
    Append a decision step (auto-assigns ``step`` and links ``:next`` from the
    previous one).
``GET  /api/cnlaw/case/{case_id}``
    The case's decisions in step order.
``GET  /api/cnlaw/case/{case_id}/chain``
    The ordered causal chain (decision -> next).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .load_laws_neo4j import make_store
from .omlx_client import OmlxEmbedder
from .vectorize_cases import (DEFAULT_FAISS_PATH as CASES_FAISS_PATH,
                              DEFAULT_META_PATH as CASES_META_PATH,
                              build_faiss_store)

router = APIRouter(prefix="/api/cnlaw/case", tags=["case"])
_store_cache = None


def _get_store():
    global _store_cache
    if _store_cache is None:
        _store_cache = make_store()
    return _store_cache


class DecisionIn(BaseModel):
    category: str = ""
    scenario: str = ""
    reasoning: str = ""
    outcome: str = ""
    confidence: float = 0.5
    decision_maker: str = "patent-agent"
    entities: List[str] = []
    source_paths: List[str] = []
    title: Optional[str] = None  # case title, set on the case's first decision
    decision_id: Optional[str] = None


class DecisionOut(BaseModel):
    decision_id: str
    case_id: str
    step: int
    category: str = ""
    scenario: str = ""
    reasoning: str = ""
    outcome: str = ""
    confidence: float = 0.5
    decision_maker: str = ""
    entities: List[str] = []
    source_paths: List[str] = []
    created_at: str = ""


class ChainLink(BaseModel):
    decision_id: str
    step: int
    category: str = ""
    outcome: str = ""
    next_id: str = ""


class CaseOut(BaseModel):
    case_id: str
    title: str = ""
    status: str = ""
    decisions: List[DecisionOut]


class SimilarHit(BaseModel):
    decision_id: str
    case_id: str = ""
    category: str = ""
    outcome: str = ""
    reasoning: str = ""
    score: float = 0.0


class SimilarResponse(BaseModel):
    scenario: str
    hits: List[SimilarHit]


_cases_backend = None  # (embedder, store, ordered_ids, meta)


def _get_cases_backend():
    import json
    import os
    global _cases_backend
    if _cases_backend is None:
        store = build_faiss_store(CASES_FAISS_PATH, CASES_META_PATH)
        ids: List[str] = []
        meta: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(CASES_META_PATH):
            data = json.loads(open(CASES_META_PATH, encoding="utf-8").read())
            ids = data.get("ids", [])
            meta = data.get("meta", {})
        _cases_backend = (OmlxEmbedder(sub_batch=2, max_retries=5), store, ids, meta)
    return _cases_backend


@router.get("/similar", response_model=SimilarResponse)
def similar(scenario: str = Query(..., description="相似场景描述"),
            k: int = Query(8, ge=1, le=50)) -> SimilarResponse:
    if not scenario.strip():
        raise HTTPException(400, "scenario 必填")
    embedder, store, ids, meta = _get_cases_backend()
    if not store.index or not ids:
        raise HTTPException(503, "案件决策索引未构建，请先运行 vectorize_cases --rebuild")
    vec = embedder.embed_batch([scenario])
    distances, indices = store.index.index.search(vec, k)
    hits: List[SimilarHit] = []
    for j, i in enumerate(indices[0]):
        if i < 0:
            continue
        vid = ids[i]
        entry = meta.get(vid, {})
        hits.append(SimilarHit(
            decision_id=entry.get("decision_id") or vid,
            case_id=entry.get("case_id") or "",
            category=entry.get("category") or "",
            outcome=str(entry.get("outcome") or "")[:160],
            reasoning=str(entry.get("reasoning") or "")[:200],
            score=float(distances[0][j]),
        ))
    return SimilarResponse(scenario=scenario, hits=hits)


class ChainOut(BaseModel):
    case_id: str
    links: List[ChainLink]


def _row_to_decision(r: Dict[str, Any]) -> DecisionOut:
    def _list(v):
        return v or []
    return DecisionOut(
        decision_id=r.get("decision_id") or "",
        case_id=r.get("case_id") or "",
        step=int(r.get("step") or 0),
        category=r.get("category") or "",
        scenario=r.get("scenario") or "",
        reasoning=r.get("reasoning") or "",
        outcome=r.get("outcome") or "",
        confidence=float(r.get("confidence") or 0.0),
        decision_maker=r.get("decision_maker") or "",
        entities=_list(r.get("entities")),
        source_paths=_list(r.get("source_paths")),
        created_at=str(r.get("created_at") or ""),
    )


@router.post("/{case_id}/decision", response_model=DecisionOut)
def record_decision(case_id: str, body: DecisionIn) -> DecisionOut:
    if not body.category:
        raise HTTPException(400, "category 必填")
    store = _get_store()
    # Assign step = max(existing) + 1.
    recs = store.execute_query(
        "MATCH (c:Case {case_id:$case_id})-[:has_decision]->(d) RETURN max(d.step) AS m",
        {"case_id": case_id},
    ).get("records", [])
    step = int(recs[0]["m"] or 0) + 1 if recs else 1
    decision_id = body.decision_id or f"{case_id}-{step}"

    store.execute_query(
        "MERGE (c:Case {case_id:$case_id}) "
        "ON CREATE SET c.title=coalesce(nullif($title,''),''), c.status='open', c.created_at=datetime()"
        " ON MATCH SET c.title=coalesce(nullif($title,''), c.title) "
        "CREATE (d:CaseDecision {decision_id:$decision_id, case_id:$case_id, step:$step, "
        "  category:$category, scenario:$scenario, reasoning:$reasoning, outcome:$outcome, "
        "  confidence:$confidence, decision_maker:$decision_maker, entities:$entities, "
        "  source_paths:$source_paths, created_at:datetime()}) "
        "CREATE (c)-[:has_decision]->(d)",
        {"case_id": case_id, "title": body.title or "", "decision_id": decision_id, "step": step,
         "category": body.category, "scenario": body.scenario, "reasoning": body.reasoning,
         "outcome": body.outcome, "confidence": body.confidence,
         "decision_maker": body.decision_maker, "entities": body.entities,
         "source_paths": body.source_paths},
    )
    if step > 1:
        store.execute_query(
            "MATCH (c:Case {case_id:$case_id})-[:has_decision]->(p:CaseDecision) "
            "WHERE p.step=$prev "
            "MATCH (c)-[:has_decision]->(d:CaseDecision {decision_id:$decision_id}) "
            "CREATE (p)-[:next]->(d)",
            {"case_id": case_id, "prev": step - 1, "decision_id": decision_id},
        )

    return _row_to_decision({"decision_id": decision_id, "case_id": case_id, "step": step,
                             "category": body.category, "scenario": body.scenario,
                             "reasoning": body.reasoning, "outcome": body.outcome,
                             "confidence": body.confidence, "decision_maker": body.decision_maker,
                             "entities": body.entities, "source_paths": body.source_paths})


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str) -> CaseOut:
    store = _get_store()
    crecs = store.execute_query(
        "MATCH (c:Case {case_id:$case_id}) RETURN c.title AS title, c.status AS status",
        {"case_id": case_id},
    ).get("records", [])
    if not crecs:
        raise HTTPException(404, f"未找到案件 {case_id}")
    drecs = store.execute_query(
        "MATCH (c:Case {case_id:$case_id})-[:has_decision]->(d) "
        "RETURN d {.decision_id, .case_id, .step, .category, .scenario, .reasoning, .outcome, "
        ".confidence, .decision_maker, .entities, .source_paths, .created_at} AS d "
        "ORDER BY d.step",
        {"case_id": case_id},
    ).get("records", [])
    decisions = [_row_to_decision(r["d"]) for r in drecs if r.get("d")]
    return CaseOut(case_id=case_id, title=crecs[0]["title"] or "",
                   status=crecs[0]["status"] or "", decisions=decisions)


@router.get("/{case_id}/chain", response_model=ChainOut)
def get_chain(case_id: str) -> ChainOut:
    store = _get_store()
    recs = store.execute_query(
        "MATCH (c:Case {case_id:$case_id})-[:has_decision]->(d) "
        "OPTIONAL MATCH (d)-[:next]->(nx) "
        "RETURN d.decision_id AS decision_id, d.step AS step, d.category AS category, "
        "d.outcome AS outcome, nx.decision_id AS next_id ORDER BY d.step",
        {"case_id": case_id},
    ).get("records", [])
    links = [
        ChainLink(decision_id=r["decision_id"] or "", step=int(r["step"] or 0),
                  category=r["category"] or "", outcome=r["outcome"] or "",
                  next_id=r["next_id"] or "")
        for r in recs
    ]
    return ChainOut(case_id=case_id, links=links)
