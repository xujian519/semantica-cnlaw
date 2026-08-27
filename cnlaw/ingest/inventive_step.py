"""Inventive-step (创造性三步法) evidence orchestration.

Given a technical solution (+ optional IPC field), assemble a *sourced* evidence
bundle for the three-step inventive-step analysis of 《专利审查指南》第二部分第四章:

    1. closest_prior_art  最接近的现有技术 (D1)
    2. distinguishing     区别特征
    3. technical_problem  实际解决的技术问题
    4. inventive_step     有无技术启示 (维持 vs 无效 对比)

Every item carries a reproducible citation — the precedent/guideline `source_path`
plus the cited 法条/指南 reference — so an agent can compose an auditable
argument instead of guessing. All retrieval *reuses* the resident search
service (:8100, semantic) and the graph API (based_on / involves / classified_in
via Neo4j); no new ingestion. The function takes injectable retrievers so it
stays unit-testable offline and the real path is exercised by the caller.

Endpoints surfaced from here: ``GET /api/cnlaw/workflow/inventive-step`` and the
``cnlaw_inventive_step`` MCP tool (see cnlaw_api / cnlaw_mcp).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# 《专利审查指南》第二部分第四章的经度：本模块把每一步的检索都指向它的判定标准。
_STEP_GUIDE = {
    "closest_prior_art": "最接近的现有技术——与发明技术领域相同或相近、公开技术特征最多",
    "distinguishing": "区别技术特征——发明与最接近现有技术相比不同的特征，产生什么技术效果",
    "technical_problem": "实际解决的技术问题——基于区别特征所能达到的技术效果重述",
    "inventive_step": "技术启示——现有技术整体上是否给出将区别特征应用到最接近现有技术的启示",
}


def _to_citation(hit: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Normalize a retrieval hit into a compact, citable evidence object."""
    return {
        "kind": kind,
        "id": (hit.get("decision_id") or hit.get("judgment_id") or hit.get("full_name") or "")[:80],
        "case_number": (hit.get("case_number") or "")[:40],
        "title": (hit.get("invention_name") or hit.get("full_name") or "")[:80],
        "reference": (hit.get("legal_basis") or hit.get("number") or "")[:80],
        "score": round(float(hit.get("score") or 0.0), 4),
        "citation_verified": bool(hit.get("citation_verified")),
        "source_path": hit.get("source_path") or "",
        "excerpt": (hit.get("text") or "")[:200],
    }


