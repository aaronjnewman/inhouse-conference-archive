#!/usr/bin/env python3
"""
Stage 3: Export records.jsonl → inhouse_conference.bib + qa_report.md

Citekey format:  LastnameYYYYShortTitle
  • Lastname: first author's last name, ASCII-only, lowercased
  • YYYY: four-digit year
  • ShortTitle: first significant word of title, lowercased, ASCII-only
Collisions get a, b, c … suffix.
"""

from __future__ import annotations
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from booktitles import get_booktitle

ROOT = Path(__file__).parent.parent
RECORDS_FILE = ROOT / "records.jsonl"
CORRECTIONS_FILE = ROOT / "corrections.jsonl"
BIB_FILE = ROOT / "inhouse_conference.bib"
QA_FILE = ROOT / "qa_report.md"

# ── text helpers ──────────────────────────────────────────────────────────────

def to_ascii(s: str) -> str:
    """Decompose accented chars to ASCII, drop remainder."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()

def clean_ws(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def bib_escape(s: str) -> str:
    """Strip characters that break BibTeX. The source PDFs/OCR produce
    spurious `{`, `}`, and isolated backslashes that are not real content —
    remove them outright rather than escape them."""
    s = s.replace("{", "").replace("}", "")
    # Drop bare backslashes (OCR noise). Preserve `\\\\` → empty too.
    s = s.replace("\\", "")
    return s

def wrap_bib_value(s: str) -> str:
    """Wrap a BibTeX field value in braces with inner-brace protection."""
    return "{" + bib_escape(s) + "}"


# ── author normalisation ──────────────────────────────────────────────────────

_DEPT_SUFFIXES = re.compile(
    r",?\s*(Dept(artment)?\.?\s*(of)?\s*\w+|University\s+of\s*\w+|"
    r"Dalhousie\s+University|PhD|MSc|MHSA|[0-9,]+)\s*$",
    re.IGNORECASE,
)

def _looks_like_two_names(s: str) -> bool:
    """Return True if 's' looks like two names joined by a comma (not Last, First)."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 2:
        return False
    # Each part should look like a name: ≤ 4 words, starts with capital
    return all(1 <= len(p.split()) <= 4 and p[:1].isupper() for p in parts)


def split_authors(authors_raw: str) -> list[str]:
    """Split an author string into a list of individual author strings."""
    if not authors_raw:
        return []
    # Remove department suffixes
    s = _DEPT_SUFFIXES.sub("", authors_raw).strip().rstrip(",;")
    # Split on ' and ', ' & '
    s = re.sub(r"\s+&\s+|\s+and\b", " AND_SEP ", s, flags=re.IGNORECASE)
    parts = re.split(r"\s+AND_SEP\s*", s)
    # Within each part, further split on commas that separate TWO names
    expanded: list[str] = []
    for part in parts:
        part = part.strip().rstrip(",;.")
        if not part:
            continue
        if "," in part and _looks_like_two_names(part):
            # Could be "Last, First" or "Name1, Name2" — hard to tell.
            # Heuristic: if the text before the comma is a single word, it's Last, First.
            before_comma = part.split(",")[0].strip()
            if len(before_comma.split()) == 1:
                # Likely "Lastname, Firstname" — keep as one name
                expanded.append(part)
            else:
                # Likely "Firstname Last1, Firstname Last2" — split
                for p in part.split(","):
                    p = p.strip()
                    if p:
                        expanded.append(p)
        elif "," in part:
            # Multiple commas or complex structure: try comma splitting
            comma_parts = [p.strip() for p in part.split(",") if p.strip()]
            if all(len(p.split()) <= 5 for p in comma_parts):
                expanded.extend(comma_parts)
            else:
                expanded.append(part)
        else:
            expanded.append(part)
    return [p.strip().rstrip(",;.") for p in expanded if p.strip()]


