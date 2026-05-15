#!/usr/bin/env python3
"""
Stage 4 (diagnostic): scan records.jsonl for parsing-error patterns and emit
diagnostics.md with one row per flagged record (category + evidence snippet).

This is read-only — it never modifies records. Used to size each pattern
before deciding parser-fix vs. corrections.jsonl.
"""

from __future__ import annotations
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RECORDS_FILE = ROOT / "records.jsonl"
OUT_FILE = ROOT / "diagnostics.md"


def load_records() -> list[dict]:
    decoder = json.JSONDecoder()
    content = RECORDS_FILE.read_text(encoding="utf-8")
    out: list[dict] = []
    pos = 0
    while pos < len(content):
        while pos < len(content) and content[pos] in " \t\n\r":
            pos += 1
        if pos >= len(content):
            break
        obj, end = decoder.raw_decode(content, pos)
        out.append(obj)
        pos = end
    return out


# ── detection rules ───────────────────────────────────────────────────────────

# Multi-entry: numbered next-entry marker inside abstract
RE_MULTI_NUM = re.compile(r"\n\s*\d{1,2}[.\)]\s+[A-Z]")

# Multi-entry: initials-style author line inside abstract
# matches "F. M. Lastname" / "F.M. Lastname" / "F. Lastname" patterns
RE_MULTI_INITIALS = re.compile(
    r"\n\s*[A-Z]\.\s*(?:[A-Z]\.?\s*)?[A-Z][a-z]{2,}",
)

# Multi-entry: all-caps line of 4+ words (probable next-entry TITLE)
RE_MULTI_ALLCAPS = re.compile(r"\n\s*([A-Z][A-Z0-9 ,'\-]{20,})\n")

# Embedded schedule fragments
RE_SCHEDULE_TIME = re.compile(r"\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\b")
RE_SCHEDULE_SESSION = re.compile(r"\bSession\s+\d+\s+Chair\b", re.IGNORECASE)
RE_SCHEDULE_DAY = re.compile(r"\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+[A-Z][a-z]+\s+\d+", re.IGNORECASE)

# Triple-newline (after collapse during load, this is rare but real)
RE_TRIPLE_NL = re.compile(r"\n{3,}")

# Page-footer leak in middle of abstract. Require start-of-line / preceding
# whitespace so citations like "(Duffy et al, In-House Conference 2012)"
# don't trigger.
RE_FOOTER_LEAK = re.compile(
    r"(?:(?<=\n)|^)\s*(?:"
    r"Psychology\s+(?:Department|and\s+Neuroscience)\s+In-?House"
    r"|In-?House\s+(?:Program|Conference|Convention)\s+\d{4}"
    r"|PAGE\s+\d+"
    r")",
    re.IGNORECASE,
)

# Orphan page numbers between paragraphs
RE_ORPHAN_PAGENUM = re.compile(r"\n\s*\d{1,3}\s*\n")

# Trailing numeral (page number on last line)
RE_TRAILING_NUM = re.compile(r"\n\s*\d{1,3}\s*$")

# Author has digit
RE_AUTH_DIGIT = re.compile(r"\d")

# Author has place / department / university
RE_AUTH_PLACE = re.compile(
    r"\b(Spain|USA|U\.S\.A\.|Canada|UK|U\.K\.|France|Germany|Italy|Japan|Australia|"
    r"Halifax|Toronto|Montreal|Boston|New\s+York|Cambridge|Oxford|"
    r"Nova\s+Scotia|Ontario|Quebec|"
    r"Department\s+of|University\s+of|Institute\s+of|School\s+of|Faculty\s+of|"
    r"Departments\s+of|Hospital|Centre\s+for|Center\s+for)\b",
    re.IGNORECASE,
)

# Lowercase initial in author name (OCR degradation: "f. Smith")
RE_AUTH_LOWER_INITIAL = re.compile(r"(?:^|[\s\-,;&/])([a-z])\.\s*[A-Z]")

# Title-is-abstract: long title with prose-style markers
RE_TITLE_PROSE = re.compile(
    r"\b(we\s+(?:found|examined|present|investigated|conducted|tested|hypothesi[sz]ed|"
    r"observed|report|propose|developed)|"
    r"the\s+present\s+(?:study|paper|experiment|investigation|research)|"
    r"in\s+(?:this|the\s+present)\s+(?:study|paper|experiment|investigation|research)|"
    r"results?\s+(?:showed|indicate|suggest|demonstrated)|"
    r"these\s+(?:results?|findings?|data)|"
    r"our\s+(?:results?|findings?|data|study))\b",
    re.IGNORECASE,
)

