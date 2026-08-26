"""Tests for the judgment SHACL constraints (cnlaw/ontology/judgment-shacl.ttl)."""

from cnlaw.ingest.judgment_shacl import validate_judgment_graph

CONFORMING = """\
@prefix dec: <https://cnlaw.dev/decision#> .
@prefix jg:   <https://cnlaw.dev/judgment#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://cnlaw.dev/judgment/1> a jg:PatentJudgment ;
    jg:judgment_id "(2011)民初字第1号" ;
    jg:case_type "民事" ;
    jg:domain "专利判决" ;
    jg:decision_date "2013-06-21"^^xsd:date ;
    jg:involves <https://cnlaw.dev/patent/1> .

<https://cnlaw.dev/patent/1> a dec:Patent ;
    dec:patent_number "200480001590.4" .
"""


def test_conforming_graph_passes():
    report = validate_judgment_graph(CONFORMING)
    assert report.conforms is True
    assert report.violation_count == 0


def test_invalid_case_type_rejected():
    data = CONFORMING.replace('jg:case_type "民事"', 'jg:case_type "刑事附带"')
    report = validate_judgment_graph(data)
    assert report.conforms is False
    assert report.violation_count >= 1


def test_missing_judgment_id_rejected():
    data = CONFORMING.replace('    jg:judgment_id "(2011)民初字第1号" ;\n', "")
    report = validate_judgment_graph(data)
    assert report.conforms is False


def test_wrong_domain_rejected():
    data = CONFORMING.replace('jg:domain "专利判决"', 'jg:domain "专利复审无效"')
    report = validate_judgment_graph(data)
    assert report.conforms is False


def test_involves_must_be_patent():
    data = CONFORMING.replace(
        "jg:involves <https://cnlaw.dev/patent/1> .",
        "jg:involves <https://cnlaw.dev/not-a-patent> .",
    ).replace(
        "<https://cnlaw.dev/patent/1> a dec:Patent ;\n    dec:patent_number \"200480001590.4\" .",
        "",
    )
    report = validate_judgment_graph(data)
    assert report.conforms is False