def normalise_name(raw: str) -> str:
    """
    Return 'LastName, First [Middle]' form.
    Input may be 'First Last' or 'Last, First' or 'F. Last' or 'Last'.
    """
    raw = raw.strip().rstrip(",.")
    if not raw:
        return ""
    # Already "Lastname, Firstname" form?
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        return f"{parts[0]}, {parts[1]}" if len(parts) == 2 else raw
    tokens = raw.split()
    if len(tokens) == 1:
        return tokens[0]
    # "First [Middle] Last" form — last token is surname
    surname = tokens[-1]
    given = " ".join(tokens[:-1])
    return f"{surname}, {given}"


def authors_bibtex(authors_raw: str) -> str:
    """Return BibTeX-format author string: 'Last, First and Last, First …'"""
    names = split_authors(authors_raw)
    if not names:
        return authors_raw or ""
    norm = [normalise_name(n) for n in names if n]
    return " and ".join(norm)


def first_lastname(authors_raw: str) -> str:
    """Return the last name of the first author for citekey generation."""
    names = split_authors(authors_raw)
    if not names:
        return "anon"
    first = names[0].strip()
    if "," in first:
        return first.split(",")[0].strip()
    tokens = first.split()
    return tokens[-1] if tokens else "anon"


# ── citekey generation ────────────────────────────────────────────────────────

_STOP_WORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "as", "by", "its", "with",
}

def short_title_word(title: str) -> str:
    """Pick the first significant word of the title for the citekey."""
    words = re.sub(r"[^A-Za-z ]", " ", to_ascii(title)).split()
    for w in words:
        if w.lower() not in _STOP_WORDS and len(w) >= 3:
            return w.lower()[:12]
    return words[0].lower()[:12] if words else "x"


def make_citekey(record: dict, used: set[str]) -> str:
    lastname = to_ascii(first_lastname(record.get("authors_raw", ""))).lower()
    lastname = re.sub(r"[^a-z]", "", lastname) or "anon"
    year = record.get("year", 0)
    word = short_title_word(record.get("title", ""))
    base = f"{lastname}{year}{word}"
    key = base
    suffix_idx = 0
    while key in used:
        suffix_idx += 1
        key = base + chr(ord("a") + suffix_idx - 1)
    used.add(key)
    return key


# ── BibTeX entry builder ──────────────────────────────────────────────────────

_ABSTRACT_NOISE = re.compile(
    r"(?:"
    r"(?:\n|^)\s*BALLOT"
    r"|(?:\n|^)\s*Most\s+Unusual\s+Abstract"
    r"|(?:\n|^)\s*Please\s+vote"
    r"|(?:\n|^)\s*Best\s+(?:Talk|Poster|Presentation)"
    r"|\s+(?:\d+\s+)?Psychology\s+Department\s+In-?House"
    r"|\s+(?:\d+\s+)?Psychology\s+and\s+Neuroscience\s+In-?House"
    r"|\s+In-?House\s+Program\s+\d{4}"
    r"|(?:\n|^)\s*PAGE\s+\d+"
    r"|(?:\n|^)\s*---+|(?:\n|^)\s*===+|(?:\n|^)\s*\*{5,}"
    r"|(?:\n|^)\s*_{4,}|\s_{6,}"        # underscore run at line-start OR mid-line
    r"|(?:\n|^)\s*Title\s*:?\s*[-_]{3,}"
    r"|(?:\n|^)\s*Author(?:s|\(s\))?\s*:?\s*_{3,}"
    r"|(?:\n|^)\s*I\s+cast\s+my\s+vote"  # 1975 ballot
    r"|(?:\n|^)\s*Presentation\s+(?:Format|Type)\s*:"
    r"|(?:\n|^)\s*Times?\s*/?\s*Day\s+Not\s+Available"
    r"|(?:\n|^)\s*Equipment\s*/?\s*Software\s+Required"
    r"|(?:\n|^)\s*\d+\s+words\b\s*[•·\*\-]"
    r")",
    re.IGNORECASE,
)

