"""Launch the cnlaw MCP server while forcing the pypi ``mcp`` SDK.

The repo root also carries a package named ``mcp`` (Semantica's own MCP server),
which would shadow the pypi SDK when the project dir is first on ``sys.path``.
This launcher drops the project dir from the front of ``sys.path`` so
``import mcp`` resolves to site-packages, then re-appends it (last) so
``cnlaw.ingest`` remains importable.

Spawn with: /path/.venv/bin/python /path/cnlaw_mcp_launcher.py
"""

import os
import sys

_project = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or ".") != _project] + [_project]

# Only the pypi SDK exposes ``mcp.server.mcpserver.MCPServer``; the repo-root
# Semantica ``mcp`` package does not. Fail loudly here rather than silently
# binding the wrong ``mcp`` if a future sys.path / packaging change defeats the
# reordering above.
try:
    from mcp.server.mcpserver import MCPServer  # noqa: E402, F401
except ImportError as exc:
    raise SystemExit(
        "无法加载 pypi mcp SDK：`import mcp` 解析到了项目根 Semantica 自带的 mcp/ 包，"
        "而非 site-packages 的 pypi SDK。请经 cnlaw_mcp_launcher.py 启动，或核对 sys.path 排布。"
    ) from exc
from cnlaw.ingest import cnlaw_mcp  # noqa: E402

if __name__ == "__main__":
    cnlaw_mcp.main()
