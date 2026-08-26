"""Tests for the judgment vectorization text / id composition."""

from cnlaw.ingest.parse_judgment import PatentJudgment
from cnlaw.ingest.vectorize_judgments import build_text, make_id


def _j(**kw):
    defaults = dict(case_number="(2012)民提字第1号", judgment_id="(2012)民提字第1号",
                    invention_name="后换档器支架", case_type="民事", cause="侵害发明专利权纠纷",
                    court="最高人民法院", decision_date="2012-12-11", application_number="94102612.4",
                    decision_result="驳回上诉，维持原判", decision_points="被诉产品是否落入保护范围",
                    legal_basis="《中华人民共和国专利法》第十一条", claims="1. 一种支架…",
                    full_text="本院认为……")
    defaults.update(kw)
    return PatentJudgment(**defaults)


def test_make_id_uses_case_number():
    assert make_id(_j()) == "(2012)民提字第1号"


def test_build_text_composes_core_fields():
    t = build_text(_j())
    assert "发明名称：后换档器支架" in t
    assert "案由：侵害发明专利权纠纷" in t
    assert "审理法院：最高人民法院" in t
    assert "专利号：94102612.4" in t
    assert "判决结果：驳回上诉，维持原判" in t
    assert "本院认为" in t


def test_build_text_capped_at_max():
    j = _j(full_text="长" * 20000)
    assert len(build_text(j)) <= 4000