# Junk at the START of an abstract (e.g., 1975 OCR ballot leftovers)
_ABSTRACT_LEAD_NOISE = re.compile(
    r"\A(?:\s*"
    r"(?:"
    r"Title\s*:?\s*-{3,}"
    r"|Author(?:s|\(s\))?\s*:?\s*_{3,}"
    r"|-{5,}"
    r"|_{5,}"
    r"|\*{5,}"
    r")"
    r")+\s*",
    re.IGNORECASE,
)

# RTF field-code artifacts that textutil sometimes leaves in .doc conversions
_RTF_ARTIFACTS = re.compile(r"SEQ CHAPTER\\?\s*\\h\s*\\r\s*\d*\s*", re.IGNORECASE)

# Page header/footer templates that leak across page breaks in OCR/extraction.
# Strip wherever they appear (not just trailing). They typically include the
# conference name + year + page number, sometimes embedded mid-abstract.
_PAGE_HEADER_FOOTERS = [
    # 2003-2009 footer: "Psychology Department In-House Conference April 2005 PAGE 29"
    re.compile(
        r"\s*Psychology\s+Department\s+In-?House\s+Conference\s+"
        r"\w+\s+\d{4}\s*(?:PAGE\s+)?\d{0,3}\s*",
        re.IGNORECASE,
    ),
    # 2013-2017 footer: "2014 Psychology and Neuroscience In-House Conference"
    re.compile(
        r"\s*\d{4}\s+Psychology\s+and\s+Neuroscience\s+In-?House\s+Conference\s*"
        r"(?:PAGE\s+\d+|\d{1,3})?\s*",
        re.IGNORECASE,
    ),
    # 1996-1999 footer: "1996 In-House Convention 9"
    re.compile(
        r"\s*\d{4}\s+In-?House\s+(?:Conference|Convention)\s+\d{1,3}\s*",
        re.IGNORECASE,
    ),
    # Same footer with page number first: "10 1998 In-House Convention"
    re.compile(
        r"(?:^|\n)\s*\d{1,3}\s+\d{4}\s+In-?House\s+(?:Conference|Convention)\s*",
        re.IGNORECASE,
    ),
    # Ordinal-Annual variant: "Twentieth Annual In-House Convention"
    re.compile(
        r"\s*(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|"
        r"Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|"
        r"Eighteenth|Nineteenth|Twentieth|Twenty-First|Twenty-Second|Twenty-Third|"
        r"Twenty-Fourth|Twenty-Fifth|Twenty-Sixth|Twenty-Seventh|Twenty-Eighth|"
        r"Twenty-Ninth|Thirtieth|\d{1,2}(?:st|nd|rd|th))\s+Annual\s+"
        r"(?:Psychology\s+(?:Department|and\s+Neuroscience)?\s+)?In-?House\s+"
        r"(?:Conference|Convention)(?:[,.][^\n]*)?",
        re.IGNORECASE,
    ),
    # "Program Addendum" header
    re.compile(r"\s*Program\s+Addendum\s*", re.IGNORECASE),
    # Standalone "Department of Psychology" between blank lines
    re.compile(
        r"(?:\n\s*\n|\A)\s*Department\s+of\s+Psychology\s*(?=\n\s*\n|\Z)",
        re.IGNORECASE,
    ),
    # Standalone "PAGE 29" or "PAGE" line
    re.compile(r"(?:\n|^)\s*PAGE(?:\s+\d{1,3})?\s*(?=\n|$)", re.IGNORECASE),
    # 2007 variant: "2007 Psychology and Neuroscience InHouse Convention PAGE 5"
    re.compile(
        r"\s*\d{4}\s+Psychology\s+and\s+Neuroscience\s+In-?House\s+"
        r"(?:Conference|Convention)(?:\s+PAGE\s+\d+|\s+\d{1,3})?\s*",
        re.IGNORECASE,
    ),
]

