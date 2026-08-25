"""Tests for the law SHACL constraints (cnlaw/ontology/law-shacl.ttl)."""

import pytest

from cnlaw.ingest.law_shacl import validate_law_graph

CONFORMING = """\
@prefix law: <https://cnlaw.dev/law#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://cnlaw.dev/law/doc/1> a law:LegalDocument ;
    law:status "现行有效" ;
    law:promulgated_date "1979-07-01"^^xsd:date ;
    law:legal_level "法律" ;
    law:has_article <https://cnlaw.dev/law/doc/1#a1> .

<https://cnlaw.dev/law/doc/1#a1> a law:Article ;
    law:number "第一条" .
"""


def test_conforming_graph_passes():
    report = validate_law_graph(CONFORMING)
    assert report.conforms is True
    assert report.violation_count == 0


def test_invalid_status_rejected():
    data = CONFORMING.replace('law:status "现行有效"', 'law:status "已失效"')
    report = validate_law_graph(data)
    assert report.conforms is False
    assert report.violation_count >= 1


def test_missing_promulgated_date_rejected():
    data = CONFORMING.replace('    law:promulgated_date "1979-07-01"^^xsd:date ;\n', "")
    report = validate_law_graph(data)
    assert report.conforms is False


def test_article_without_number_rejected():
    data = CONFORMING.replace('    law:number "第一条" .', "    .")
    report = validate_law_graph(data)
    assert report.conforms is False
