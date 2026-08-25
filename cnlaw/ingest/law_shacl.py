"""Validate legal RDF data against the cnlaw SHACL constraints.

Wraps Semantica's OntologyEngine.validate_graph so the corpus can be checked
against cnlaw/ontology/law-shacl.ttl (PySHACL-backed) before and after import.
"""

from __future__ import annotations

from pathlib import Path

from semantica.ontology.engine import OntologyEngine

_LAW_SHACL = Path(__file__).resolve().parents[1] / "ontology" / "law-shacl.ttl"


def validate_law_graph(data_graph, shacl=None):
    """Validate an RDF data graph against the law SHACL shapes.

    Args:
        data_graph: RDF string or rdflib.Graph to validate.
        shacl: Optional override path to a SHACL file (defaults to law-shacl.ttl).

    Returns:
        semantica.ontology.ontology_validator.SHACLValidationReport.
    """
    engine = OntologyEngine()
    return engine.validate_graph(data_graph, shacl=shacl or _LAW_SHACL)
