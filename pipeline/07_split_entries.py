#!/usr/bin/env python3
"""
Stage 7: Split contaminated entries — given a breakpoints file written by
the human reviewer (descriptions of specific issues to fix.md), each line
of the form

   % year=YYYY  entry_id=XX
   - <breakpoint text 1>
   - <breakpoint text 2>
   ...

instructs the script to:
  1. Find each breakpoint text inside the parent entry's abstract.
  2. Truncate the parent abstract at the FIRST breakpoint.
  3. For each subsequent section (between two breakpoints, or after the
     last breakpoint to end-of-abstract), parse it as a new entry using
     the year-appropriate author/title heuristic and emit an `add` op.

Output: corrections_from_splits.jsonl — preview, then run with --apply
to append to corrections.jsonl.
"""

from __future__ import annotations
import json
import re
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
PIPE = Path(__file__).parent
DESC_FILE = ROOT / "descriptions of specific issues to fix.md"
OUT = ROOT / "corrections_from_splits.jsonl"


def _load_module(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, PIPE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── descriptions file parser ──────────────────────────────────────────────────

# Strip surrounding markdown decoration from a breakpoint line.
# Examples handled:
#   '- "abstract = {Tl 2. Scott Bishop"'                  →  'Tl 2. Scott Bishop'
#   '- "Effects of ..." '                                 →  'Effects of ...'
#   '-   F. D. Quine'                                     →  'F. D. Quine'
#   '- new entry at "Symposium To Hebb and Beyond"'       →  'Symposium To Hebb and Beyond'
#   '- new entry at Singh, Prem'                          →  'Singh, Prem'
_LEAD = re.compile(r"^\s*-+\s*")
_QUOTE_WRAP = re.compile(r'^"(.*)"\s*[.,]?\s*$')
_ABSTRACT_PREFIX = re.compile(r'^\s*"?\s*abstract\s*=\s*\{\s*', re.IGNORECASE)
# Strip leading meta-phrases the reviewer used
_META_PREFIX = re.compile(
    r"^(?:new\s+entr(?:y|ies)\s+(?:start(?:s|ing)?\s+)?(?:at|starts?\s+at)\s*"
    r"|create\s+(?:a\s+)?new\s+entr(?:y|ies)\s+(?:starting\s+)?at\s*"
    r"|second\s+\"?abstract\"?\s+field\s+is\s+actually\s+a\s+separate\s+entry\s+starting\s+at\s*"
    r"|split\s+at\s*:?\s*"
    r")\s*\"?",
    re.IGNORECASE,
)
# Words sometimes left over after stripping
_LEFTOVER = re.compile(r'^\s*["·•\-:]+\s*')


def _clean_breakpoint(line: str) -> str:
    """Pull the breakpoint phrase out of a Markdown bullet line.

    Strategy: strip meta-prefix first. Then:
      • If line matches a pure-note prose pattern ("this contains ...",
        "there is a ..."), look for an embedded quoted phrase as the marker.
      • If line begins with a quote, the quoted phrase IS the marker.
      • Otherwise, treat the plain text as the marker (trimmed at any
        '[' bracket-note like '[NOTE: ...]').
    """
    s = _LEAD.sub("", line).strip()
    if not s:
        return s
    s = _META_PREFIX.sub("", s).strip()
    if not s:
        return s
    bib_field_words = {"abstract", "title", "author", "authors"}

    if _is_pure_note(s):
        # Embedded quoted marker
        quoted = re.findall(r'"([^"]+)"', s)
        for q in quoted:
            if q.strip().lower() not in bib_field_words:
                return _strip_trailing_punct(q)
        return ""
    if s.startswith('"'):
        m = re.match(r'^"([^"]+)"', s)
        if m and m.group(1).strip().lower() not in bib_field_words:
            s = m.group(1)
    else:
        # Plain text up to first '[' (side note) — keep inline quotes
        cut = s.find('[')
        if cut > 0:
            s = s[:cut].strip()
    # Strip "abstract = {" / "title = {" prefix from the extracted text
    if _ABSTRACT_PREFIX.match(s):
        s = _ABSTRACT_PREFIX.sub("", s)
        cut = s.find('"')
        if cut >= 0:
            s = s[:cut]
    s = re.sub(r'^title\s*=\s*\{\s*', "", s, flags=re.IGNORECASE)
    # Cut at trailing reviewer-prose markers
    cut = s.find('", ')
    if cut >= 0:
        s = s[:cut]
    # Strip trailing quote/paren/punctuation
    s = re.sub(r'["\}\)]+\s*$', "", s).strip()
    s = s.rstrip(",")
    s = _LEFTOVER.sub("", s)
    return s.strip()


def parse_descriptions(path: Path) -> list[dict]:
    """Return a list of {year, entry_id, breakpoints[], field_updates[]}
    from the markdown."""
    text = path.read_text(encoding="utf-8")
    cases: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        # Header line: % year=N  entry_id=X
        m = re.match(r"\s*%\s*year\s*=\s*(\d+)\s+entry_id\s*=\s*(\S+)", line)
        if m:
            if current and (current["breakpoints"] or current["field_updates"]):
                cases.append(current)
            current = {
                "year": int(m.group(1)),
                "entry_id": m.group(2),
                "breakpoints": [],
                "field_updates": [],
                "raw_lines": [],
            }
            continue
        if current is None:
            continue
        # Bullet line
        if re.match(r"\s*-", line):
            current["raw_lines"].append(line)
            # Field update? ("- author is 'Juckes, Tim'")
            fu = _try_parse_field_update(line)
            if fu:
                current["field_updates"].append(fu)
                continue
            # Otherwise treat as a split breakpoint
            bp = _clean_breakpoint(line)
            if bp and len(bp) >= 4 and not _is_pure_note(bp):
                current["breakpoints"].append(bp)
    if current and (current["breakpoints"] or current["field_updates"]):
        cases.append(current)
    return cases


_PURE_NOTE_PATTERNS = (
    re.compile(r"^(?:title|abstract|authors?)\s+is\s+", re.IGNORECASE),
    re.compile(r"^this\s+contains", re.IGNORECASE),
    re.compile(r"^there\s+is\s+a\s+", re.IGNORECASE),
    re.compile(r"^new\s+entries?\s+(?:start\s+)?at\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^create\s+(?:a\s+)?new\s+entries?\s+(?:starting\s+)?at\s*:?\s*$",
               re.IGNORECASE),
    re.compile(r"^second\s+\"?abstract\"?\s+field", re.IGNORECASE),
    re.compile(r"^split\s+at\s*:?\s*$", re.IGNORECASE),
)


def _is_pure_note(s: str) -> bool:
    return any(p.match(s) for p in _PURE_NOTE_PATTERNS)


# Patterns for field-update lines (NOT splits): "author is 'X'", "title is 'X'"
_FIELD_UPDATE_RE = re.compile(
    r"^\s*-?\s*(?P<field>title|abstract|authors?)\s+is\s+\"?(?P<value>[^\"]+)\"?\s*$",
    re.IGNORECASE,
)
# Field-name → records.jsonl field key
_FIELD_NAME_MAP = {
    "title": "title",
    "author": "authors_raw",
    "authors": "authors_raw",
    "abstract": "abstract",
}


def _strip_trailing_punct(s: str) -> str:
    """Trim trailing whitespace, commas, closing brackets/quotes."""
    s = s.strip()
    s = re.sub(r'["\}\)]+\s*$', "", s)
    return s.rstrip(",.;:").strip()


def _try_parse_field_update(line: str) -> tuple[str, str] | None:
    """Match a 'author is "X"' / 'title is "X"' style line.
    Returns (field_name, value) or None."""
    m = _FIELD_UPDATE_RE.match(line)
    if not m:
        return None
    field = _FIELD_NAME_MAP.get(m.group("field").lower())
    if not field:
        return None
    return field, m.group("value").strip().strip('"').rstrip(",").strip()


# ── inference: parse a chunk as a new entry, year-aware ───────────────────────


def _strip_entry_number(text: str) -> str:
    """Drop leading OCR-garbled entry numbers ('3 3. ', 'Tl 2. ', 'TS. ', '9. ',
    '33.').  Requires either:
      - an explicit T/P/HP/SS prefix followed by 1+ digit-like chars, OR
      - a real digit anywhere in the marker (so '33.', '3 3.', or '9.' qualify,
        but bare 'L.' / 'B.' / 'M.' as author initials are NOT stripped).
    """
    return re.sub(
        r"^\s*(?:"
        r"(?:HP|SS|[TP])[\s0-9OoQlI|iSsBZzb]{1,5}"   # explicit prefix
        r"|\d{1,2}"                                    # plain digit(s) like '33.'
        r"|\d\s*[0-9OoQlI|iSsBZzb]"                    # mixed like '3 3.' / '3l.'
        r"|[0-9OoQlI|iSsBZzb]\s*\d"                    # mixed like 'l3.' / 'S 3.'
        r")[.,)]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _normalize_separators(chunk: str) -> str:
    """Replace OCR-garbled author/title separators ('-:-', '- :', ':-') with
    a canonical ' - ', so the 1976-1980 inline parser can find them."""
    # Common OCR variants: "-:-", "- :-", " :- ", " -- "
    chunk = re.sub(r"\s+[-–]\s*[:;]\s*[-–]?\.?", " - ", chunk)
    chunk = re.sub(r"\s+[-–]{2,}\s+", " - ", chunk)
    return chunk


def _breakpoint_looks_like_author(breakpoint: str) -> bool:
    """True if the breakpoint text looks like a person name (initials or
    First Last), rather than a title-style sentence.

    Used to choose between author-first and title-first parsing for
    1994+ chunks where the user's breakpoint indicates the START of the
    new entry — and the START is either the author name or the title.
    """
    s = breakpoint.strip()
    if not s:
        return False
    # "Lastname, Firstname" presenter format (2025+)
    if re.match(r"^[A-Z][a-zA-Z\-]+,\s*[A-Z]", s):
        return True
    # Initials + Lastname: "F. M. Lastname", "F.M. Lastname", "C. N. Bennett"
    if re.match(r"^[A-Z]\.\s*(?:[A-Z]\.?\s*)?[A-Z][a-z]+", s):
        return True
    # Firstname Lastname (1-4 words, all capitalized, no colon or long phrase)
    words = s.split()
    if 1 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
        if ":" not in s and len(s) < 60:
            return True
    return False


def _infer_labeled_chunk(chunk: str) -> tuple[str, str, str] | None:
    """If the chunk uses explicit TALK/POSTER TITLE / AUTHORS / ABSTRACT
    labels (2019, 2022-2025 formats), parse them directly. Returns None
    if no labels are found."""
    t = re.search(r"(?i)(?:TALK|POSTER)\s*TITLE\s*:\s*([^\n]+(?:\n(?!\s*(?:AUTHORS?|ABSTRACT)\s*:)[^\n]+)*)", chunk)
    a = re.search(r"(?i)AUTHORS?\s*:\s*([^\n]+)", chunk)
    ab = re.search(r"(?i)ABSTRACT\s*:\s*(.+?)(?=\n\s*(?:[A-Z][a-z]+,\s*[A-Z])|\Z)",
                   chunk, re.DOTALL)
    if not (t or a or ab):
        return None
    title = re.sub(r"\s+", " ", t.group(1)).strip() if t else ""
    authors = a.group(1).strip() if a else ""
    abstract = ab.group(1).strip() if ab else ""
    return title, authors, abstract


def _infer_entry(chunk: str, year: int, parser_module,
                 breakpoint: str = "") -> tuple[str, str, str]:
    """Parse a chunk of text as a new entry. Returns (title, authors, abstract)."""
    chunk = _strip_entry_number(chunk).strip()
    if not chunk:
        return "", "", ""

    # Labeled formats (2019, 2022-2025): use explicit labels regardless of year
    if re.search(r"(?i)(?:TALK|POSTER)\s*TITLE\s*:", chunk):
        labeled = _infer_labeled_chunk(chunk)
        if labeled and labeled[0]:
            return labeled

    # Year-appropriate format
    if 1976 <= year <= 1980:
        # Inline: "Author - Title\n\nAbstract" (sometimes "Author. Title")
        cleaned = _normalize_separators(chunk)
        title, authors, abstract = parser_module._parse_inline_early(cleaned)
        if not authors:
            title, authors, abstract = parser_module._parse_author_first(cleaned)
    elif 1981 <= year <= 1993:
        title, authors, abstract = parser_module._parse_author_first(chunk)
    else:  # 1994+
        # Pick parser based on what the breakpoint looks like.
        # If breakpoint is a name, the chunk is author-first; else title-first.
        author_starting = _breakpoint_looks_like_author(breakpoint)
        if author_starting:
            title, authors, abstract = parser_module._parse_author_first(chunk)
            # Fallback if author-first produced empty title
            if not title or not abstract:
                t2, a2, ab2 = parser_module._parse_title_first(chunk)
                if t2 and a2:
                    title, authors, abstract = t2, a2, ab2
        else:
            title, authors, abstract = parser_module._parse_title_first(chunk)
            if not authors:
                t2, a2, ab2 = parser_module._parse_author_first(chunk)
                if a2:
                    title, authors, abstract = t2, a2, ab2
    # Final cleanup: strip residual entry-number prefix from title and authors
    title = _strip_entry_number(title).strip()
    authors = _strip_entry_number(authors).strip()
    return title.strip(), authors.strip(), abstract.strip()


# ── main split logic ──────────────────────────────────────────────────────────


def find_breakpoint(abstract: str, breakpoint: str) -> int | None:
    """Locate `breakpoint` inside `abstract`. Tries exact, then whitespace-
    tolerant matching using string normalization (avoids regex catastrophic
    backtracking)."""
    pos = abstract.find(breakpoint)
    if pos >= 0:
        return pos
    matches = _find_all_whitespace_tolerant(abstract, breakpoint)
    return matches[0] if matches else None


def _load_extracted(year: int) -> str:
    """Read the year's extracted text (which still has paragraph breaks).
    Returns "" if unavailable."""
    path = ROOT / "extracted" / f"{year}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _find_all_whitespace_tolerant(source: str, needle: str) -> list[int]:
    """Return positions in `source` where `needle` occurs, treating any
    whitespace run as equivalent. Uses linear string scan with whitespace
    normalization to avoid the catastrophic-backtracking risk of regex
    alternatives like `\\s+\\S+\\s+\\S+...`.
    """
    if not source or not needle:
        return []
    # Pre-collapse whitespace in both — keep a position map back to the
    # original source.
    norm_chars: list[str] = []
    pos_map: list[int] = []
    in_ws = False
    for i, ch in enumerate(source):
        if ch.isspace():
            if not in_ws:
                norm_chars.append(" ")
                pos_map.append(i)
                in_ws = True
        else:
            norm_chars.append(ch)
            pos_map.append(i)
            in_ws = False
    norm_source = "".join(norm_chars)
    norm_needle = re.sub(r"\s+", " ", needle).strip()
    positions: list[int] = []
    start = 0
    while True:
        idx = norm_source.find(norm_needle, start)
        if idx < 0:
            break
        positions.append(pos_map[idx])
        start = idx + 1
    return positions


def _locate_in_source(source: str, breakpoint: str, near: str = "") -> int | None:
    """Locate `breakpoint` in `source`. If `near` is given, locate the
    LAST occurrence of `near` first (typically the parent's title in the
    abstracts section, not in the schedule TOC) and prefer breakpoint
    matches AFTER that anchor."""
    if not source:
        return None
    matches = _find_all_whitespace_tolerant(source, breakpoint)
    if not matches:
        return None
    if near:
        anchor_positions = _find_all_whitespace_tolerant(source, near[:80])
        if anchor_positions:
            anchor_pos = anchor_positions[-1]
            after = [p for p in matches if p > anchor_pos]
            if after:
                return after[0]
    return matches[0]


def main() -> None:
    parser_module = _load_module("p2", "02_parse.py")
    export_module = _load_module("p3", "03_export_bib.py")

    # Load records and apply existing corrections (so we work on the
    # current state, not stale parser output).
    records = export_module.load_records()
    records, patched, deleted = export_module.apply_corrections(records)
    by_key = {(r["year"], r["entry_id"]): r for r in records}

    cases = parse_descriptions(DESC_FILE)
    print(f"Loaded {len(cases)} cases from {DESC_FILE.name}")

    patch_ops: list[dict] = []
    add_ops: list[dict] = []
    notes: list[str] = []

    # Cache source files per year (since multiple cases may share a year)
    source_cache: dict[int, str] = {}

    for case in cases:
        year = case["year"]
        eid = case["entry_id"]
        rec = by_key.get((year, eid))
        if rec is None:
            notes.append(f"  ⚠ {year}/{eid}: parent record not found (skipped)")
            continue

        # Apply field-update patches first ("author is X", "title is X")
        if case.get("field_updates"):
            patch = {field: value for field, value in case["field_updates"]}
            patch_ops.append({
                "year": year, "entry_id": eid, "patch": patch,
            })

        # If no breakpoints, we're done with this case
        if not case["breakpoints"]:
            continue

        abstract = rec.get("abstract", "") or ""
        if not abstract:
            notes.append(f"  ⚠ {year}/{eid}: parent has no abstract to split")
            continue

        # Locate each breakpoint in the CURRENT (cleaned) abstract for
        # truncation. This is the source of truth for "what stays in parent".
        positions: list[tuple[int, str]] = []
        for bp in case["breakpoints"]:
            pos = find_breakpoint(abstract, bp)
            if pos is None:
                notes.append(f"  ⚠ {year}/{eid}: breakpoint not found in abstract: {bp!r}")
            else:
                positions.append((pos, bp))
        if not positions:
            continue
        positions.sort()

        # Truncate parent at first breakpoint
        first_pos = positions[0][0]
        new_parent_abstract = abstract[:first_pos].rstrip()
        patch_ops.append({
            "year": year,
            "entry_id": eid,
            "patch": {"abstract": new_parent_abstract},
        })

        # For each section, use the ORIGINAL extracted text (where paragraph
        # breaks survive) to do reliable title/author/abstract inference.
        source = source_cache.setdefault(year, _load_extracted(year))
        # Anchor: use the parent's title (or first 80 chars of original
        # abstract) to find where in the source we are.
        anchor = rec.get("title", "")[:80]
        for i, (pos, bp) in enumerate(positions):
            # Find this breakpoint in the source
            next_bp = positions[i + 1][1] if i + 1 < len(positions) else None
            src_start = _locate_in_source(source, bp, near=anchor)
            if src_start is None:
                # Fallback: parse the cleaned chunk (less reliable)
                end = positions[i + 1][0] if i + 1 < len(positions) else len(abstract)
                chunk = abstract[pos:end].strip()
                src_chunk_kind = "cleaned"
            else:
                if next_bp:
                    src_end = _locate_in_source(source, next_bp, near=bp)
                    if src_end is None or src_end <= src_start:
                        src_end = src_start + 3000
                else:
                    src_end = src_start + 3000
                chunk = source[src_start:src_end]
                src_chunk_kind = "source"
            title, authors_raw, sub_abstract = _infer_entry(
                chunk, year, parser_module, breakpoint=bp)
            new_eid = _suffix_eid(eid, i)
            add_ops.append({
                "year": year,
                "entry_id": new_eid,
                "add": True,
                "presentation_type": rec.get("presentation_type", "talk"),
                "title": title,
                "authors_raw": authors_raw,
                "abstract": sub_abstract,
                "parser_format": f"split_from_parent_{src_chunk_kind}",
                "confidence": "manual_split",
                "qa_flags": ["needs-split-review"],
                "note_extra": f"Split from {eid} at: {bp[:40]!r}",
            })

    # Write preview file
    lines: list[str] = [
        "# Auto-generated from `pipeline/07_split_entries.py`.\n",
        f"# Source: {DESC_FILE.name}\n",
        f"# {len(patch_ops)} parent truncations + {len(add_ops)} new entries.\n",
        "#\n",
        "# Inspect each line, then run with --apply to append to corrections.jsonl.\n\n",
    ]
    if notes:
        lines.append("# Notes/warnings:\n")
        for n in notes:
            lines.append(f"# {n}\n")
        lines.append("\n")

    for p in sorted(patch_ops, key=lambda x: (x["year"], x["entry_id"])):
        lines.append(json.dumps(p, ensure_ascii=False) + "\n")
    for a in sorted(add_ops, key=lambda x: (x["year"], x["entry_id"])):
        lines.append(json.dumps(a, ensure_ascii=False) + "\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(f"  Parent truncations: {len(patch_ops)}")
    print(f"  New entries:        {len(add_ops)}")
    print(f"  Warnings:           {len(notes)}")
    if notes:
        print("\nWarnings:")
        for n in notes:
            print(n)

    if "--apply" in sys.argv:
        _append_to_corrections(patch_ops, add_ops)


def _suffix_eid(parent_eid: str, idx: int) -> str:
    """Generate a new entry_id from parent_eid + sequence letter."""
    return f"{parent_eid}-split{idx + 1}"


def _append_to_corrections(patches: list[dict], adds: list[dict]) -> None:
    import datetime
    target = ROOT / "corrections.jsonl"
    if not (patches or adds):
        print("\nNothing to apply.")
        return
    header = (
        f"\n# ── Entry-split batch {datetime.date.today().isoformat()} "
        f"(via 07_split_entries.py) — "
        f"{len(patches)} truncations + {len(adds)} new entries ──\n"
    )
    with target.open("a", encoding="utf-8") as f:
        f.write(header)
        for p in sorted(patches, key=lambda x: (x["year"], x["entry_id"])):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
        for a in sorted(adds, key=lambda x: (x["year"], x["entry_id"])):
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"\nAppended to {target.name}.")
    print("Now run:")
    print("  python3 pipeline/03_export_bib.py")
    print("  python3 pipeline/05_review.py")


if __name__ == "__main__":
    main()
