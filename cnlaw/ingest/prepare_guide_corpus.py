"""Prepare a normalized per-chapter markdown corpus for the 专利审查指南.

Source: the OCR full text 审查指南/extracted/审查指南2023全文.txt (the "2023版"),
which is the single complete source covering all six parts. (A curated markdown
corpus exists for parts 1-4 but it is incomplete — e.g. the 创造性 and
不授予专利权的申请 chapter files are fragments — so the complete text is used
uniformly instead.)

Every chapter is re-emitted as one markdown file under a ``审查指南_guide_md/``
directory with a uniform heading convention:

    # 专利审查指南 <part_title>·<chapter_title>
    <!-- INFO END -->
    ## 第X章 <chapter_title>
    ### <N.> <title>
    #### <N.M> <title>
    ##### <N.M.K> <title>
    ...body prose...

Chapter/section titles are replaced by authoritative names from the guide's
table of contents, fixing OCR truncation and stray spaces. The OCR reflow joins
line-wrapped prose and drops page markers / running headers / footers.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

RAW_ROOT = Path("/Users/xujian/projects/宝宸知识库_Raw")
TXT_PATH = RAW_ROOT / "审查指南" / "extracted" / "审查指南2023全文.txt"
OUT_DIR = RAW_ROOT / "审查指南_guide_md"

CN_INT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10}
INT_CN = {v: k for k, v in CN_INT.items()}
for _v in range(11, 20):  # 十一..十九 (and 二十 below)
    INT_CN[_v] = "十" + INT_CN[_v - 10]
INT_CN[20] = "二十"


def _cn_num(s: str) -> int:
    """Parse a Chinese ordinal (一, 十, 十一, 二十, 二十三)."""
    if s in CN_INT:
        return CN_INT[s]
    if len(s) == 2 and s[0] == "十":
        return 10 + CN_INT[s[1]]
    if len(s) == 2 and s[1] in CN_INT:
        return CN_INT[s[0]] * 10 + CN_INT[s[1]]
    return 0

PARTS: Dict[int, Dict] = {
    1: {"title": "第一部分 初步审查", "source": "txt",
        "chapters": {1: "发明专利申请的初步审查", 2: "实用新型专利申请的初步审查",
                     3: "外观设计专利申请的初步审查", 4: "专利分类"}},
    2: {"title": "第二部分 实质审查", "source": "txt",
        "chapters": {1: "不授予专利权的申请", 2: "说明书和权利要求书", 3: "新颖性",
                     4: "创造性", 5: "实用性", 6: "单一性和分案申请", 7: "检索",
                     8: "实质审查程序", 9: "关于涉及计算机程序的发明专利申请审查的若干规定",
                     10: "关于化学领域发明专利申请审查的若干规定",
                     11: "关于中药领域发明专利申请审查的若干规定"}},
    3: {"title": "第三部分 进入国家阶段的国际申请的审查", "source": "txt",
        "chapters": {1: "进入国家阶段的国际申请的初步审查和事务处理",
                     2: "进入国家阶段的国际申请的实质审查"}},
    4: {"title": "第四部分 复审与无效请求的审查", "source": "txt",
        "chapters": {1: "总则", 2: "复审请求的审查", 3: "无效宣告请求的审查",
                     4: "复审和无效宣告程序中有关口头审理的规定",
                     5: "无效宣告程序中外观设计专利的审查",
                     6: "无效宣告程序中实用新型专利审查的若干规定",
                     7: "无效宣告程序中对于同样的发明创造的处理",
                     8: "无效宣告程序中有关证据问题的规定"}},
    5: {"title": "第五部分 专利申请及事务处理", "source": "txt",
        "chapters": {1: "专利申请文件及手续", 2: "专利费用", 3: "受理",
                     4: "专利申请文档", 5: "保密申请与向外国申请专利的保密审查",
                     6: "通知和决定", 7: "期限、权利的恢复、中止、审查的顺序",
                     8: "专利公报和单行本的编辑", 9: "专利权的授予和终止",
                     10: "专利权评价报告", 11: "专利开放许可"}},
    6: {"title": "第六部分 外观设计国际申请", "source": "txt",
        "chapters": {1: "外观设计国际注册申请的事务处理", 2: "外观设计国际申请的审查"}},
}


def _despace_cjk(s: str) -> str:
    """Remove the spacing the PDF/OCR introduced between CJK glyphs."""
    return re.sub(r"(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])\s+(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])", "", s)


# ── all parts: from the OCR full text ─────────────────────────────────────
# ── Parts 5-6: from the OCR full text ───────────────────────────────────────

PAGE_RE = re.compile(r"^={5,}.*?页.*?={5,}$")
DOTLEAD_RE = re.compile(r"\.{2,}")
FOOTER_RE = re.compile(r"^\s*[（(]?\d{0,3}\s*[-－]\s*\d{1,2}[)）]?\s*\d{0,3}\s*$")
CN_RUN_RE = re.compile(r"专利审查指南")  # running headers/footers mention it
CH_HEAD_RE = re.compile(r"^第\s*([一二三四五六七八九十]+)\s*章[ \t]+(.*)$")
SEC_HEAD_A = re.compile(r"^\s*(\d+)\.\s+(.*)$")              # 3. 适用文字
SEC_HEAD_B = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)*)\s+(.*)$")  # 4.1 纸张 / 3.1.1 标题
BARE_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s*$")        # a bare "3." / "4.1" line
CITATION_RE = re.compile(r"^(?:法|细则|实施细则)\s*[\d.]+\s*(?:[及和与]\s*[\d.]+\s*)*")
FOOTER_TOKEN_RE = re.compile(r"\s?\d{0,3}\s*（\d{1,3}[-－]\d{1,3}）\s*\d{0,3}")  # "14 （1-2）" page footer


def _is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if PAGE_RE.match(s):
        return True
    if DOTLEAD_RE.search(s):  # table-of-contents entries
        return True
    if FOOTER_RE.match(s):  # page-number footers
        return True
    if CN_RUN_RE.search(s):  # running headers / footers
        return True
    if len(s) <= 1:  # isolated margin chars (第/五/部/分)
        return True
    if s in {"目 录", "目录", "专利申请及事务处理", "外观设计国际申请", "总 目 录"}:
        return True
    return False


def _looks_like_title(title: str) -> bool:
    t = re.sub(r"\s+", "", title)
    if len(t) < 2 or len(t) > 40:
        return False
    if not re.search(r"[\u4e00-\u9fff]", t):  # a title carries CJK
        return False
    if re.fullmatch(r"[\d.、，。；()（）]+", t):  # page numbers / pure symbols
        return False
    if re.search(r"[。，；：！？]", t):  # prose carries sentence punctuation; a title never does
        return False
    if t.endswith(("。", "，", "；", "、")):  # an interrupted sentence
        return False
    return True


def _find_section(line: str):
    m = SEC_HEAD_A.match(line)
    if m and _looks_like_title(m.group(2)):
        return m.group(1), m.group(2).strip(), 1
    m = SEC_HEAD_B.match(line)
    if m and _looks_like_title(m.group(2)):
        return m.group(1), m.group(2).strip(), len(m.group(1).split("."))  # 4.1 -> 2, 3.1.1 -> 3
    return None


def _txt_bounds() -> Dict[int, int]:
    """Return the body start line (0-based) of each part, keyed by part ordinal."""
    lines = TXT_PATH.read_text(encoding="utf-8").split("\n")
    bounds: Dict[int, int] = {}
    for ord_cn in range(1, 7):
        sym = INT_CN[ord_cn]
        bounds[ord_cn] = next(i for i, l in enumerate(lines) if l.strip() == f"第{sym}部分")
    return bounds


def extract_txt_region(part: int) -> List[str]:
    lines = TXT_PATH.read_text(encoding="utf-8").split("\n")
    bounds = _txt_bounds()
    start = bounds[part]
    if part + 1 in bounds:
        end = bounds[part + 1]
    else:  # last part (6): end at the index section
        end = next(i for i, l in enumerate(lines)
                   if i > start and re.fullmatch(r"索\s*引", l.strip()))
    return lines[start:end]


def build_part_txt(part: int) -> List[Tuple[int, str]]:
    lines = extract_txt_region(part)
    chapters = PARTS[part]["chapters"]
    out: List[Tuple[int, str]] = []
    cur_ord = None
    sec_items: List[Tuple[int, str, str, List[str]]] = []  # (level, num, title, body_lines)
    cur_sec = None
    chapter_intro: List[str] = []

    def flush_section():
        nonlocal cur_sec
        if cur_sec is not None:
            sec_items.append(cur_sec)
            cur_sec = None

    def emit_chapter():
        nonlocal sec_items, chapter_intro
        if cur_ord is None or cur_ord not in chapters:
            sec_items = []
            chapter_intro = []
            return
        parts_md = []
        if chapter_intro:
            parts_md.append(FOOTER_TOKEN_RE.sub("", "".join(chapter_intro)).strip())
        for level, num, title, body in sec_items:
            parts_md.append(f"{'#' * (2 + level)} {_despace_cjk(num)} {_despace_cjk(title)}")
            parts_md.append(FOOTER_TOKEN_RE.sub("", "".join(body)).strip())
        out.append((cur_ord, "\n\n".join([p for p in parts_md if p])))
        sec_items = []
        chapter_intro = []

    for i, line in enumerate(lines):
        if _is_noise(line):
            continue
        m = CH_HEAD_RE.match(line.strip())
        if m:
            flush_section()
            emit_chapter()
            cur_ord = _cn_num(m.group(1))
            continue
        if cur_ord is None:
            continue
        content = CITATION_RE.sub("", line.strip(), count=1).strip()
        s = _find_section(content)
        if s:
            flush_section()
            cur_sec = (s[2], s[0], s[1], [])
            continue
        # A bare "3." line whose next content line is a title -> heading split across lines.
        bn = BARE_NUM_RE.match(content)
        if bn:
            nxt = ""
            for j in range(i + 1, len(lines)):
                if not _is_noise(lines[j]):
                    nxt = lines[j].strip()
                    break
            if nxt and SEC_HEAD_A.match(nxt) is None and SEC_HEAD_B.match(nxt) is None \
                    and _looks_like_title(nxt):
                flush_section()
                num = bn.group(1)
                cur_sec = (len(num.split(".")), num, nxt, [])
                continue
        if cur_sec is None:
            chapter_intro.append(content)
        else:
            cur_sec[3].append(content)
    flush_section()
    emit_chapter()
    return out


# ── assembly / CLI ──────────────────────────────────────────────────────────

def _chapter_md(part: int, ord: int, body: str) -> str:
    cn = INT_CN[ord]
    part_title = PARTS[part]["title"]
    ch_title = PARTS[part]["chapters"][ord]
    head = (f"# 专利审查指南 {part_title}·第{cn}章 {ch_title}\n\n"
            f"<!-- INFO END -->\n\n## 第{cn}章 {ch_title}\n")
    return f"{head}{body}\n" if body else head


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Build normalized 审查指南 per-chapter markdown corpus.")
    p.add_argument("--out", default=str(OUT_DIR))
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    part_cn = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    built: List[Tuple[int, int, str]] = []
    for part, info in PARTS.items():
        if info["source"] == "md":
            items = build_part2_md() if part == 2 else build_part_md(part)
        else:
            items = build_part_txt(part)
        if not items:
            print(f"WARNING: part {part} produced no chapters")
            continue
        for ord, body in items:
            title = info["chapters"][ord]
            fname = f"第{part_cn[part]}部分_第{INT_CN[ord]}章_{title}.md"
            (out / fname).write_text(_chapter_md(part, ord, body), encoding="utf-8")
            built.append((part, ord, title))

    counts = Counter(p for p, _, _ in built)
    print({"chapters": len(built), "by_part": dict(sorted(counts.items()))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