def _is_ocr_garbage_line(line: str) -> bool:
    """True if a line is dominated by non-letter characters (OCR scanner
    noise from figures, handwriting, signatures). Used to drop lines like
    ``h'\\n,-~ (,-i._ '`` while preserving normal punctuation in real text."""
    s = line.strip()
    if not s:
        return False
    # Count letters vs total alphanum-or-symbol characters
    letters = sum(1 for c in s if c.isalpha())
    non_space = sum(1 for c in s if not c.isspace())
    if non_space == 0:
        return False
    letter_ratio = letters / non_space
    # Short line with few letters is suspicious
    if non_space < 60 and letter_ratio < 0.5:
        return True
    # Lines with many non-alphanumeric symbols regardless of length
    junk_chars = sum(1 for c in s if c in "~`!@#$%^&*\\|/<>{}[]")
    if junk_chars >= 4 and letter_ratio < 0.65:
        return True
    return False


def _strip_ocr_garbage(text: str) -> str:
    """Drop lines that look like OCR scanner noise."""
    out = []
    for line in text.splitlines():
        if not _is_ocr_garbage_line(line):
            out.append(line)
    return "\n".join(out)


_FOOTER_FOR_TRUNCATE = re.compile(
    r"(?:"
    r"\d{4}\s+(?:Psychology\s+(?:Department\s+|and\s+Neuroscience\s+)?)?"
    r"In-?House\s+(?:Conference|Convention)\s*\w*\s*\d{0,3}"
    r"|Psychology\s+Department\s+In-?House\s+Conference\s+\w+\s+\d{4}\s*(?:PAGE\s+)?\d{0,3}"
    r"|\d{1,3}\s+\d{4}\s+In-?House\s+(?:Conference|Convention)"
    r")",
    re.IGNORECASE,
)


def _truncate_after_page_break(text: str) -> str:
    """If a page-footer occurs and the content after it looks like a new
    entry (short title line + author-style line + long paragraph), truncate
    at the footer. Otherwise keep the text as-is (real cross-page abstract).
    """
    m = _FOOTER_FOR_TRUNCATE.search(text)
    if not m:
        return text
    after = text[m.end():].lstrip()
    if len(after) < 80:
        return text
    # Look at the first 600 chars after the footer
    sample = after[:600]
    # Heuristic 1: contains a standalone capitalised name line ("Richard Brown")
    name_on_own_line = bool(re.search(
        r"\n\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)*(?:\s+[A-Z][a-zA-Z\-']+)\s*\n",
        "\n" + sample))
    # Heuristic 2: leading content has a "Title-Case-Phrase\n...\nName"
    # structure typical of a new entry
    if name_on_own_line:
        return text[:m.start()].rstrip()
    return text


def clean_field(text: str) -> str:
    """Whitespace-normalize a single-line field (title, authors_raw).

    Collapses every whitespace run — including internal line breaks — to
    a single space and strips the ends. Source PDFs and OCR routinely
    introduce hard wraps inside titles and author lists; those are
    artifacts, not intentional formatting.
    """
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip()


