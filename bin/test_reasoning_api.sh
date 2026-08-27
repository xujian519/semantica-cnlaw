#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# cnlaw 前向链式推理 /api/reason 联通性测试脚本
# 模板覆盖两类：图谱连接推理 + 专利法律要件推理，全部使用中文谓词与 ? 变量。
#
# 用法:
#   ./bin/test_reasoning_api.sh
#   BASE_URL=http://localhost:8001 ./bin/test_reasoning_api.sh
# 依赖: curl + python3（解析 JSON，避免依赖 jq）
# -----------------------------------------------------------------------------
set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8001}"
PY="${PY:-python3}"
ENDPOINT="$BASE_URL/api/reason"

PASS=0
FAIL=0

# 提取 inferred_facts 数组，逐行打印
facts_of() {
  "$PY" -c 'import json,sys; d=json.load(sys.stdin); print("\n".join(d.get("inferred_facts") or []))' 2>/dev/null
}

# run <模板名> <期望子串> <facts_json> <rules_json>
run() {
  local name="$1" expect="$2" facts="$3" rules="$4"
  local resp body reason
  resp=$(curl -s --max-time 30 -X POST "$ENDPOINT" \
        -H 'Content-Type: application/json' \
        -d "{\"facts\":$facts,\"rules\":$rules,\"mode\":\"forward\",\"apply_to_graph\":false}")
  body=$(printf '%s' "$resp" | facts_of)
  if printf '%s' "$body" | grep -qF "$expect"; then
    PASS=$((PASS+1))
    printf '  [PASS] %s -> 推出: %s\n' "$name" "$(printf '%s' "$body" | tr '\n' ';')"
  else
    FAIL=$((FAIL+1))
    reason=$(printf '%s' "$resp" | "$PY" -c 'import json,sys;d=json.load(sys.stdin);print(d.get("detail") or d.get("message") or "空结果")' 2>/dev/null || echo "无结果/请求失败")
    printf '  [FAIL] %s  未推出 %s (原因: %s)\n' "$name" "'$expect'" "$(printf '%s' "$reason" | tr '\n' ' ')"
  fi
}

# -----------------------------------------------------------------------------
echo "==> 健康检查 $BASE_URL/health"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/health")
echo "    health HTTP $CODE"
if [ "$CODE" != "200" ]; then
  echo "    !! 服务不可用，请先启动:"
  echo "       set -a && source .env && set +a && ./.venv/bin/uvicorn cnlaw.ingest.explorer_app:app --host 0.0.0.0 --port 8001"
  exit 2
fi
echo

echo "==> 图谱连接推理"
echo "  ─ 模板 1: 判决按 IPC 技术领域归类"
run "G1 判决IPC归类" "relates_to(沪一中民五知初字第47号" \
  '["involves(沪一中民五知初字第47号, 200480001590.4)","classified_in(200480001590.4, H04Q)"]' \
  '["IF involves(?J, ?P) AND classified_in(?P, ?IPC) THEN relates_to(?J, ?IPC)"]'

echo "  ─ 模板 2: 判决/决定依据条文 → 上位法律"
run "G2 追溯上位法" "applies_statute(4W113883" \
  '["based_on(4W113883, 第九十三条)","has_article(中华人民共和国立法法, 第九十三条)"]' \
  '["IF based_on(?D, ?A) AND has_article(?L, ?A) THEN applies_statute(?D, ?L)"]'

echo "  ─ 模板 3: 法规沿革替代 → 现行依据"
run "G3 现行依据" "current_basis(〔2008〕民三终字第10号" \
  '["based_on(〔2008〕民三终字第10号, 专利法2008第二十二条)","has_article(中华人民共和国专利法2008, 专利法2008第二十二条)","supersedes(中华人民共和国专利法2020, 中华人民共和国专利法2008)"]' \
  '["IF based_on(?J, ?A) AND has_article(?O, ?A) AND supersedes(?N, ?O) THEN current_basis(?J, ?N)"]'
echo

echo "==> 专利法律要件推理"
echo "  ─ 模板 4: 创造性（三步法）"
run "L1 创造性" "inventive(对比文件1)" \
  '["closest_prior_art(对比文件1)","distinguishing_feature(对比文件1, 双轴驱动)","no_technical_hint(双轴驱动)"]' \
  '["IF closest_prior_art(?D) AND distinguishing_feature(?D, ?F) AND no_technical_hint(?F) THEN inventive(?D)"]'

echo "  ─ 模板 5: 新颖性（现有技术公开）"
run "L2 新颖性" "anticipation(CN202011111111.1" \
  '["discloses(对比文件1, 特征A)","claimed(CN202011111111.1, 特征A)"]' \
  '["IF discloses(?D, ?F) AND claimed(?P, ?F) THEN anticipation(?P, ?D)"]'

echo "  ─ 模板 6: 等同原则侵权"
run "L3 等同侵权" "equivalent_infringe(被控产品" \
  '["claim_means(权利要求1, 焊接)","product_means(被控产品, 螺栓)","substantially_same(焊接, 螺栓)"]' \
  '["IF claim_means(?C, ?M1) AND product_means(?X, ?M2) AND substantially_same(?M1, ?M2) THEN equivalent_infringe(?X, ?C)"]'
echo

echo "== 结果汇总: PASS=$PASS  FAIL=$FAIL (端点: $ENDPOINT)"
[ "$FAIL" -eq 0 ]
