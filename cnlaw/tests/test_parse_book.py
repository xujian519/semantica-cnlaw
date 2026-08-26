"""Tests for the 以案说法 book parser (cnlaw/ingest/parse_book.py)."""

from pathlib import Path

import pytest

from cnlaw.ingest.parse_book import (
    EXTRACT_ROOT,
    _is_head_title,
    _match_section,
    _norm_num,
    parse_book_txt,
    scan_book,
)

_SAMPLE = """             第一章         不授予专利权的客体

      对发明创造授予专利权必须有利于推动其应用，提高创新能力，促进
科学技术进步和经济社会发展。

1   《专利法》第 2 条所称的发明创造

      根据《专利法》笫 2 条笫 2 款的规定，发明是指对产品、方法或其改进所提出的
新的技术方案。

1.1   技术方案的判断

      根据《专利审查指南》第二部分第一章第 2 节的规定，技术方案是对要解决的
技术问题所采取的利用了自然规律的技术手段的集合。

1. 2. 2   包括方法特征的产品权利要求

      对于既包括产品结构特征，又包括结构部件的加工装配方法的实用新型权利要求。



                                                          001
咖气：复审、无效典型案例指引
"""


def _write(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def test_parse_book_metadata_and_sections(tmp_path):
    p = _write(tmp_path, "第一章-不授予专利权的客体.txt", _SAMPLE)
    doc = parse_book_txt(p)

    assert doc.name.startswith("以案说法 第一章")
    assert "不授予专利权的客体" in doc.name
    assert doc.full_name.startswith("《以案说法：专利复审、无效典型案例指引》")
    assert doc.category == "书籍"
    assert doc.domain == "专利"
    assert doc.legal_level == "书籍"
    assert doc.status == "现行有效"
    assert doc.source_date == "2018-09-01"
    assert doc.promulgated_date == "2018-09-01"

    numbers = [a.number for a in doc.articles]
    assert "1" in numbers and "1.1" in numbers
    # OCR-spaced number normalised back to a dotted path
    assert any(a.number == "1.2.2" for a in doc.articles)

    s = next(a for a in doc.articles if a.number == "1.2.2")
    assert s.kind == "book_section"
    assert s.level == 3
    assert s.parent_number == "1.2"
    assert s.title == "包括方法特征的产品权利要求"
    assert "实用新型" in s.text

    # chapter intro prose becomes a '0' introduction node
    intro = next(a for a in doc.articles if a.number == "0")
    assert intro.kind == "introduction"
    assert "对发明创造授予专利权" in intro.text

    # running header / page footer noise is dropped, so no garbage section
    assert all(a.text for a in doc.articles)


def test_parse_book_heading_vs_prose(tmp_path):
    # a prose line that merely begins with a numeral is not a heading
    assert _is_head_title("技术方案的判断") is True
    assert _is_head_title("对棋盘本身的结构进行了限定，并具体限定了棋盘为双面棋盘") is False
    assert _is_head_title("中 JBL Pulse 蓝牙音箱的产品介绍页面、产品展示页面") is False
    assert _is_head_title("非治疗目的的外科手术方法") is True
    # a leftover OCR number fragment at the head is not a valid title
    assert _is_head_title(". l 现有设计状况的考量") is False


@pytest.mark.parametrize("raw,expected", [
    ("1. 2. 2", "1.2.2"),
    ("3. 3. l. 1", "3.3.1.1"),
    ("4. 4. l", "4.4.1"),
    ("3.2 . 1", "3.2.1"),
    ("1", "1"),
])
def test_norm_num(raw, expected):
    assert _norm_num(raw) == expected


def test_match_section_spaced_number():
    # space around the dot + l glyph must still yield a normalised heading
    m = _match_section("4. 4. l   现有设计状况的考量")
    assert m is not None
    assert m[1] == "4.4.1"
    assert m[2] == "现有设计状况的考量"


@pytest.mark.skipif(not EXTRACT_ROOT.exists(), reason="《以案说法》提取文本目录不存在")
def test_scan_book_complete():
    docs = scan_book()
    assert len(docs) == 12  # 第一章..第十二章
    assert all(len(d.articles) > 0 for d in docs)
    assert all(d.domain == "专利" for d in docs)
    assert all(d.category == "书籍" for d in docs)
    assert all(d.full_name.startswith("《以案说法") for d in docs)
    # 全书-full.txt is excluded -> no chapter named after the whole book
    assert not any("全书" in d.name for d in docs)
