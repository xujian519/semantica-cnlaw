"""Explorer app pre-loaded with the cnlaw legal graph (M4).

Run with: set -a && source .env && set +a && \
  ./.venv/bin/uvicorn cnlaw.ingest.explorer_app:app --host 0.0.0.0 --port 8001

Building the graph from Neo4j takes a few seconds at import time; the resulting
GraphSession is held on app.state so /api/graph/* serves the legal corpus.
"""

from __future__ import annotations

import os

from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession

from .case_api import router as case_router
from .cnlaw_api import router as cnlaw_router
from .explorer_graph import build_law_context_graph
from .graph_api import router as graph_router
from .ipc_api import router as ipc_router

# Cap how many per-hub edges the canvas loads so its hub-star clusters stay
# interactive (see explorer_graph._HUB_SIDE). ``0`` disables the cap = full graph.
_GRAPH_MAX_EDGES_PER_HUB = int(os.environ.get("CNLAW_GRAPH_MAX_EDGES_PER_HUB", "80"))


def build_session() -> GraphSession:
    return GraphSession(
        build_law_context_graph(max_edges_per_hub=_GRAPH_MAX_EDGES_PER_HUB)
    )


app = create_app(session=build_session())

# create_app() registers a SPA catch-all GET /{full_path:path} last, which would
# shadow any router added after it. Move the cnlaw router ahead of that catch-all
# so /api/cnlaw/* resolves (everything else still falls through to the catch-all).
_catchall = next(
    r for r in app.router.routes if getattr(r, "path", None) == "/{full_path:path}"
)
app.router.routes.remove(_catchall)
app.include_router(cnlaw_router)
app.include_router(ipc_router)
app.include_router(graph_router)
app.include_router(case_router)
app.router.routes.append(_catchall)
