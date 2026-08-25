"""Tests for the 专利审查指南 parser (cnlaw/ingest/parse_guide.py)."""

from pathlib import Path

import pytest

from cnlaw.ingest.parse_guide import (
    parse_amendment_markdown,
    parse_guide_markdown,
    scan_guide_corpus,
)
from cnlaw.ingest.prepare_guide_corpus import OUT_DIR

_SAMPLE = """# 专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书

<!-- INFO END -->

## 第二章 说明书和权利要求书

引言段：专利法第二十六条第一款规定……

### 1 引言

根据专利法第二十六条第一款的规定，一件发明专利申请应当有说明书（必要时应当有附图）及其摘要和权利要求书。

### 2 说明书

专利法第二十六条第三款和专利法实施细则第二十条分别对说明书的实质性内容和撰写方式作了规定。

#### 2.1 说明书应当满足的要求

说明书应当对发明作出清楚、完整的说明。

##### 2.1.1 清楚

说明书的内容应当清楚。

### 3 申请文件

#### 3.1 其他文件

其他文件的审查……
"""

_AMENDMENT_SAMPLE = """# 专利审查指南修改对照表

> 根据2025年11月13日国家知识产权局令第84号公布，自2026年1月1日起施行

<!-- INFO END -->

## 说明

本文档列出修改内容。

## 第一部分第一章

### 1. 4.1.2 发明人

**旧版（2023）：**

> 发明人是指对发明创造的实质性特点作出创造性贡献的人。……

**新版（2026）：**

专利法实施细则第十四条规定，发明人应当填写真实信息。……

### 2. 4.1.6 专利代理机构

**旧版（2023）：**

旧内容。……

**新版（2026）：**

新内容。……
"""


def _write(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def test_parse_guide_sections_and_metadata(tmp_path):
    p = _write(tmp_path, "第二章.md", _SAMPLE)
    doc = parse_guide_markdown(p)

    assert doc.full_name == "专利审查指南 第二部分 实质审查·第二章 说明书和权利要求书"
    assert doc.name == "说明书和权利要求书"
    assert doc.category == "审查指南"
    assert doc.domain == "专利"
    assert doc.legal_level == "部门规章"
    assert doc.source_date == "2023-12-11"

    numbers = [a.number for a in doc.articles]
    assert "1" in numbers and "2" in numbers and "2.1" in numbers and "2.1.1" in numbers

    s21 = next(a for a in doc.articles if a.number == "2.1")
    assert s21.level == 2
    assert s21.parent_number == "2"
    assert s21.title == "说明书应当满足的要求"
    assert s21.part == "二"
    assert s21.chapter == "说明书和权利要求书"
    assert "本领域技术" not in s21.text and "清楚、完整" in s21.text

    # the chapter-level intro becomes a number='0' node
    intro = next(a for a in doc.articles if a.number == "0")
    assert intro.kind == "introduction"
    assert "引言段" in intro.text


def test_parse_guide_drops_container_heading(tmp_path):
    # `#### 3 申请文件` has no prose of its own (its child 3.1 carries it) -> dropped
    p = _write(tmp_path, "第二章.md", _SAMPLE)
    doc = parse_guide_markdown(p)
    assert not any(a.number == "3" and a.level == 1 for a in doc.articles)
    assert any(a.number == "3.1" for a in doc.articles)
    assert all(a.text for a in doc.articles)  # no zero-text nodes


def test_parse_amendment(tmp_path):
    p = _write(tmp_path, "修改对照表.md", _AMENDMENT_SAMPLE)
    doc = parse_amendment_markdown(p)
    assert doc.full_name == "专利审查指南修改对照表"
    assert len(doc.articles) == 2
    assert doc.articles[0].kind == "amendment"
    assert doc.articles[0].number == "1"
    assert doc.articles[0].title == "4.1.2 发明人"
    assert "旧版（2023）：" in doc.articles[0].text
    assert "新版（2026）：" in doc.articles[0].text


@pytest.mark.skipif(not OUT_DIR.exists(), reason="归一化指南语料目录不存在")
def test_scan_guide_corpus_complete():
    docs = scan_guide_corpus(OUT_DIR)
    # 六部分共 38 章，每章至少一个节
    assert len(docs) == 38
    assert all(len(d.articles) > 0 for d in docs)
    assert all(d.domain == "专利" for d in docs)
    assert all(d.category == "审查指南" for d in docs)
