"""Validate patent judgment RDF data against the judgment SHACL constraints.

Wraps Semantica's OntologyEngine.validate_graph so the judgment corpus can be
checked against cnlaw/ontology/judgment-shacl.ttl (PySHACL-backed) before and
after import.
"""

from __future__ import annotations

from pathlib import Path

from semantica.ontology.engine import OntologyEngine

_JUDGMENT_SHACL = Path(__file__).resolve().parents[1] / "ontology" / "judgment-shacl.ttl"


def validate_judgment_graph(data_graph, shacl=None):
    """Validate an RDF data graph against the judgment SHACL shapes.

    Args:
        data_graph: RDF string or rdflib.Graph to validate.
        shacl: Optional override path to a SHACL file (defaults to judgment-shacl.ttl).

    Returns:
        semantica.ontology.ontology_validator.SHACLValidationReport.
    """
    engine = OntologyEngine()
    return engine.validate_graph(data_graph, shacl=shacl or _JUDGMENT_SHACL)