# Affiliation-style first paragraph of abstract
RE_ABS_AFFIL_HEAD = re.compile(
    r"\A[^\n]{0,200}\n[^\n]*\b(Department|University|Institute|Hospital|"
    r"Faculty|School)\b",
    re.IGNORECASE,
)

# Thresholds
ABS_LONG = 2200          # suspicious (250-word abstract ≈ 1800 chars)
ABS_VERY_LONG = 3000     # almost certainly contaminated
ABS_VERY_SHORT = 60      # likely truncated
TITLE_LONG = 220


def diagnose(r: dict) -> list[tuple[str, str]]:
    """Return a list of (tag, evidence_snippet) for the record."""
    tags: list[tuple[str, str]] = []
    title = r.get("title") or ""
    authors = r.get("authors_raw") or ""
    abstract = r.get("abstract") or ""

    # ── abstract checks ──────────────────────────────────────────────────────
    if abstract:
        if m := RE_MULTI_NUM.search(abstract):
            tags.append(("multi-entry-numerated", _snip(abstract, m)))
        if m := RE_MULTI_INITIALS.search(abstract):
            tags.append(("multi-entry-initials", _snip(abstract, m)))
        if m := RE_MULTI_ALLCAPS.search(abstract):
            tags.append(("multi-entry-allcaps-title", _snip(abstract, m)))
        if RE_SCHEDULE_TIME.search(abstract) or RE_SCHEDULE_SESSION.search(abstract):
            m = RE_SCHEDULE_TIME.search(abstract) or RE_SCHEDULE_SESSION.search(abstract)
            tags.append(("embedded-schedule", _snip(abstract, m)))
        elif RE_SCHEDULE_DAY.search(abstract):
            m = RE_SCHEDULE_DAY.search(abstract)
            tags.append(("embedded-day-header", _snip(abstract, m)))
        if m := RE_TRIPLE_NL.search(abstract):
            tags.append(("triple-newline", _snip(abstract, m)))
        if m := RE_FOOTER_LEAK.search(abstract):
            tags.append(("page-footer-leak", _snip(abstract, m)))
        if m := RE_ORPHAN_PAGENUM.search(abstract):
            tags.append(("orphan-pagenum", _snip(abstract, m)))
        if m := RE_TRAILING_NUM.search(abstract):
            tags.append(("trailing-numeral", _snip(abstract, m)))
        if RE_ABS_AFFIL_HEAD.match(abstract):
            tags.append(("abstract-affiliation-head", abstract[:120].replace("\n", " ⏎ ")))
        n = len(abstract)
        if n > ABS_VERY_LONG:
            tags.append(("abstract-very-long", f"{n} chars"))
        elif n > ABS_LONG:
            tags.append(("abstract-suspicious-long", f"{n} chars"))
        if 0 < n < ABS_VERY_SHORT:
            tags.append(("abstract-too-short", f"{n} chars"))

    # ── title checks ─────────────────────────────────────────────────────────
    if title:
        if len(title) > TITLE_LONG:
            tags.append(("title-too-long", f"{len(title)} chars"))
        if RE_TITLE_PROSE.search(title):
            m = RE_TITLE_PROSE.search(title)
            tags.append(("title-is-abstract", _snip(title, m)))
        if "\n" in title:
            tags.append(("title-has-newline", title[:80].replace("\n", " ⏎ ")))

    # ── authors checks ───────────────────────────────────────────────────────
    if authors:
        if RE_AUTH_DIGIT.search(authors):
            tags.append(("author-has-digit", authors[:80]))
        if RE_AUTH_PLACE.search(authors):
            m = RE_AUTH_PLACE.search(authors)
            tags.append(("author-has-place", _snip(authors, m)))
        if RE_AUTH_LOWER_INITIAL.search(authors):
            m = RE_AUTH_LOWER_INITIAL.search(authors)
            tags.append(("author-lowercase-initial", _snip(authors, m)))

    return tags


