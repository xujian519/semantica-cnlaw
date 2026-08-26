"""Tests for the decision SHACL constraints (cnlaw/ontology/decision-shacl.ttl)."""

from cnlaw.ingest.decision_shacl import validate_decision_graph

CONFORMING = """\
@prefix dec: <https://cnlaw.dev/decision#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://cnlaw.dev/decision/1> a dec:PatentDecision ;
    dec:decision_id "566693" ;
    dec:case_type "无效" ;
    dec:decision_result "维持专利权有效" ;
    dec:decision_date "2024-01-29"^^xsd:date ;
    dec:domain "专利复审无效" ;
    dec:involves <https://cnlaw.dev/patent/1> .

<https://cnlaw.dev/patent/1> a dec:Patent ;
    dec:patent_number "00807334.1" .
"""


def test_conforming_graph_passes():
    report = validate_decision_graph(CONFORMING)
    assert report.conforms is True
    assert report.violation_count == 0


def test_invalid_case_type_rejected():
    data = CONFORMING.replace('dec:case_type "无效"', 'dec:case_type "驳回"')
    report = validate_decision_graph(data)
    assert report.conforms is False
    assert report.violation_count >= 1


def test_invalid_decision_result_rejected():
    data = CONFORMING.replace('dec:decision_result "维持专利权有效"', 'dec:decision_result "无效"')
    report = validate_decision_graph(data)
    assert report.conforms is False


def test_missing_decision_id_rejected():
    data = CONFORMING.replace('    dec:decision_id "566693" ;\n', "")
    report = validate_decision_graph(data)
    assert report.conforms is False


def test_wrong_domain_rejected():
    data = CONFORMING.replace('dec:domain "专利复审无效"', 'dec:domain "专利"')
    report = validate_decision_graph(data)
    assert report.conforms is False


def test_involves_must_be_patent():
    data = CONFORMING.replace(
        "dec:involves <https://cnlaw.dev/patent/1> .",
        "dec:involves <https://cnlaw.dev/not-a-patent> .",
    ).replace(
        "<https://cnlaw.dev/patent/1> a dec:Patent ;\n    dec:patent_number \"00807334.1\" .",
        "",
    )
    report = validate_decision_graph(data)
    assert report.conforms is False