def clean_abstract(text: str) -> str:
    """Strip ballot forms, page footers, RTF artifacts, OCR garbage,
    and similar noise."""
    if not text:
        return text
    text = _RTF_ARTIFACTS.sub("", text)
    text = _strip_ocr_garbage(text)
    # Truncate at page footer if a new entry follows it (cross-page contamination)
    text = _truncate_after_page_break(text)
    # Strip page header/footer templates that may appear anywhere
    # (cross-page leaks). Run repeatedly until stable so multiple instances
    # in one abstract all get removed.
    for pat in _PAGE_HEADER_FOOTERS:
        text = pat.sub(" ", text)
    # Strip orphan page numbers: a line containing only 1-3 digits between
    # blank-line-separated paragraphs (page break artifact).
    text = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", text)
    # Truncate at a "Symposium" or "Special Speaker"/"Invited Speaker"
    # section header on its own line — these introduce content that belongs
    # to a different (often unlabeled) entry.
    m = re.search(
        r"\n\s*(?:Symposium|Special\s+Speaker|Invited\s+Speaker|"
        r"Keynote\s+Address|Plenary)\s*\n",
        text,
        re.IGNORECASE,
    )
    if m:
        text = text[:m.start()]
    # Truncate at embedded schedule break: a time range followed by
    # Session/Coffee/Lunch/Break/Closing/Wine etc.
    m = re.search(
        r"\n\s*\d{1,2}:\d{2}\s*(?:am|pm)?\s*[-–]\s*\d{1,2}:\d{2}\s*(?:am|pm)?[:\s]+"
        r"\s*(?:Session|Coffee|Lunch|Break|Closing|Wine|Open|Reception|Dinner|"
        r"Posters?|COFFEE|LUNCH|BREAK)",
        text,
        re.IGNORECASE,
    )
    if m:
        text = text[:m.start()]
    # Also handle the case where a schedule begins with a bare time + entry
    # marker (no time-range): "\n1:30 T42)" — but only if multiple such
    # patterns appear (signal of an embedded schedule, not a single time
    # reference in regular prose).
    sched_marks = list(re.finditer(
        r"\n\s*\d{1,2}:\d{2}\s+(?:[TPH]+\d+\s*\)|Session)", text))
    if len(sched_marks) >= 2:
        text = text[:sched_marks[0].start()]
    # Drop "Session N. Chair: Name" markers anywhere (often appear when an
    # entry's "abstract" is actually the post-entry schedule rather than
    # real abstract content).
    text = re.sub(
        r"(?im)^\s*Session\s+\d+\.?\s*(?:Chair\s*:?[^\n]*)?$",
        "",
        text,
    )
    # Also "Chair:" on its own line (orphaned after schedule fragments).
    text = re.sub(r"(?im)^\s*Chair\s*:[^\n]*$", "", text)
    # If the entire abstract has degenerated to nothing but schedule
    # fragments (Session, Chair, time ranges, names on single lines), drop it.
    if re.fullmatch(r"\s*(?:Session|Chair|\d{1,2}:\d{2}[ap]?m?|\s|\n|"
                    r"[A-Z][a-z]+|[A-Z]\.|\.|,|:|/|the|in|2nd|3rd|Floor|"
                    r"Lounge|Dinner|Reception|Closing|Comments)*",
                    text):
        text = ""
    # Strip trailing single-numeral page numbers at the very end.
    text = re.sub(r"\n\s*\d{1,3}\s*$", "", text)
    # Collapse any whitespace runs introduced by substitution
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Per spec: at most one \n in a row (no blank lines inside an abstract).
    text = re.sub(r"\n{2,}", "\n", text)
    # Strip leading ballot/separator noise
    text = _ABSTRACT_LEAD_NOISE.sub("", text)
    m = _ABSTRACT_NOISE.search(text)
    if m:
        text = text[:m.start()].strip()
    # Per spec, abstracts have no internal line breaks and no multi-space
    # runs. OCR line wrapping is more often artifact than intentional
    # formatting. Done last so the line-anchored noise patterns above can
    # still match.
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _field(name: str, value: str) -> str:
    if not value:
        return ""
    return f"  {name} = {wrap_bib_value(value)},\n"


def record_to_bib(record: dict, citekey: str) -> str:
    year = record.get("year", "")
    booktitle, bt_source = get_booktitle(int(year))

    lines = [f"@inproceedings{{{citekey},\n"]
    lines.append(_field("title", clean_field(record.get("title", ""))))
    lines.append(_field("author", authors_bibtex(clean_field(record.get("authors_raw", "")))))
    lines.append(_field("booktitle", booktitle))
    lines.append(_field("year", str(year)))

    abstract = clean_abstract((record.get("abstract") or "").strip())
    if abstract:
        lines.append(_field("abstract", abstract))

    # Note field: parser format + QA flags
    notes: list[str] = []
    ptype = record.get("presentation_type", "talk")
    if ptype != "talk":
        notes.append(ptype.replace("_", " ").title())
    qa_flags = list(record.get("qa_flags", []))
    # Surface invited-speaker as a human-readable note, not a raw QA flag
    if "invited-speaker" in qa_flags:
        qa_flags.remove("invited-speaker")
        notes.append("Invited speaker")
    if qa_flags:
        notes.append(f"QA: {', '.join(qa_flags)}")
    if bt_source == "inferred":
        notes.append("booktitle inferred")
    if record.get("note_extra"):
        notes.append(record["note_extra"])
    if notes:
        lines.append(_field("note", "; ".join(notes)))

    lines.append("}\n")
    return "".join(l for l in lines if l)


