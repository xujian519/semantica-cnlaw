"""Validate IPC classification RDF data against the IPC SHACL constraints.

Wraps Semantica's OntologyEngine.validate_graph so the IPC classification corpus
can be checked against cnlaw/ontology/ipc-shacl.ttl (PySHACL-backed).
"""

from __future__ import annotations

from pathlib import Path

from semantica.ontology.engine import OntologyEngine

_IPC_SHACL = Path(__file__).resolve().parents[1] / "ontology" / "ipc-shacl.ttl"


def validate_ipc_graph(data_graph, shacl=None):
    """Validate an RDF data graph against the IPC SHACL shapes.

    Args:
        data_graph: RDF string or rdflib.Graph to validate.
        shacl: Optional override path to a SHACL file (defaults to ipc-shacl.ttl).

    Returns:
        semantica.ontology.ontology_validator.SHACLValidationReport.
    """
    engine = OntologyEngine()
    return engine.validate_graph(data_graph, shacl=shacl or _IPC_SHACL)
