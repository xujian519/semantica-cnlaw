#!/usr/bin/env bash
# 以独立后台进程启动本机 Neo4j。
# 注意：brew services 因 openjdk@21 依赖而不可靠，故用 nohup + libexec/bin/neo4j。
set -e
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home}"
NEO4J_VER="$(ls /opt/homebrew/Cellar/neo4j | head -1)"
NEO4J_BIN=/opt/homebrew/opt/neo4j/libexec/bin/neo4j
NEO4J_HOME="/opt/homebrew/Cellar/neo4j/${NEO4J_VER}/libexec"

PID="$(lsof -tiTCP:7687 -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PID" ]; then
  echo "Neo4j 已在运行 (pid=$PID)"
  exit 0
fi

nohup env JAVA_HOME="$JAVA_HOME" NEO4J_HOME="$NEO4J_HOME" "$NEO4J_BIN" console \
  >/opt/homebrew/var/log/neo4j/neo4j-detached.log 2>&1 &
disown
echo "Neo4j 后台启动，等待 7687 就绪..."
for i in $(seq 1 20); do
  if lsof -iTCP:7687 -sTCP:LISTEN >/dev/null 2>&1; then echo "就绪 (http://localhost:7474)"; exit 0; fi
  sleep 3
done
echo "未在 60s 内就绪，请查看 /opt/homebrew/var/log/neo4j/neo4j-detached.log" >&2
exit 1