# ── QA report ────────────────────────────────────────────────────────────────

def write_qa_report(records: list[dict], citekeys: dict[str, str]) -> None:
    lines: list[str] = [
        "# QA Report — Dalhousie In-House Conference BibTeX Pipeline\n\n",
    ]
    total = len(records)
    with_abs = sum(1 for r in records if r.get("abstract", "").strip())
    no_abs = total - with_abs
    no_title = sum(1 for r in records if not r.get("title", "").strip())
    no_auth = sum(1 for r in records if not r.get("authors_raw", "").strip())
    schedule_only = sum(1 for r in records if "schedule-only" in r.get("qa_flags", []))

    lines.append(f"## Summary\n\n")
    lines.append(f"| Metric | Count |\n|--------|-------|\n")
    lines.append(f"| Total records | {total} |\n")
    lines.append(f"| With abstract | {with_abs} |\n")
    lines.append(f"| No abstract (schedule-only or missing) | {no_abs} |\n")
    lines.append(f"| No title | {no_title} |\n")
    lines.append(f"| No authors | {no_auth} |\n")
    lines.append(f"| Schedule-only entries | {schedule_only} |\n")
    lines.append("\n")

    # Per-year summary
    lines.append("## Per-year counts\n\n")
    lines.append("| Year | Total | With abstract | Flags |\n")
    lines.append("|------|-------|--------------|-------|\n")
    from collections import Counter
    year_groups: dict[int, list[dict]] = {}
    for r in records:
        year_groups.setdefault(r["year"], []).append(r)
    for yr in sorted(year_groups):
        yrecs = year_groups[yr]
        wabs = sum(1 for r in yrecs if r.get("abstract", "").strip())
        flag_counts: Counter[str] = Counter()
        for r in yrecs:
            for f in r.get("qa_flags", []):
                flag_counts[f] += 1
        flag_str = ", ".join(f"{k}:{v}" for k, v in sorted(flag_counts.items())
                             if k not in {"schedule-only", "no-abstract"}) or ""
        lines.append(f"| {yr} | {len(yrecs)} | {wabs} | {flag_str} |\n")
    lines.append("\n")

    # Entries needing manual review
    lines.append("## Entries needing review\n\n")
    issues = [r for r in records if not r.get("title") or not r.get("authors_raw")
              or r.get("confidence") == "low"
              or "abstract-too-short" in r.get("qa_flags", [])]
    if issues:
        lines.append("| Citekey | Year | Issues |\n|---------|------|--------|\n")
        for r in issues[:100]:  # cap at 100 for readability
            ck = citekeys.get(f"{r['year']}_{r['entry_id']}", "?")
            flags = ", ".join(r.get("qa_flags", []))
            lines.append(f"| {ck} | {r['year']} | {flags} |\n")
        if len(issues) > 100:
            lines.append(f"\n_(showing first 100 of {len(issues)} flagged entries)_\n")
    else:
        lines.append("No entries flagged for review.\n")

    QA_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"QA report → {QA_FILE}")


# ── main ──────────────────────────────────────────────────────────────────────

def load_records() -> list[dict]:
    decoder = json.JSONDecoder()
    content = RECORDS_FILE.read_text(encoding="utf-8")
    records: list[dict] = []
    pos = 0
    while pos < len(content):
        while pos < len(content) and content[pos] in " \t\n\r":
            pos += 1
        if pos >= len(content):
            break
        obj, end = decoder.raw_decode(content, pos)
        records.append(obj)
        pos = end
    return records


