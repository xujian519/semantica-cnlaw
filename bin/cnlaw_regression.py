#!/usr/bin/env python3
"""Live semantic-search regression over the cnlaw corpus.

Hits the resident search service (default 127.0.0.1:8100). Semantic cases are
scored by whether any expected keyword lands in a Top-k hit; robustness cases
only assert the API does not error and returns well-formed hits.

Run:  ./.venv/bin/python bin/cnlaw_regression.py [--service URL] [--k K]
"""
from __future__ import annotations

import argparse

import httpx

# (query, expected keywords) — any keyword present in full_name/text counts.
SEMANTIC_CASES = [
    ("判断发明是否具备创造性", ["创造性", "新颖性", "实用性"]),
    ("注册商标被驳回后如何申请复审救济", ["驳回", "复审", "商标评审"]),
    ("劳动合同解除后公司需要赔偿吗", ["解除劳动合同", "经济补偿", "赔偿", "违法解除"]),
    ("员工工作中受伤算不算工伤", ["工伤", "工伤保险", "职业病"]),
    ("夫妻共同财产在离婚时如何分割", ["夫妻共同财产", "离婚", "分割", "共同财产"]),
    ("公司注册资本是实缴还是认缴", ["注册资本", "认缴", "实缴", "出资", "股东"]),
    ("买到缺陷产品造成损害能否索赔", ["缺陷产品", "产品责任", "赔偿", "消费者"]),
    ("著作权侵权如何认定", ["著作权", "侵权", "复制", "作品"]),
    ("不服行政拘留决定可以起诉吗", ["行政拘留", "行政诉讼", "起诉", "行政复议"]),
    ("环境污染给他人造成损失谁承担赔偿责任", ["环境污染", "污染", "赔偿责任", "侵权"]),
    ("合同违约的违约金如何约定", ["违约金", "违约责任", "合同解除", "损失赔偿"]),
    ("发明专利的保护期限是多少年", ["保护期限", "二十年", "专利权", "专利法"]),
]

# (query, expected keywords, k, note) — robustness: must not error, must be well-formed.
ROBUSTNESS_CASES = [
    ("qqzzxx 无意义乱序词组", [], 3, "空结果/无关词"),
    ("侵权", ["侵权", "损害", "责任"], 3, "两字短查询"),
    ("债", ["债", "债权", "债务"], 3, "单字查询"),
    ("专利法 2020 修改", ["专利法"], 3, "带日期版本"),
    ("保障人民群众合法权益促进社会公平正义维护国家法治统一…" * 6, [], 3, "超长查询"),
    ("劳动合同", [], 20, "k 超出"),
]


def hit_ok(hit, keywords) -> bool:
    blob = hit.get("full_name", "") + " " + hit.get("text", "")
    return any(kw in blob for kw in keywords)


def fetch(service, query, k) -> list:
    r = httpx.get(f"{service}/search", params={"q": query, "k": k}, timeout=90, trust_env=False)
    r.raise_for_status()
    hits = r.json().get("results", [])
    for h in hits:  # 校验六个字段齐全
        for field in ("full_name", "source_date", "number", "text", "status", "score"):
            if field not in h:
                raise AssertionError(f"missing field {field}")
    return hits


def run_semantic(service, query, kws, k) -> tuple[str, int, list[str], str | None]:
    try:
        hits = fetch(service, query, k)
    except Exception as e:
        return query, 0, [], f"error: {e}"
    matched = sum(int(hit_ok(h, kws)) for h in hits)
    lines = [f"    [{h['score']:.3f}]{'★' if hit_ok(h, kws) else ' '} {h['full_name']} {h['number']} | {h['text'][:32]}…" for h in hits]
    return query, matched, lines, None


def run_robustness(service, query, kws, k, note) -> tuple[str, int, list[str], str | None]:
    try:
        hits = fetch(service, query, k)
    except Exception as e:
        return query, 0, [], f"error: {e}"
    # 鲁棒性：不崩即可；若给了关键词，顺带看是否命中相关
    matched = sum(int(hit_ok(h, kws)) for h in hits) if kws else len(hits)
    lines = [f"    [{h['score']:.3f}] {h['full_name']} {h['number']} | {h['text'][:32]}…" for h in hits[:3]]
    return f"{query}  (边界·{note})", matched, lines, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", default="http://127.0.0.1:8100")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--no-robustness", action="store_true")
    args = ap.parse_args()
    k = args.k

    tot, matched = 0, 0
    print(f"═══ 语义检索回归（service={args.service}, k={k}）═══")
    for query, kws in SEMANTIC_CASES:
        q, m, lines, err = run_semantic(args.service, query, kws, k)
        if err:
            print(f"❌ {q} -> {err}")
            continue
        tot += k
        matched += m
        print(f"\n■ {q}  (命中 {m}/{k}):")
        print("\n".join(lines))
    print(f"\n════ 语义域汇总: Top-{k} 命中 {matched}/{tot} ({matched / tot:.0%}) ════")

    if not args.no_robustness:
        print(f"\n═══ 边界用例（不崩 + 结构完整）═══")
        for query, kws, rk, note in ROBUSTNESS_CASES:
            q, m, lines, err = run_robustness(args.service, query, kws, rk, note)
            if err:
                print(f"❌ {q} -> {err}")
            else:
                print(f"\n■ {q}  (ok, 返回 {m} 命中):")
                print("\n".join(lines))


if __name__ == "__main__":
    main()
