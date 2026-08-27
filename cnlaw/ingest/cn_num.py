"""Chinese <-> Arabic numeral helpers for statute references (pure, offline).

Patent decisions cite 第22条第3款 while stored Article nodes and judgments use
Chinese numerals (第二十二条 / 第二十二条第三款). These helpers normalize both
sides so a user's ``ground`` reference resolves to the same Article number, and
the graph queries can match `Article.number` regardless of which form it uses.
"""

from __future__ import annotations

import re

_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "贰": 2, "两": 2,
             "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6,
             "陆": 6, "七": 7, "柒": 7, "八": 8, "捌": 8, "九": 9, "玖": 9}
_CN_UNIT = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}

_CN_DIG = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
           7: "七", 8: "八", 9: "九"}


def cn_num_to_int(s: str) -> int:
    """Convert a Chinese-numeral run (0..9999) to an int, e.g. '二十二' -> 22."""
    total = 0
    current = 0
    for ch in s:
        if ch in _CN_DIGIT:
            current = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            total += (current or 1) * _CN_UNIT[ch]
            current = 0
    return total + current


def cn_numerals_to_arabic(text: str) -> str:
    """Replace runs of Chinese numerals with Arabic, e.g. '第二十二条' -> '第22条'."""
    def repl(m):
        return str(cn_num_to_int(m.group(0)))
    return re.sub(r"[零〇一二两三四五六七八九十百千壹贰叁肆伍陆柒捌玖拾佰仟]+", repl, text)


def arabic_to_cn(n: int) -> str:
    """Convert an int to Chinese numerals, e.g. 22 -> '二十二', 122 -> '一百二十二'."""
    if n < 0:
        return str(n)
    if n < 10:
        return _CN_DIG[n]
    if n < 20:
        return "十" + (_CN_DIG[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return _CN_DIG[tens] + "十" + (_CN_DIG[ones] if ones else "")
    if n < 1000:
        hun, rest = divmod(n, 100)
        s = _CN_DIG[hun] + "百"
        if rest == 0:
            return s
        if rest < 10:
            return s + "零" + _CN_DIG[rest]
        return s + arabic_to_cn(rest)
    th, rest = divmod(n, 1000)
    s = _CN_DIG[th] + "千"
    return s + (arabic_to_cn(rest) if rest else "")


def extract_article_number(ref: str) -> int | None:
    """Pull the 条 number out of a statute reference, either numeral form.

    '专利法第22条第3款' / '第二十二条第三款' -> 22; '实施细则第二十条' -> 20.
    Returns None when no 第X条 pattern is present.
    """
    norm = cn_numerals_to_arabic(ref or "")
    m = re.search(r"第(\d+)条", norm)
    return int(m.group(1)) if m else None
