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

import mcp  # noqa: E402, F401  now resolves to the pypi SDK
from cnlaw.ingest import cnlaw_mcp  # noqa: E402

if __name__ == "__main__":
    cnlaw_mcp.main()
