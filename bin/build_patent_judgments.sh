#!/usr/bin/env bash
# 一键构建「专利判决」知识库管道（幂等，可重复/断点跑）：
#   1/3 入库       load_judgments_neo4j   （增量 MERGE，不清库，按案号去重）
#   2/3 建图       judgment_citations     （判决 → 法条 Article 的 based_on 边）
#   3/3 全量向量化 vectorize_judgments     （文档级 bge-m3，独立 FAISS，断点续跑）
#   4   重启检索服务 search_service         （加载最新判决索引）
#
# 用法:
#   bin/build_patent_judgments.sh                     # 全量（夜间跑）
#   bin/build_patent_judgments.sh --limit 40          # 冒烟：只处理前 N 份
#   bin/build_patent_judgments.sh --clear             # 先删 PatentJudgment 子图再入库
#   bin/build_patent_judgments.sh --no-restart        # 向量化后不重启检索服务
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/bin/activate-env.sh"
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

SEARCH_PORT="${SEARCH_PORT:-8100}"
LIMIT=""
CLEAR_FLAG=""
RESTART_SEARCH=1

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
  echo
  echo "选项:"
  echo "  --limit N        只处理前 N 份（冒烟）"
  echo "  --clear          入库前先删除 PatentJudgment 子图（不影响共享的 Patent 节点）"
  echo "  --no-restart     向量化后不重启检索服务"
  echo "  -h, --help       显示帮助"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit) LIMIT="$2"; shift 2 ;;
    --clear) CLEAR_FLAG="--clear"; shift ;;
    --no-restart) RESTART_SEARCH=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

# Neo4j 就绪检查（load 依赖它，向量化不需要）
if ! lsof -tiTCP:7687 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⚠  Neo4j 未在 7687 监听，先启动它：bin/start-neo4j.sh" >&2
  exit 1
fi
if ! lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⚠  oMLX 嵌入服务未在 8000 监听，向量化会失败。请先启动 oMLX App。" >&2
  exit 1
fi

time_now() { date '+%H:%M:%S'; }
run() {
  echo "[$(time_now)] $1"
  shift
  "$@"
}

echo "==================== 开始构建专利判决知识库 ===================="

run "1/3 入库 load_judgments_neo4j ..." \
  "$PY" -m cnlaw.ingest.load_judgments_neo4j $CLEAR_FLAG ${LIMIT:+--limit "$LIMIT"}

run "2/3 建图 judgment_citations（based_on）..." \
  "$PY" -m cnlaw.ingest.judgment_citations

run "3/3 向量化 vectorize_judgments（断点续跑）..." \
  "$PY" -m cnlaw.ingest.vectorize_judgments ${LIMIT:+--limit "$LIMIT"} \
  --faiss-path "$ROOT/data/vector_store/patent_judgments.faiss" \
  --meta-path "$ROOT/data/vector_meta/patent_judgments.json"

if [[ "$RESTART_SEARCH" == "1" ]]; then
  run "4/4 重启检索服务（:${SEARCH_PORT}）..." true
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
    if curl -s "http://127.0.0.1:${SEARCH_PORT}/health" 2>/dev/null | grep -q '"judgments_ready":true'; then
      ready="yes"; break
    fi
    sleep 1
  done
  if [[ -n "$ready" ]]; then
    echo "  ✓ 检索服务就绪 judgments_ready=true"
  else
    echo "  ⚠ 40s 内未确认 judgments_ready，看日志：$LOGDIR/search_service.log" >&2
  fi
fi

echo "==================== 完成 ===================="
echo "已嵌入数量：$("$PY" -c "import json;print(len(json.load(open('$ROOT/data/vector_meta/patent_judgments.json')).get('ids',[])))")"
