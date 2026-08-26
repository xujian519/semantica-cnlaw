#!/usr/bin/env bash
# 一键构建「IPC 国际专利分类」管道（幂等，可重复/断点跑）：
#   1/2 入库   load_ipc_neo4j   （解析 8 部分类表，MERGE IpcNode + parent 边）
#   2/2 建边   ipc_links        （决定/专利 → IPC 的 classified_in 边）
#
# IPC 是结构数据，不参与向量化；分类浏览 API 运行时直查 Neo4j，无需重启检索服务。
# Explorer 知识图谱画布在导入时构建，如需在画布看到 IPC 节点，请用 --restart-explorer。
#
# 用法:
#   bin/build_ipc.sh                     # 全量
#   bin/build_ipc.sh --dry-run           # 只打印计划计数
#   bin/build_ipc.sh --restart-explorer  # 完成后重启 Explorer（重载含 IPC 的画布）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/bin/activate-env.sh"
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

DRY_RUN=""
RESTART_EXPLORER=0
EXPLORER_PORT="${EXPLORER_PORT:-8001}"

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  echo
  echo "选项:"
  echo "  --dry-run           只打印计划计数，不写库"
  echo "  --restart-explorer  完成后重启 Explorer（:${EXPLORER_PORT}）以重载画布"
  echo "  -h, --help          显示帮助"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --restart-explorer) RESTART_EXPLORER=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

if ! lsof -tiTCP:7687 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⚠  Neo4j 未在 7687 监听，先启动它：bin/start-neo4j.sh" >&2
  exit 1
fi

time_now() { date '+%H:%M:%S'; }
run() { echo "[$(time_now)] $1"; shift; "$@"; }

echo "==================== 开始构建 IPC 分类知识库 ===================="

run "1/2 入库 load_ipc_neo4j ..." \
  "$PY" -m cnlaw.ingest.load_ipc_neo4j $DRY_RUN

run "2/2 建边 ipc_links（classified_in）..." \
  "$PY" -m cnlaw.ingest.ipc_links $DRY_RUN

if [[ "$RESTART_EXPLORER" == "1" ]]; then
  run "重启 Explorer（:${EXPLORER_PORT}）加载含 IPC 的画布..." true
  PID="$(lsof -tiTCP:${EXPLORER_PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$PID" ]]; then
    echo "  停止旧进程 pid=$PID"
    kill "$PID" 2>/dev/null || true
    sleep 2
  fi
  nohup "$ROOT/.venv/bin/uvicorn" cnlaw.ingest.explorer_app:app --host 0.0.0.0 --port "$EXPLORER_PORT" \
    > "$LOGDIR/explorer.log" 2>&1 &
  disown
  echo "  已启动 Explorer pid=$!，日志：$LOGDIR/explorer.log"
fi

echo "==================== 完成 ===================="
echo "IPC 节点：$("$PY" -c "from cnlaw.ingest.load_laws_neo4j import make_store; s=make_store(); print(s.execute_query('MATCH (n:IpcNode) RETURN count(n) AS c')['records'][0]['c'])")"
