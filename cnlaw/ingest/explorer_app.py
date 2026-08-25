"""Explorer app pre-loaded with the cnlaw legal graph (M4).

Run with: set -a && source .env && set +a && \
  ./.venv/bin/uvicorn cnlaw.ingest.explorer_app:app --host 0.0.0.0 --port 8001

Building the graph from Neo4j takes a few seconds at import time; the resulting
GraphSession is held on app.state so /api/graph/* serves the legal corpus.
"""

from __future__ import annotations

from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession

from .cnlaw_api import router as cnlaw_router
from .explorer_graph import build_law_context_graph


def build_session() -> GraphSession:
    return GraphSession(build_law_context_graph())


app = create_app(session=build_session())

# create_app() registers a SPA catch-all GET /{full_path:path} last, which would
# shadow any router added after it. Move the cnlaw router ahead of that catch-all
# so /api/cnlaw/* resolves (everything else still falls through to the catch-all).
_catchall = next(
    r for r in app.router.routes if getattr(r, "path", None) == "/{full_path:path}"
)
app.router.routes.remove(_catchall)
app.include_router(cnlaw_router)
app.router.routes.append(_catchall)
