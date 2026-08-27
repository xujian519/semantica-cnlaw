"""Tests for the IPC SHACL constraints (cnlaw/ontology/ipc-shacl.ttl)."""

from cnlaw.ingest.ipc_shacl import validate_ipc_graph

CONFORMING = """\
@prefix ipc: <https://cnlaw.dev/ipc#> .
@prefix dec: <https://cnlaw.dev/decision#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://cnlaw.dev/ipc/A01B1/02> a ipc:IpcNode ;
    ipc:code "A01B1/02" ;
    ipc:title "锹；铲" ;
    ipc:level "subgroup" ;
    ipc:version "2026.01" .

<https://cnlaw.dev/decision/1> a dec:PatentDecision ;
    dec:decision_id "566693" ;
    dec:case_type "无效" ;
    dec:decision_result "维持专利权有效" ;
    dec:domain "专利复审无效" ;
    ipc:classified_in <https://cnlaw.dev/ipc/A01B1/02> .
"""


def test_conforming_graph_passes():
    report = validate_ipc_graph(CONFORMING)
    assert report.conforms is True
    assert report.violation_count == 0


def test_missing_code_rejected():
    data = CONFORMING.replace('    ipc:code "A01B1/02" ;\n', "")
    report = validate_ipc_graph(data)
    assert report.conforms is False


def test_invalid_level_rejected():
    data = CONFORMING.replace('ipc:level "subgroup"', 'ipc:level "groupX"')
    report = validate_ipc_graph(data)
    assert report.conforms is False


def test_invalid_code_pattern_rejected():
    data = CONFORMING.replace('ipc:code "A01B1/02"', 'ipc:code "NOTANIPC"')
    report = validate_ipc_graph(data)
    assert report.conforms is False


def test_classified_in_target_must_be_ipc_node():
    data = CONFORMING.replace(
        "ipc:classified_in <https://cnlaw.dev/ipc/A01B1/02> .",
        "ipc:classified_in <https://cnlaw.dev/not-a-node> .",
    )
    report = validate_ipc_graph(data)
    assert report.conforms is False
