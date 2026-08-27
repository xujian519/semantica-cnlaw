"""Parse the 2026.01 Chinese IPC classification table into structured nodes.

The corpus lives as eight ``extracted_text/IPC_<X>部_2026.01.txt`` files (one
per IPC section A-H). Each classification entry's code sits at column 0 of the
line; continuation lines (indented) are the tail of the *previous* entry's title
and are skipped. Because the extracted PDF text is noisy, the entry level is
derived from the *code structure* (``A`` -> ``A01`` -> ``A01B`` -> ``A01B1/00``
-> ``A01B1/02``), never from the layout, and titles are best-effort cleaned.

The tree (``ipc:parent``) is also derived from the code: subgroup -> its main
group (or the nearest shallower subgroup), main group -> subclass, subclass ->
class, class -> section. For aggregating decisions under a node we use **code
prefix matching** (every code that starts with ``A01B`` belongs to subclass
A01B), which is the IPC semantics and is layout-independent.

Pure functions here are unit-testable; only the loader touches Neo4j.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VERSION = "2026.01"

# Standard IPC section titles (fallback when the txt line is noisy/missing).
SECTION_TITLES = {
    "A": "人类生活必需",
    "B": "作业；运输",
    "C": "化学；冶金",
    "D": "纺织；造纸",
    "E": "固定建筑物",
    "F": "机械工程；照明；加热；武器；爆破",
    "G": "物理",
    "H": "电学",
}
_LEVELS = ("section", "class", "subclass", "group", "subgroup")

# Page header/footer noise.
_PAGE_RE = re.compile(r"^\s*第\s*\d+\s*页，共\s*\d+\s*页\s*$")
_EDITION_RE = re.compile(r"^\s*\d{4}(?:\.0?\d)?版IPC分类表-[A-H]部\s*$")

# A classification entry line. The code must be the very first character (no
# leading whitespace); an indented line is a title continuation and is skipped.
#   group1 = section letter, group2 = class digits, group3 = subclass letter,
#   group4 = group/subgroup "N/MM", group5 = dots before the title (subgroup depth).
_ENTRY_RE = re.compile(
    r"^([A-H])(\d{2})?([A-Z])?((?:\d+)?(?:/\d+)?)?\s*([.·]*)\s*(.*)$"
)

# Version markers embedded / trailing a title.
_VERSION_MARK_RE = re.compile(r"[\[〔(（]\s*\d{4}[\.．]\d{2}\s*[\]〕)）]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class IpcNode:
    """A single IPC classification entry."""

    code: str = ""
    title: str = ""
    level: str = ""
    version: str = VERSION
    dots: int = 0  # subgroup indent depth, used to reconstruct the tree

    def key(self) -> str:
        return self.code


def _section_letter_from_path(path) -> str:
    """Derive the section letter (A-H) from a file path like IPC_A部_2026.01.txt."""
    m = re.search(r"IPC_([A-H])部", str(path))
    return m.group(1) if m else ""


def detect_section_title(text: str, section: str) -> str:
    """Best-effort section title: prefer the ``X部——title`` line, else the fallback."""
    m = re.search(rf"{section}\s*[A-H]?部[——\-－]{{1,3}}\s*(.+)", text)
    if m:
        title = _clean_title(m.group(1))
        if title:
            return title
    return SECTION_TITLES.get(section, section)


def _clean_title(raw: str) -> str:
    """Strip version markers, embedded notes and collapse whitespace."""
    title = _VERSION_MARK_RE.sub("", raw or "")
    title = title.replace("〔", "").replace("〕", "").replace("【", "").replace("】", "")
    title = _WHITESPACE_RE.sub(" ", title).strip()
    return title


def _entry_level(sec: str, cls: Optional[str], sub: Optional[str], group: Optional[str]) -> Optional[str]:
    if not cls:
        # section letter only -> don't create a node here (handled separately)
        return None
    if not sub:
        return "class"
    if not group:
        return "subclass"
    if group.endswith("/00"):
        return "group"
    return "subgroup"


def _entry_code(sec: str, cls: str, sub: str, group: str) -> str:
    if not group:
        # class (A01) or subclass (A01B) line - no /NN suffix
        return f"{sec}{cls}{sub or ''}"
    num, _, denom = group.partition("/")
    return f"{sec}{cls}{sub}{num}/{denom or '00'}"


def parse_ipc_file(path) -> List[IpcNode]:
    """Parse one section txt file into its IPC entries (incl. the section node)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    section = _section_letter_from_path(path)
    section_title = detect_section_title(text, section)

    nodes: List[IpcNode] = []
    seen: set = set()

    if section:
        nodes.append(IpcNode(code=section, title=section_title, level="section", dots=0))
        seen.add(section)

    for line in text.split("\n"):
        if not line or line[0].isspace():
            continue  # title continuation / indented note, not an entry
        if _PAGE_RE.match(line) or _EDITION_RE.match(line):
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        sec, cls, sub, group, dots, title = m.groups()
        level = _entry_level(sec, cls, sub, group)
        if level is None:
            continue  # section-like line; the section node is already emitted
        code = _entry_code(sec, cls, sub or "", group or "")
        if code in seen:
            continue
        seen.add(code)
        # main-group /00 lines have no dots; subgroups carry a dot depth.
        ndots = len(dots) if level == "subgroup" else 0
        nodes.append(IpcNode(code=code, title=_clean_title(title), level=level, dots=ndots))
    return nodes


