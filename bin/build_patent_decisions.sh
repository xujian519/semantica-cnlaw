#!/usr/bin/env bash
# 一键构建「专利复审无效决定」知识库管道（幂等，可重复/断点跑）：
#   0/6 转换        docx2decision_md   （从 2026 月度 zip 流式抽取 docx → 语料 md）
#   1/6 入库        load_decisions_neo4j（增量 MERGE，按 (case_number, decision_id) 去重）
#   2/6 建图        decision_citations  （决定 → 法条 Article 的 based_on 边）
#   3/6 建边        ipc_links           （决定/专利 → IPC 的 classified_in 边，幂等）
#   4/6 全量向量化  vectorize_decisions（文档级 bge-m3，独立 FAISS，断点续跑）
#   5/6 重启检索    重启 search_service（:8100，加载最新决定索引）
#
# 说明（本次实测）：2026 docx 表头已自带 法律依据/决定要点/案号 等全部管道字段，
# md 解析即达 ~100% 覆盖，故默认【不做 JSON 侧车】；仅当需要产出知识库 assets 时
# 用 --with-json-backfill（需先给 extract_invalidation_decisions.py 加参数化）。
#
# 用法:
#   bin/build_patent_decisions.sh --month 202601            # 试点单月
#   bin/build_patent_decisions.sh --months 202601,202602    # 批量
#   bin/build_patent_decisions.sh --month 202601 --limit 15 # 冒烟
#   bin/build_patent_decisions.sh --month 202601 --dry-run  # 只打印计划计数
#   bin/build_patent_decisions.sh --month 202601 --no-restart
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/bin/activate-env.sh"
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

DATA_ROOT="/Users/xujian/projects/宝宸知识库_Raw/无效复审决定"
MD_DIR="$DATA_ROOT/专利无效决定-2026-md"
DOWNLOAD_ROOT="/Users/xujian/Downloads/专利无效数据"

SEARCH_PORT="${SEARCH_PORT:-8100}"
MONTH=""
LIMIT=""
DRY_RUN=0
RESTART_SEARCH=1
WITH_JSON=0

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  echo
  echo "选项:"
  echo "  --month MM         处理单个月份（如 202601）；与 --months 二选一"
  echo "  --months A,B       批量处理多个月份（逗号分隔）"
  echo "  --limit N          只处理前 N 份（冒烟）"
  echo "  --dry-run          只打印计划计数，不写库/不向量化"
  echo "  --with-json-backfill 启用规则式 JSON 侧车（需先参数化 extract 脚本）"
  echo "  --no-restart       向量化后不重启检索服务"
  echo "  -h, --help         显示帮助"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --month) MONTH="$2"; shift 2 ;;
    --months) MONTHS="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --with-json-backfill) WITH_JSON=1; shift ;;
    --no-restart) RESTART_SEARCH=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "${MONTH:-}" && -z "${MONTHS:-}" ]]; then
  echo "需指定 --month 或 --months" >&2; usage; exit 1
fi
IFS=',' read -ra MONTH_LIST <<< "${MONTHS:-$MONTH}"

# Neo4j 就绪检查（load/建边依赖它，向量化不需要）
if ! lsof -tiTCP:7687 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⚠  Neo4j 未在 7687 监听，先启动它：bin/start-neo4j.sh" >&2
  exit 1
fi
if ! lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⚠  oMLX 嵌入服务未在 8000 监听，向量化会失败。请先启动 oMLX App。" >&2
  exit 1
fi

time_now() { date '+%H:%M:%S'; }
run() { echo "[$(time_now)] $1"; shift; "$@"; }

echo "==================== 开始构建专利复审无效决定知识库 ===================="

for m in "${MONTH_LIST[@]}"; do
  echo "==== 月份 ${m} ===="
  ZIP="$DOWNLOAD_ROOT/${m}/${m}.zip"
  if [[ ! -f "$ZIP" ]]; then
    echo "⚠  缺少压缩包：$ZIP，跳过" >&2
    continue
  fi

  if [[ "$DRY_RUN" == "0" ]]; then
    run "0/6 转换 ${m} -> $MD_DIR ..." \
      "$PY" -m cnlaw.ingest.docx2decision_md --input "$ZIP" --output "$MD_DIR" \
      ${LIMIT:+--limit "$LIMIT"}
  fi

  if [[ "$WITH_JSON" == "1" ]]; then
    echo "  [--with-json-backfill] 规则式 JSON 侧车生成（需先参数化 extract 脚本，占位）"
  fi

  run "1/6 入库 load_decisions_neo4j ..." \
    "$PY" -m cnlaw.ingest.load_decisions_neo4j --root "$MD_DIR" ${LIMIT:+--limit "$LIMIT"} \
    ${DRY_RUN:+--dry-run}

  run "2/6 建边 decision_citations（based_on）..." \
    "$PY" -m cnlaw.ingest.decision_citations --root "$MD_DIR" ${DRY_RUN:+--dry-run}
done

run "3/6 建边 ipc_links（classified_in）..." \
  "$PY" -m cnlaw.ingest.ipc_links ${DRY_RUN:+--dry-run}

if [[ "$DRY_RUN" == "0" ]]; then
  run "4/6 向量化 vectorize_decisions（断点续跑）..." \
    "$PY" -m cnlaw.ingest.vectorize_decisions --root "$MD_DIR" ${LIMIT:+--limit "$LIMIT"} \
    --faiss-path "$ROOT/data/vector_store/patent_decisions.faiss" \
    --meta-path "$ROOT/data/vector_meta/patent_decisions.json"
fi

if [[ "$RESTART_SEARCH" == "1" && "$DRY_RUN" == "0" ]]; then
  run "5/6 重启检索服务（:${SEARCH_PORT}）..." true
  PID="$(lsof -tiTCP:${SEARCH_PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$PID" ]]; then
    echo "  停止旧进程 pid=$PID"
    kill "$PID" 2>/dev/null || true
    sleep 2
  fi
  nohup "$ROOT/.venv/bin/uvicorn" cnlaw.ingest.search_service:app --port "$SEARCH_PORT" \
    > "$LOGDIR/search_service.log" 2>&1 &
  disown
  echo "  已启动检索服务 pid=$!，日志：$LOGDIR/search_service.log"
  ready=""
  for i in $(seq 1 40); do
    if curl -s "http://127.0.0.1:${SEARCH_PORT}/health" 2>/dev/null | grep -q '"decisions_ready":true'; then
      ready="yes"; break
    fi
    sleep 1
  done
  if [[ -n "$ready" ]]; then
    echo "  ✓ 检索服务就绪 decisions_ready=true"
  else
    echo "  ⚠ 40s 内未确认 decisions_ready，看日志：$LOGDIR/search_service.log" >&2
  fi
fi

echo "==================== 完成 ===================="
echo "已嵌入数量：$("$PY" -c "import json;print(len(json.load(open('$ROOT/data/vector_meta/patent_decisions.json')).get('ids',[])))" 2>/dev/null || echo '?')"
