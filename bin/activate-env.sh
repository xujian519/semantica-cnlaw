#!/usr/bin/env bash
# 加载 semantica-cnlaw 本地中文环境变量
#   用法:  source bin/activate-env.sh
set -a
source "$(dirname "$0")/../.env"
set +a

# 便捷别名
if command -v cypher-shell >/dev/null 2>&1; then
  alias neo4j-shell='cypher-shell -a bolt://localhost:7687 -u neo4j -p "$GRAPH_STORE_NEO4J_PASSWORD"'
fi
echo "✓ 已加载 semantica-cnlaw 环境（Neo4j: ${GRAPH_STORE_NEO4J_URI}, Ollama: ${OLLAMA_HOST}）"