def apply_corrections(records: list[dict]) -> tuple[list[dict], int, int]:
    """Apply manual overrides from corrections.jsonl.

    Each line is a JSON object of one of these shapes:
      Field patch: {"year": N, "entry_id": "T5", "field": "title", "value": "..."}
      Multi-field: {"year": N, "entry_id": "T5", "patch": {"title": "...", "authors_raw": "..."}}
      Add new:     {"year": N, "entry_id": "T999", "add": true, ...record fields...}
      Delete:      {"year": N, "entry_id": "T5", "delete": true}

    Returns (records, patched_count, deleted_count). Records not matched in
    the input are silently skipped (logged).
    """
    if not CORRECTIONS_FILE.exists():
        return records, 0, 0

    by_key: dict[tuple[int, str], dict] = {(r["year"], r["entry_id"]): r for r in records}
    patched = 0
    deleted = 0
    to_delete: set[tuple[int, str]] = set()
    to_add: list[dict] = []

    with CORRECTIONS_FILE.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            try:
                op = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"  corrections.jsonl line {line_no}: invalid JSON ({e})")
                continue
            key = (op.get("year"), op.get("entry_id"))
            if op.get("delete"):
                to_delete.add(key)
                deleted += 1
                continue
            if op.get("add"):
                # Required fields: year, entry_id; rest as provided
                new_rec = {k: v for k, v in op.items() if k not in ("add",)}
                new_rec.setdefault("presentation_type", "talk")
                new_rec.setdefault("authors_raw", "")
                new_rec.setdefault("title", "")
                new_rec.setdefault("abstract", "")
                new_rec.setdefault("parser_format", "manual_correction")
                new_rec.setdefault("confidence", "manual")
                new_rec.setdefault("qa_flags", [])
                to_add.append(new_rec)
                # Also expose immediately to by_key so later patches can target it
                by_key[key] = new_rec
                continue
            rec = by_key.get(key)
            if not rec:
                print(f"  corrections.jsonl line {line_no}: no record for "
                      f"year={op.get('year')} entry_id={op.get('entry_id')}")
                continue
            if "patch" in op:
                for k, v in op["patch"].items():
                    rec[k] = v
                patched += 1
            elif "field" in op:
                rec[op["field"]] = op.get("value", "")
                patched += 1
            # Recompute qa_flags after edits (drop flags that no longer apply)
            flags = list(rec.get("qa_flags", []))
            if rec.get("abstract", "").strip() and "no-abstract" in flags:
                flags.remove("no-abstract")
            if rec.get("authors_raw", "").strip() and "no-authors" in flags:
                flags.remove("no-authors")
            if rec.get("title", "").strip() and "no-title" in flags:
                flags.remove("no-title")
            rec["qa_flags"] = flags

    if to_delete:
        records = [r for r in records if (r["year"], r["entry_id"]) not in to_delete]
    if to_add:
        records.extend(to_add)

    return records, patched, deleted


def main() -> None:
    records = load_records()
    print(f"Loaded {len(records)} records")

    records, patched, deleted = apply_corrections(records)
    if patched or deleted:
        print(f"Applied {patched} corrections, deleted {deleted} records — "
              f"{len(records)} records remain")

    used_keys: set[str] = set()
    citekey_map: dict[str, str] = {}
    bib_entries: list[str] = []

    for r in sorted(records, key=lambda x: (x.get("year", 0), x.get("entry_id", ""))):
        ck = make_citekey(r, used_keys)
        citekey_map[f"{r['year']}_{r['entry_id']}"] = ck
        entry = record_to_bib(r, ck)
        bib_entries.append(entry)

    header = (
        "% Dalhousie Department of Psychology & Neuroscience\n"
        "% Annual In-House Conference proceedings, 1975–2025\n"
        "% Generated by pipeline/03_export_bib.py\n"
        "% Total entries: " + str(len(bib_entries)) + "\n\n"
    )
    BIB_FILE.write_text(header + "\n".join(bib_entries), encoding="utf-8")
    print(f"Wrote {len(bib_entries)} entries → {BIB_FILE}")

    write_qa_report(records, citekey_map)


if __name__ == "__main__":
    main()
