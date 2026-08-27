"""Rules for excluding non-legal files and spotting local regulations.

The corpus stores instruments under department directories, but the layout is
not clean: Obsidian index files (`_index.md`) sit in every directory, how-to
documents (攻略/手册) leak into `其他/`, and local regulations (地方性法规)
appear both under the dedicated `地方性法规/` tree AND mixed into `行政法规/`
(e.g. `三都水族自治县都柳江渔业条例`). These rules handle each case.
"""

from __future__ import annotations

import re
from typing import Optional

# 地方性法规常见特征词（地点 + 规范性文件后缀）
_LOCAL_PLACE = r"(省|市|自治区|自治州|自治县|自治旗|区|县)"
_LOCAL_ACT = r"(条例|办法|规定|实施细则|实施办法|规则|规程|决定)"
_LOCAL_RE = re.compile(rf"^(中华人民共和国)?.*{_LOCAL_PLACE}.*{_LOCAL_ACT}$")

# 全国性法规虽会提及省/市/县/区（如“国务院关于…地区封锁的规定”“城市公共交通条例”），
# 但它们并非地方性法规。凡标题以国家权力机关/国家机关名称或通用政策领域名词（非具体地名）开头
# 者一律不判为地方性法规，避免把全国性法规误排除出库。
_NATIONAL_PREFIX = re.compile(
    r"^(全国|国务院|最高人民法院|最高人民检察院|全国人民代表大会常务委员会|"
    r"中华人民共和国|中国人民解放军|中央)"
)
_GENERIC_NATIONAL = re.compile(
    r"^(城市|行政区域|行政区划|风景名胜区|蓄滞洪区|人力资源市场|"
    r"森林和野生动物|矿产资源|自然保护区|保税区|进出口|民族工作)"
)

# 攻略 / 手册类非法规文档
_HOWTO_RE = re.compile(r"(攻略|入门手册|实用手册|操作指南|问答集)")

LOCAL_CATEGORY = "地方性法规"


def is_index_file(file_name: str) -> bool:
    """True for the Obsidian directory index file present in every folder."""
    return file_name == "_index.md"


def is_local_regulation(full_name: str) -> bool:
    """Heuristic for a local regulation hiding in a national-category folder.

    A national law is named 中华人民共和国X; a local regulation names a place
    (省/市/自治区/自治州/县...) followed by 条例/办法/规定/... This is marked
    for manual review rather than hard-deleted, since a name like
    《上海航运交易所管理规定》 is actually a State-Council-approved rule.
    """
    if not full_name:
        return False
    name = full_name.strip()
    # 全国性法规（国家权力机关/机关名称开头，或通用政策领域名词开头）不视为地方性法规
    if _NATIONAL_PREFIX.match(name) or _GENERIC_NATIONAL.match(name):
        return False
    return bool(_LOCAL_RE.match(name))


def is_howto(full_name: str) -> bool:
    """True for how-to/guide documents that are not legal instruments."""
    return bool(_HOWTO_RE.search(full_name or ""))


def should_exclude(file_name: str, full_name: str, category: str) -> Optional[str]:
    """Return a reason string if the file must be excluded, else None.

    The caller applies directory-level exclusion for `地方性法规/` first; this
    function is the file-level backstop that also marks local regulations for
    manual review instead of dropping them silently.
    """
    if is_index_file(file_name):
        return f"Obsidian 索引文件 {file_name}"
    if category == LOCAL_CATEGORY:
        return "地方性法规目录整体排除"
    if is_howto(full_name):
        return "非法规文档（攻略/手册类）"
    if is_local_regulation(full_name):
        return "疑似地方性法规，待人工复核"
    return None
