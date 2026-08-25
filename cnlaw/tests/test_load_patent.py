"""Tests for the patent corpus loader (cnlaw/ingest/load_patent.py)."""

import os
from pathlib import Path

import pytest

from cnlaw.ingest.load_patent import PATENT_DOMAIN, PATENT_ROOT, scan_patent_corpus

# 地方性法规 / 技术标准（应被排除，不应出现在专利语料清单中）
_EXCLUDED_NAMES = {
    "山东省专利纠纷行政裁决和行政调解办法",
    "山东省专利条例",
    "淄博市专利管理若干规定",
    "青岛市专利保护规定",
    "专利申请号标准",
}


@pytest.mark.skipif(not Path(PATENT_ROOT).exists(), reason="专利语料目录不存在")
def test_scan_patent_corpus_only_new_instruments():
    docs = scan_patent_corpus()
    names = {d.name for d in docs}
    # 仅收录真正新增：7 部规章 + 1 部新司法解释
    assert len(docs) >= 8
    assert "专利代理管理办法" in names
    assert "专利实施强制许可办法" in names
    assert "专利权质押登记办法" in names
    assert "专利标识标注办法" in names
    assert "专利行政执法办法" in names
    assert "关于规范专利申请行为的若干规定" in names
    assert "用于专利程序的生物材料保藏办法" in names
    assert "最高人民法院关于审理侵害知识产权民事纠纷案件适用惩罚性赔偿的解释" in {d.full_name for d in docs}


@pytest.mark.skipif(not Path(PATENT_ROOT).exists(), reason="专利语料目录不存在")
def test_scan_patent_corpus_excludes_local_and_standard():
    docs = scan_patent_corpus()
    names = {d.name for d in docs}
    assert not (_EXCLUDED_NAMES & names)


@pytest.mark.skipif(not Path(PATENT_ROOT).exists(), reason="专利语料目录不存在")
def test_scan_patent_corpus_domain_and_articles():
    docs = scan_patent_corpus()
    assert docs, "应解析出至少一篇专利文件"
    for d in docs:
        assert d.domain == PATENT_DOMAIN
        assert len(d.articles) > 0, f"{d.name} 应解析出条文"
        assert d.legal_level in ("部门规章", "司法解释")


def test_patent_domain_constant():
    assert PATENT_DOMAIN == "专利"