def _citations(hits: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    out = []
    for h in hits or []:
        c = _to_citation(h, kind)
        if c["source_path"] or c["reference"]:
            out.append(c)
    return out


def _default_retrievers() -> Dict[str, Callable[..., Any]]:
    from .graph_api import ground as graph_ground
    from .semantic_search import search_decisions, search_judgments, search_law
    return {
        "search_decisions": search_decisions,
        "search_judgments": search_judgments,
        "search_law": search_law,
        "graph_ground": graph_ground,
    }


def _ground_hits(ground_fn, article: str, field: str, k: int) -> List[Dict[str, Any]]:
    """Decisions/judgments citing ``article`` (via based_on), optionally IPC-restricted.

    ``graph_api.ground`` returns a Pydantic ``GroundResponse`` (attribute access);
    injectable fakes (tests) may return a plain dict. Read either form so the
    based_on citations resolve in production — previously only the dict path was
    exercised, which silently dropped the graph leg under the real endpoint.

    ``graph_api.ground`` is a FastAPI endpoint whose *every* parameter defaults
    to a ``Query(...)`` object, so it must be called with all params as plain
    values — omitting ``law``/``offset`` leaks a ``Query`` object into the Neo4j
    parameters (``ProcessingError``), which is exactly what made the graph leg go
    silent. Passing them explicitly avoids that while keeping the function pure.
    """
    def _rows(resp):
        if isinstance(resp, dict):
            return resp.get("hits", []) or []
        return getattr(resp, "hits", None) or []

    def _v(h, key):
        if isinstance(h, dict):
            return h.get(key, "") or ""
        return getattr(h, key, "") or ""

    try:
        resp = ground_fn(article=article, law=None, ipc=field or None, k=k, offset=0)
    except Exception:
        return []
    out = []
    for h in _rows(resp):
        ref = (_v(h, "law") + " " + _v(h, "article")).strip()
        out.append({
            "kind": _v(h, "kind"),
            "decision_id": _v(h, "id"), "case_number": _v(h, "case_number"),
            "case_type": _v(h, "case_type"), "decision_result": _v(h, "decision_result"),
            "source_path": _v(h, "source_path"),
            "reference": ref,
            "invention_name": "", "legal_basis": ref,
            "text": "", "score": 0.0,
        })
    return out


def build_inventive_bundle(claim: str, *, field: str = "", k: int = 5,
                           retrievers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assemble a four-step sourced evidence bundle for an inventive-step analysis.

    ``claim`` is a natural-language technical solution description (or field of
    the invention); ``field`` an optional IPC prefix to scope the precedent
    retrieval (e.g. ``H01M``). ``retrievers`` lets a caller inject fakes; when
    omitted, the real semantic + graph harness is used. The result is a dict of
    step objects, each with ``title``, ``note`` (the guideline standard), and a
    ``citations`` list; no LLM is involved — the agent composes the argument from
    these citations.
    """
    r = retrievers or _default_retrievers()
    guide = _STEP_GUIDE

    # Step 1 — D1 最接近的现有技术: 同领域、公开特征最多的现有技术.
    # Semantic over invalid/reexam decisions scoped to the invention's IP field.
    # (No invalidity-outcome filter — D1 is the closest existing technology,
    # independent of what the board ultimately concluded about any one case.)
    d1_hits = r["search_decisions"](
        f"{claim} 现有技术", k, ipc=field or None, rerank=True)

    # Step 2 — 区别特征: 复审委对相似发明的创造性认定. Substring-ground on 22.3
    # brings decisions where the board reasoned about distinguishing features.
    dist_hits = r["search_decisions"](
        f"{claim} 区别技术特征", k, ground="第22条第3款", ipc=field or None, rerank=True)

    # Step 3 — 实际解决的技术问题: 审查指南四章 + 判例的“技术问题”表述.
    tp_law = r["search_law"]("创造性 实际解决的技术问题 技术启示", k, hybrid=True)
    # graph based_on 22.3 for the statutory anchor.

    # Step 4 — 技术启示: 维持(有创造性) 与 无效(无创造性) 同领域对比.
    # 维持桶精确到「维持专利权有效」(子串匹配「维持」会连带「维持驳回决定」, 于申请人不
    # 利, 不应归入有创造性一侧); 无效桶为「宣告…无效」, 两侧 result 值天然互斥、不重叠.
    inv_hits = r["search_decisions"](
        f"{claim} 技术启示 显而易见", k, ground="第22条第3款", ipc=field or None,
        result="维持专利权有效", rerank=True)
    no_inv_hits = r["search_decisions"](
        f"{claim} 技术启示 显而易见", k, ground="第22条第3款", ipc=field or None,
        result="无效", rerank=True)

    # Graph evidence: who actually cites 22.3 in this field (based_on).
    graph_hits = _ground_hits(r["graph_ground"], "专利法第22条第3款", field, k)

    bundle: Dict[str, Any] = {
        "claim": claim,
        "field": field,
        "guide_basis": "《专利审查指南》第二部分第四章 3.2 (发明是否具备创造性)",
        "analyze": "cnlaw_inventive_step",
        "steps": {}
    }
    bundle["steps"]["closest_prior_art"] = {
        "title": "最接近的现有技术 (D1)", "note": guide["closest_prior_art"],
        "citations": _citations(d1_hits, "decision"),
    }
    bundle["steps"]["distinguishing"] = {
        "title": "区别技术特征", "note": guide["distinguishing"],
        "citations": _citations(dist_hits, "decision") + _citations(graph_hits, "graph"),
    }
    bundle["steps"]["technical_problem"] = {
        "title": "实际解决的技术问题", "note": guide["technical_problem"],
        "citations": _citations(tp_law, "law") + _citations(graph_hits, "graph"),
    }
    bundle["steps"]["inventive_step"] = {
        "title": "有无技术启示", "note": guide["inventive_step"],
        "citations": (
            _citations(inv_hits, "decision维持") +
            _citations(no_inv_hits, "decision无效") +
            _citations(graph_hits, "graph")
        ),
    }
    return bundle


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Inventive-step evidence bundle (from live services).")
    parser.add_argument("claim", help="技术方案描述")
    parser.add_argument("--field", default="", help="IPC 前缀（如 H01M）")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)
    import json
    bundle = build_inventive_bundle(args.claim, field=args.field, k=args.k)
    print(json.dumps(bundle, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
