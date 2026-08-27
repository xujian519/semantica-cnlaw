"""Validate patent decision RDF data against the decision SHACL constraints.

Wraps Semantica's OntologyEngine.validate_graph so the decision corpus can be
checked against cnlaw/ontology/decision-shacl.ttl (PySHACL-backed) before and
after import.
"""

from __future__ import annotations

from pathlib import Path

from semantica.ontology.engine import OntologyEngine

_DECISION_SHACL = Path(__file__).resolve().parents[1] / "ontology" / "decision-shacl.ttl"


def validate_decision_graph(data_graph, shacl=None):
    """Validate an RDF data graph against the decision SHACL shapes.

    Args:
        data_graph: RDF string or rdflib.Graph to validate.
        shacl: Optional override path to a SHACL file (defaults to decision-shacl.ttl).

    Returns:
        semantica.ontology.ontology_validator.SHACLValidationReport.
    """
    engine = OntologyEngine()
    return engine.validate_graph(data_graph, shacl=shacl or _DECISION_SHACL)