def parse_ipc_directory(directory) -> List[IpcNode]:
    """Parse every section txt in a directory and dedupe by code (first wins)."""
    d = Path(directory)
    by_code: Dict[str, IpcNode] = {}
    order: List[str] = []
    for path in sorted(glob_paths(d)):
        for node in parse_ipc_file(path):
            if node.code not in by_code:
                by_code[node.code] = node
                order.append(node.code)
    return [by_code[c] for c in order]


def glob_paths(d: Path) -> List[Path]:
    return sorted(d.glob("IPC_*部_2026*.txt"))


# ── Tree / parent derivation (code-based) ─────────────────────────────────────

def _main_group(code: str) -> str:
    """A01B1/02 -> A01B1/00 (the main group for that subclass+group)."""
    m = re.match(r"^([A-H]\d{2}[A-Z])(\d+)/", code)
    return f"{m.group(1)}{m.group(2)}/00" if m else ""


def _parent_code(seq: List[IpcNode], i: int) -> str:
    """Derive the parent of node i by code + the preceding subgroup dots."""
    node = seq[i]
    code, level = node.code, node.level

    if level == "class":
        return code[0]
    if level == "subclass":
        return code[:3]
    if level == "group":
        return code[:4]  # subclass

    # subgroup: nearest preceding entry in the same main group with one fewer dot
    group = _main_group(code)
    depth = node.dots
    for prev in reversed(seq[:i]):
        if not prev.code.startswith(code[:4]):
            continue  # different subclass -> reset
        if _main_group(prev.code) != group:
            continue  # different main group -> parent is the main group
        if prev.dots < depth:
            return prev.code
    return group


def build_ipc_tree(nodes: List[IpcNode]) -> Tuple[List[IpcNode], List[Tuple[str, str]]]:
    """Return (nodes, parent_edges) with parent edges as (child_code, parent_code).

    Parent edges are derived from the code structure so the result never depends
    on the source layout. Children whose parent node is not present in ``nodes``
    (e.g. an orphan subgroup whose /00 node is missing) are left without a parent.
    """
    codes = {n.code for n in nodes}
    edges: List[Tuple[str, str]] = []
    seen: set = set()
    for i, node in enumerate(nodes):
        parent = _parent_code(nodes, i)
        if not parent or parent == node.code:
            continue
        if parent not in codes:
            continue  # orphan; skip rather than invent a node
        edge = (node.code, parent)
        if edge in seen:
            continue
        seen.add(edge)
        edges.append(edge)
    return nodes, edges


# ── Decision IPC code normalisation / resolution ─────────────────────────────

# A candidate IPC code in a (noisy) decision ipc field like "H04L 25/49" or
# "F28F19/04; B23K10/00". Captures subclass/group/subgroup; class/section are
# handled by the caller when a finer code cannot be resolved.
_IPC_TOKEN_RE = re.compile(r"[A-H]\d{2}[A-Z](?:\s*\d{1,5})?(?:/\d{1,6})?")
_CLASS_RE = re.compile(r"[A-H]\d{2}")
_SECTION_RE = re.compile(r"[A-H]")


def normalize_ipc_codes(raw: str) -> List[str]:
    """Extract and canonicalise IPC codes from a dirty decision ipc field.

    Removes version markers and inner whitespace, and drops orphan fragment codes
    (e.g. a stray ``/30`` after ``;;``). Class and section fragments are *not*
    returned here - only subclass/group/subgroup codes, which are what the table
    classifies decisions by.
    """
    text = _VERSION_MARK_RE.sub(" ", raw or "")
    # tokens like "H04L 25/49" -> "H04L25/49"; brace forms like "25/49(2006.01)" drop
    codes: List[str] = []
    for tok in _IPC_TOKEN_RE.findall(text):
        norm = re.sub(r"\s+", "", tok)
        if norm not in codes:
            codes.append(norm)
    return codes


def build_ipc_index(nodes: List[IpcNode]) -> Dict[str, IpcNode]:
    """A code->node lookup for fast resolution."""
    return {n.code: n for n in nodes}


def resolve_ipc_in_index(code: str, by_code: Dict[str, IpcNode]) -> Optional[str]:
    """Most-specific existing node for a raw code using a prebuilt index, or None.

    Falls back through main-group -> subclass -> class -> section so a decision
    whose exact group/subgroup is absent still links to the nearest ancestor.
    """
    candidates = [code]
    if "/" in code:
        m = re.match(r"^([A-H]\d{2}[A-Z]\d+)/", code)
        if m:
            candidates.append(f"{m.group(1)}/00")
        candidates.append(code[:4])  # subclass
    candidates.append(code[:3])  # class
    candidates.append(code[0])  # section
    for c in candidates:
        if c in by_code:
            return c
    return None


def resolve_ipc(code: str, nodes: List[IpcNode]) -> Optional[str]:
    """Convenience wrapper over :func:`resolve_ipc_in_index` (builds the index)."""
    return resolve_ipc_in_index(code, build_ipc_index(nodes))


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Parse the IPC classification table.")
    parser.add_argument("--dir", default="/Users/xujian/projects/宝宸知识库_Raw/IPC分类表/extracted_text")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    nodes = parse_ipc_directory(args.dir)
    if args.limit is not None:
        nodes = nodes[: args.limit]
    _, edges = build_ipc_tree(nodes)
    from collections import Counter

    levels = Counter(n.level for n in nodes)
    print({"nodes": len(nodes), "edges": len(edges), "levels": dict(levels)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