def _snip(text: str, m: re.Match, width: int = 80) -> str:
    start = max(0, m.start() - width // 2)
    end = min(len(text), m.end() + width // 2)
    snip = text[start:end].replace("\n", " ⏎ ")
    if start > 0:
        snip = "…" + snip
    if end < len(text):
        snip = snip + "…"
    return snip


# ── citekey lookup (rebuild from records the same way export does) ───────────

def _citekey(r: dict, used: set[str]) -> str:
    import unicodedata
    authors = r.get("authors_raw") or ""
    title = r.get("title") or ""
    # First lastname
    first = authors.split(" and ")[0].split("&")[0].split(",")[0].strip()
    if "," in (authors.split(" and ")[0]):
        first = authors.split(" and ")[0].split(",")[0].strip()
    else:
        toks = first.split()
        first = toks[-1] if toks else "anon"
    lastname = unicodedata.normalize("NFD", first).encode("ascii", "ignore").decode().lower()
    lastname = re.sub(r"[^a-z]", "", lastname) or "anon"
    year = r.get("year", 0)
    # Short title
    words = re.sub(r"[^A-Za-z ]", " ",
                   unicodedata.normalize("NFD", title).encode("ascii", "ignore").decode()).split()
    stop = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
            "is", "are", "as", "by", "its", "with"}
    word = ""
    for w in words:
        if w.lower() not in stop and len(w) >= 3:
            word = w.lower()[:12]
            break
    if not word:
        word = words[0].lower()[:12] if words else "x"
    base = f"{lastname}{year}{word}"
    key = base
    i = 0
    while key in used:
        i += 1
        key = base + chr(ord("a") + i - 1)
    used.add(key)
    return key


def main() -> None:
    records = load_records()
    print(f"Loaded {len(records)} records")

    # Build citekeys
    used: set[str] = set()
    keys: dict[tuple[int, str], str] = {}
    for r in sorted(records, key=lambda x: (x.get("year", 0), x.get("entry_id", ""))):
        keys[(r["year"], r["entry_id"])] = _citekey(r, used)

    # Diagnose each record
    findings: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    per_record: list[tuple[dict, list[tuple[str, str]]]] = []
    tag_counts: Counter[str] = Counter()
    tag_year_counts: dict[str, Counter[int]] = defaultdict(Counter)

    for r in records:
        tags = diagnose(r)
        if tags:
            per_record.append((r, tags))
            for tag, snip in tags:
                tag_counts[tag] += 1
                tag_year_counts[tag][r["year"]] += 1
                findings[tag].append((r, snip))

    # ── write report ────────────────────────────────────────────────────────
    lines: list[str] = [
        "# Diagnostics — Dalhousie In-House Conference BibTeX Pipeline\n\n",
        f"Total records scanned: **{len(records)}**\n",
        f"Records with at least one flag: **{len(per_record)}** "
        f"({100 * len(per_record) / len(records):.1f}%)\n\n",
        "## Tag summary (sorted by count)\n\n",
        "| Tag | Count | Years (top 5) |\n|-----|-------|---------------|\n",
    ]
    for tag, count in tag_counts.most_common():
        top_years = ", ".join(f"{yr}:{c}" for yr, c in tag_year_counts[tag].most_common(5))
        lines.append(f"| `{tag}` | {count} | {top_years} |\n")
    lines.append("\n")

    # Per-tag detail
    for tag, _ in tag_counts.most_common():
        lines.append(f"## `{tag}` ({tag_counts[tag]} records)\n\n")
        lines.append("| Citekey | Year | Entry | Evidence |\n|---|---|---|---|\n")
        # Sort by year then entry_id
        for r, snip in sorted(findings[tag],
                              key=lambda x: (x[0]["year"], x[0]["entry_id"]))[:200]:
            ck = keys.get((r["year"], r["entry_id"]), "?")
            ev = snip.replace("|", "\\|")[:150]
            lines.append(f"| `{ck}` | {r['year']} | {r['entry_id']} | {ev} |\n")
        if tag_counts[tag] > 200:
            lines.append(f"\n_(showing first 200 of {tag_counts[tag]})_\n")
        lines.append("\n")

    OUT_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"Diagnostics → {OUT_FILE}")
    print(f"\nTop tags:")
    for tag, count in tag_counts.most_common(15):
        print(f"  {count:>4}  {tag}")


if __name__ == "__main__":
    main()
