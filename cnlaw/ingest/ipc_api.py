"""Neo4j-backed IPC classification browse / filter API for the Explorer.

Serves the IPC classification tree (section -> class -> subclass -> group ->
subgroup) and the patent reexamination/invalidation decisions classified under a
given IPC node. Unlike the semantic-search endpoints (which run in the resident
search_service against FAISS), these are structural queries answered directly
from Neo4j, so decisions are aggregated by IPC code prefix (the subtree of a
node is every code that starts with that node's code).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .load_laws_neo4j import make_store

router = APIRouter(prefix="/api/cnlaw/ipc", tags=["ipc"])
_store_cache = None


def _get_store():
    global _store_cache
    if _store_cache is None:
        _store_cache = make_store()
    return _store_cache


class IpcNodeOut(BaseModel):
    code: str
    title: str = ""
    level: str = ""
    decision_count: int = 0
    patent_count: int = 0
    has_children: bool = False


class IpcDecisionHit(BaseModel):
    decision_id: str
    case_number: str = ""
    case_type: str = ""
    decision_result: str = ""
    decision_points: str = ""
    application_number: str = ""
    invention_name: str = ""
    source_path: str = ""
    source_file: str = ""
    ipc: str = ""


class IpcDecisionResponse(BaseModel):
    code: str
    level: str
    title: str = ""
    results: List[IpcDecisionHit]


def _node(code: str) -> Optional[Dict[str, Any]]:
    recs = _get_store().execute_query(
        "MATCH (i:IpcNode {code:$code}) RETURN i.code AS code, i.title AS title, i.level AS level",
        {"code": code},
    ).get("records", [])
    return recs[0] if recs else None


def _counts(prefix: str) -> Dict[str, int]:
    """Decision / patent counts whose IPC code is in the ``prefix`` subtree."""
    q = _get_store().execute_query(
        "MATCH (d:PatentDecision)-[:classified_in]->(i:IpcNode) WHERE i.code STARTS WITH $p "
        "RETURN count(DISTINCT d) AS c",
        {"p": prefix},
    ).get("records", [])
    dec = q[0]["c"] if q else 0
    q = _get_store().execute_query(
        "MATCH (p:Patent)-[:classified_in]->(i:IpcNode) WHERE i.code STARTS WITH $p "
        "RETURN count(DISTINCT p) AS c",
        {"p": prefix},
    ).get("records", [])
    pat = q[0]["c"] if q else 0
    return {"decision_count": dec, "patent_count": pat}


def _has_children(code: str) -> bool:
    q = _get_store().execute_query(
        "MATCH (c:IpcNode)-[:parent]->(p:IpcNode {code:$code}) RETURN count(c) AS c",
        {"code": code},
    ).get("records", [])
    return bool(q and q[0]["c"])


def _children(code: str) -> List[Dict[str, Any]]:
    recs = _get_store().execute_query(
        "MATCH (c:IpcNode)-[:parent]->(p:IpcNode {code:$code}) "
        "RETURN c.code AS code, c.title AS title, c.level AS level ORDER BY c.code",
        {"code": code},
    ).get("records", [])
    return [{"code": r["code"], "title": r["title"] or "", "level": r["level"]} for r in recs]


def _to_node_out(node: Dict[str, Any]) -> IpcNodeOut:
    code, level, title = node["code"], node.get("level", ""), node.get("title", "")
    counts = _counts(code)
    return IpcNodeOut(
        code=code,
        title=title,
        level=level,
        decision_count=counts["decision_count"],
        patent_count=counts["patent_count"],
        has_children=_has_children(code),
    )


@router.get("/sections", response_model=List[IpcNodeOut])
def sections() -> List[IpcNodeOut]:
    """The eight top-level IPC sections."""
    recs = _get_store().execute_query(
        "MATCH (i:IpcNode) WHERE i.level='section' RETURN i.code AS code, i.title AS title, "
        "i.level AS level ORDER BY i.code"
    ).get("records", [])
    return [_to_node_out({"code": r["code"], "title": r["title"] or "", "level": r["level"]}) for r in recs]


@router.get("/tree", response_model=List[IpcNodeOut])
def tree(parent: str = Query(..., description="IPC code whose children to list")) -> List[IpcNodeOut]:
    """Children of an IPC node (for lazy expand of the browse tree)."""
    return [_to_node_out(n) for n in _children(parent)]


@router.get("/{code}/decisions", response_model=IpcDecisionResponse)
def decisions(code: str, k: int = Query(50, ge=1, le=200)) -> IpcDecisionResponse:
    """Decisions classified under an IPC node (including its descendants)."""
    node = _node(code)
    if node is None:
        raise HTTPException(status_code=404, detail=f"IPC 分类 {code} 不存在")
    recs = _get_store().execute_query(
        "MATCH (d:PatentDecision)-[:classified_in]->(i:IpcNode) "
        "WHERE i.code STARTS WITH $p "
        "WITH DISTINCT d "
        "RETURN d.decision_id AS decision_id, d.case_number AS case_number, "
        "d.case_type AS case_type, d.decision_result AS decision_result, "
        "d.decision_points AS decision_points, d.application_number AS application_number, "
        "d.invention_name AS invention_name, d.source_path AS source_path, "
        "d.source_file AS source_file, d.ipc AS ipc "
        "ORDER BY d.decision_date DESC LIMIT $k",
        {"p": code, "k": k},
    ).get("records", [])
    results = [
        IpcDecisionHit(
            decision_id=r["decision_id"] or "",
            case_number=r["case_number"] or "",
            case_type=r["case_type"] or "",
            decision_result=r["decision_result"] or "",
            decision_points=(r["decision_points"] or "")[:200],
            application_number=r["application_number"] or "",
            invention_name=r["invention_name"] or "",
            source_path=r["source_path"] or "",
            source_file=r["source_file"] or "",
            ipc=r["ipc"] or "",
        )
        for r in recs
    ]
    return IpcDecisionResponse(code=code, level=node["level"], title=node["title"] or "", results=results)
