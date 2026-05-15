#!/usr/bin/env python3
"""
Stage 2: Parse extracted text files into structured records.

Reads every file in ../extracted/, parses presentation entries, and writes
../records.jsonl with one JSON object per presentation.

Output fields per record:
  year, entry_id, presentation_type (talk|poster|honours_poster|special),
  authors_raw, title, abstract, source_file, parser_format, confidence, qa_flags
"""

from __future__ import annotations
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXTRACTED = ROOT / "extracted"
RECORDS_FILE = ROOT / "records.jsonl"

# ── text helpers ──────────────────────────────────────────────────────────────

def clean_ws(s: str) -> str:
    s = s.replace("\t", " ")
    s = re.sub(r" {2,}", " ", s)
    return s.strip()

def clean_block(s: str) -> str:
    lines = [clean_ws(l) for l in s.splitlines()]
    out: list[str] = []
    prev_blank = False
    for l in lines:
        if l == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(l)
            prev_blank = False
    return "\n".join(out).strip()

def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    for bad, good in [("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"),
                      ("­", ""),   # soft hyphen
                      ("–", "-"), ("—", "--"),
                      ("‘", "'"), ("’", "'"),
                      ("“", '"'), ("”", '"'),
                      (" ", " "),   # non-breaking space
                      (" ", " "),   # narrow no-break space
                      (" ", " "),   # thin space
                      (" ", " "),   # hair space
                      (" ", " "),   # figure space
                      ("​", ""),    # zero-width space
                      ("‌", ""),    # zero-width non-joiner
                      ("‍", ""),    # zero-width joiner
                      ("﻿", ""),    # BOM / zero-width nbsp
                      ]:
        s = s.replace(bad, good)
    # Drop control characters (C0 + C1, except \t \n \r) and Unicode
    # Private Use Area characters (often font-substitution glyphs in OCR).
    s = "".join(
        ch for ch in s
        if (ch in "\t\n\r"
            or (0x20 <= ord(ch) < 0x7f)            # printable ASCII
            or (0xa0 <= ord(ch) < 0xe000)          # extended Unicode (real text)
            or (0xf900 <= ord(ch) < 0xfff0))       # compatibility forms
    )
    return s

# ── entry-boundary patterns ───────────────────────────────────────────────────

# OCR character substitutions commonly seen for digits:
#   l, I, |, i  → 1
#   O, o, Q     → 0
#   S, s        → 5
#   B           → 8
#   Z, z        → 2
#   b           → 6
# We accept these in label positions and normalize back to digits below.
_OCR_DIGIT_CHARS = r"0-9OoQlI|iSsBZzb"
_OCR_DIGIT_MAP = str.maketrans({
    "O": "0", "o": "0", "Q": "0",
    "l": "1", "I": "1", "|": "1", "i": "1",
    "S": "5", "s": "5",
    "B": "8",
    "Z": "2", "z": "2",
    "b": "6",
})


def _normalize_ocr_label(label: str) -> str:
    """Map a label like 'TlO' / 'TS' / 'PI' / 'S' / 'l' to its true form
    'T10' / 'T5' / 'P1' / '5' / '1'. Keeps the prefix (T/P/HP/SS) as-is;
    translates OCR letter-digits in the suffix."""
    s = label.strip()
    m = re.match(r"^(HP|SS|[TP])(.*)$", s, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        suffix = m.group(2).translate(_OCR_DIGIT_MAP)
        suffix = re.sub(r"\D", "", suffix)
        return prefix + suffix if suffix else s
    # No prefix → plain numeric label, possibly with OCR letters
    translated = s.translate(_OCR_DIGIT_MAP)
    digits = re.sub(r"\D", "", translated)
    return digits or s


# T1)  P2)  HP3)  SS4)  (parenthesis delimiter). Accept OCR digit lookalikes.
# Allow optional whitespace between prefix letter and digits ("T 14)").
_ENTRY_PAREN = re.compile(
    rf"(?m)^[ \t]*(?P<label>(?:HP|SS|[TP])\s*[{_OCR_DIGIT_CHARS}]{{1,3}})\s*\)\s*",
    re.IGNORECASE,
)

# T1.  P2.  (period delimiter)
_ENTRY_DOT = re.compile(
    rf"(?m)^[ \t]*(?P<label>(?:HP|SS|[TP])\s*[{_OCR_DIGIT_CHARS}]{{1,3}})\s*\.\s*",
    re.IGNORECASE,
)

# T1:  P2:  (colon delimiter – 2018 format)
_ENTRY_COLON = re.compile(
    rf"(?m)^[ \t]*(?P<label>(?:HP|SS|[TP])\s*[{_OCR_DIGIT_CHARS}]{{1,3}})\s*:\s*",
    re.IGNORECASE,
)

# Plain numbers: 1.  2,  3-  (period, comma, or dash – handles OCR variation).
# Years indent the marker (1978 ≈ 12 spaces, 1990 ≈ 20 spaces). Allow up to 32.
# Allow OCR digit lookalikes (S=5, l=1, I=1, O=0, …); we further restrict to
# paragraph-break positions via _plain_num_filter to avoid false matches
# inside abstracts (e.g. "S. Adamo" as a name reference). Look-ahead accepts
# both upper- and lower-case first letter of the author name (OCR can flip case).
_PLAIN_NUM = re.compile(
    rf"(?m)^[ \t]{{0,32}}(?P<label>[{_OCR_DIGIT_CHARS}]{{1,2}})[.,\-]\s+(?=[A-Za-z])"
)


def _plain_num_filter(matches: list[re.Match], text: str) -> list[re.Match]:
    """For plain-numbered markers (OCR-letter variants of digits): only keep
    matches at a paragraph break — start of file or preceded by `\\n\\n`.
    Pure-digit labels are always kept (preserves existing behaviour for
    years with reliable OCR)."""
    kept: list[re.Match] = []
    for m in matches:
        label = m.group("label").strip()
        start = m.start()
        is_digit = label.isdigit()
        at_para_start = (start == 0
                         or text[max(0, start - 2):start] == "\n\n"
                         or (start >= 1 and text[start - 1] == "\n"
                             and (start < 2 or text[start - 2] == "\n")))
        if is_digit or at_para_start:
            kept.append(m)
    return kept

# HP#  on a line by itself (for 2019 schedule-only)
_ENTRY_BARE = re.compile(r"(?m)^(?P<label>(?:HP|SS|[TP])\d+)\s*$", re.IGNORECASE)

# Asterisk separator line (2008 submission-form format)
_STAR_SEP = re.compile(r"(?m)^\*{3,}\s*$")

# 2008 submission-form trailers — strip these and everything after
_2008_TRAILER_RE = re.compile(
    r"(?im)^\s*(?:PRESENTATION\s+FORMAT|TIMES?/?\s*DAY\s+NOT\s+AVAILABLE|"
    r"TIMES?\s*/?\s*DAYS?\s+UNAVAILABLE|EQUIPMENT\s*/?\s*SOFTWARE\s+REQUIRED|"
    r"AVAILABILITY\s*:)"
)
# Standalone TALK or POSTER marker (block 4 style)
_2008_END_MARKER_RE = re.compile(r"(?im)^\s*(TALK|POSTER)\s*$")
# Leading "PRESENTATION TYPE: ..." line (block 12 style)
_2008_LEAD_PT_RE = re.compile(r"(?im)\A\s*PRESENTATION\s+TYPE\s*:[^\n]*\n+")


def _strip_2008_trailers(block: str) -> tuple[str, str | None]:
    """Strip submission-form trailer lines from a 2008 block.

    Returns (cleaned_block, detected_presentation_type).
    Detected type is 'talk', 'poster', or None.
    """
    pt: str | None = None
    # Detect presentation type from full block first
    m = re.search(r"(?im)Presentation\s+(?:format|type)\s*:?\s*[\t _]*"
                  r"(?:Talk\s*[_x\*\s]*?\s*[xX]\s*[_\s]*Poster"
                  r"|Talk\s*[_x\*\s]*[xX]"
                  r"|Talk\s*(?=$|\n|\.|\s))", block)
    if m:
        pt = "talk"
    m = re.search(r"(?im)Presentation\s+(?:format|type)\s*:?\s*"
                  r"(?:Talk\s*[_\s]*Poster\s*[_x\*\s]*[xX]"
                  r"|Poster\s*[_x\*\s]*[xX]"
                  r"|Poster\s*(?=$|\n|\.|\s))", block)
    if m:
        pt = "poster"
    # Bare "TALK"/"POSTER" line
    em = _2008_END_MARKER_RE.search(block)
    if em and pt is None:
        pt = em.group(1).lower()

    # Now strip trailers
    block = _2008_LEAD_PT_RE.sub("", block)
    tm = _2008_TRAILER_RE.search(block)
    if tm:
        block = block[:tm.start()].rstrip()
    em2 = _2008_END_MARKER_RE.search(block)
    if em2:
        block = block[:em2.start()].rstrip()
    return block, pt


def _label_sort_key(label: str) -> tuple[str, int] | None:
    """Decompose a label into (prefix, number) for monotonicity checks.
    Handles plain numbers ('5'), T#/P#/HP#/SS# (incl. OCR letter forms).
    Returns None if the label cannot be parsed as a numbered entry marker.
    """
    s = label.strip()
    if not s:
        return None
    # T#, P#, HP#, SS# — allow OCR digit lookalikes
    m = re.match(r"^(HP|SS|[TP])\s*([0-9OoQlI|iSsBZzb]{1,3})$", s, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        digits = m.group(2).translate(_OCR_DIGIT_MAP)
        digits = re.sub(r"\D", "", digits)
        if digits:
            return (prefix, int(digits))
    # Plain numeric
    if s.isdigit():
        return ("", int(s))
    return None


def _label_to_int(label: str) -> int | None:
    """Translate an OCR-tolerant label (digits + lookalikes) to an int.
    Returns None if no digits can be extracted."""
    s = label.strip().translate(_OCR_DIGIT_MAP)
    s = re.sub(r"\D", "", s)
    return int(s) if s else None


def _monotonic_filter(matches: list[re.Match]) -> list[re.Match]:
    """Placeholder retained for plain-numeric labels. Previously dropped
    non-monotonic markers as OCR phantoms; that approach broke files with a
    table-of-contents at the top (e.g. 1985), where TOC labels precede the
    real (in-order) entries. We now rely on `_plain_num_filter` to confine
    matches to paragraph-break positions and `deduplicate_blocks` to keep
    the longest block per label."""
    return matches


def split_into_blocks(text: str, pattern: re.Pattern) -> list[tuple[str, str]]:
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    # If this is _PLAIN_NUM (plain-numeric labels): drop OCR-letter matches
    # that aren't at paragraph breaks (avoid in-abstract false positives).
    if pattern is _PLAIN_NUM:
        matches = _plain_num_filter(matches, text)
    matches = _monotonic_filter(matches)
    blocks = []
    for i, m in enumerate(matches):
        raw_label = m.group("label").strip() if "label" in m.groupdict() else m.group(0).strip()
        # Normalize OCR-degraded labels: 'TlO' → 'T10', 'PI' → 'P1', 'S' → '5'.
        label = _normalize_ocr_label(raw_label)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        blocks.append((label, clean_block(block)))
    return blocks


def _block_quality(block: str) -> tuple[int, int]:
    """Score a block for dedup preference. Real abstract blocks have a
    paragraph break (\\n\\n) and a long second paragraph. Schedule/TOC blocks
    that captured many subsequent entries are long but have no paragraph
    structure inside — they're a stream of short lines.

    Returns (has_paragraph_break, length) so paragraph-structured blocks win
    even when shorter than a sprawling schedule block.
    """
    # Has at least one paragraph break followed by ≥80 chars of content?
    has_para = 0
    parts = re.split(r"\n\s*\n", block, maxsplit=2)
    if len(parts) >= 2 and len(parts[1].strip()) >= 80:
        has_para = 1
    return (has_para, len(block))


def deduplicate_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Per label, keep the block with the best quality (paragraph-structured
    > sprawling schedule fragments), with length as tiebreaker."""
    seen: dict[str, tuple[str, str]] = {}
    for label, block in blocks:
        key = re.sub(r"[^A-Z0-9]", "", label.upper())
        if key not in seen or _block_quality(block) > _block_quality(seen[key][1]):
            seen[key] = (label, block)
    order: list[str] = []
    done: set[str] = set()
    for label, _ in blocks:
        key = re.sub(r"[^A-Z0-9]", "", label.upper())
        if key not in done:
            order.append(key)
            done.add(key)
    return [seen[k] for k in order if k in seen]


def _entry_type(label: str) -> str:
    label = label.upper().strip()
    if label.startswith("HP"):
        return "honours_poster"
    if label.startswith("SS"):
        return "special"
    if label.startswith("P"):
        return "poster"
    return "talk"


# ── field extraction heuristics ───────────────────────────────────────────────

_TITLE_STARTERS = re.compile(
    r"^(the|a|an|on|is|are|does|how|what|why|when|where|can|do|will|for|"
    r"in|of|to|from|by|effects?|role|impact|influence|relationship|use|"
    r"development|using|investigating|examining|understanding|towards?)\b"
    r"(?!\s*\.)",  # exclude "A." / "I." style author initials
    re.IGNORECASE,
)

# Words that indicate a sentence continuation, not a proper name
_SENTENCE_STARTERS = re.compile(
    r"^(these|this|our|we|here|such|they|their|thus|hence|however|moreover|"
    r"furthermore|therefore|additionally|although|because|since|while|after|"
    r"before|when|where|it|its|following|subsequent|results?|methods?|"
    r"subjects?|participants?|data|analysis|findings?|conclusion)\b",
    re.IGNORECASE,
)

# Verb forms that cannot appear in a name list
_VERB_FORMS = re.compile(
    r"\b(are|is|was|were|have|has|had|will|would|can|could|may|might|"
    r"shall|should|be|been|being|do|does|did|done|show|suggest|indicate|"
    r"found|report|present|examine|provide|describe|demonstrate|increase|"
    r"decrease|reduce|improve|affect|result|occur|involve|require|support)\b",
    re.IGNORECASE,
)


def _seg_starts_like_name(p: str) -> bool:
    """A name segment can start with an uppercase letter, OR a lowercase
    letter followed by '.' (OCR-degraded initial: 'c. Edwards')."""
    if not p:
        return True
    if p[0].isupper():
        return True
    # OCR-degraded initial: single lowercase letter followed by period
    if len(p) >= 2 and p[0].isalpha() and p[1] == ".":
        return True
    return False


def _seg_is_name(seg: str) -> bool:
    """Return True if a comma-or-and-separated segment looks like a name (list)."""
    seg = seg.strip().strip(",;.")
    if not seg:
        return True  # empty segment OK (e.g. trailing &)
    if _VERB_FORMS.search(seg):
        return False
    if _SENTENCE_STARTERS.match(seg):
        return False
    parts = [p.strip() for p in seg.split(",") if p.strip()]
    return all(
        len(p.split()) <= 6
        and not _TITLE_STARTERS.match(p)
        and not _SENTENCE_STARTERS.match(p)
        and _seg_starts_like_name(p)
        for p in parts
    )


def looks_like_authors(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 250:
        return False
    # Must have alphabetic content (rules out page numbers)
    if not re.search(r"[A-Za-z]", line):
        return False

    # Strip superscript/footnote digit annotations adjacent to commas
    # e.g. "Watt,3 Wald,4 &" → "Watt, Wald, &"
    cleaned = re.sub(r",\s*\d+\b", ",", line)
    cleaned = re.sub(r"\b\d+\s+(?=[A-Z])", "", cleaned).strip()

    words = cleaned.split()

    # Short (≤5 words): likely author if it starts with an uppercase letter
    # (or an OCR-degraded lowercase initial like 'c.') and doesn't match any
    # known title/sentence-continuation starters AND doesn't contain
    # title-style connector words.
    starts_name_like = (
        line[0].isupper()
        or (len(line) >= 2 and line[0].isalpha() and line[1] == ".")
    )
    if (len(words) <= 5
            and starts_name_like
            and not _TITLE_STARTERS.match(line)
            and not _SENTENCE_STARTERS.match(line)):
        # Reject if the line contains lowercase prepositions/connectors that
        # are typical in titles but not in name lists.
        if re.search(r'\b(?:in|of|on|the|for|with|from|by|using|under|over|'
                     r'via|about|against|despite|via|towards?|across|among|'
                     r'between|within|after|before|during|while)\b',
                     line, re.IGNORECASE):
            return False
        return True

    # "and"/"&" connector: split and verify each segment looks like a name
    if re.search(r"\band\b|\&", cleaned):
        segs = re.split(r"\s*(?:\band\b|\&)\s*", cleaned)
        if segs and all(_seg_is_name(s) for s in segs):
            return True

    # Comma-separated list: each part short and name-like
    if "," in cleaned:
        parts = [p.strip() for p in re.split(r",\s*", cleaned) if p.strip()]
        name_parts = [p for p in parts if re.search(r"[A-Za-z]", p)]
        if (2 <= len(name_parts) <= 15 and
                all(len(p.split()) <= 6
                    and not _TITLE_STARTERS.match(p)
                    and not _VERB_FORMS.search(p)
                    for p in name_parts)):
            return True

    return False


_NAME_PARTICLES = {
    "de", "von", "van", "der", "den", "du", "le", "la", "el",
    "and", "the", "of",
}


def _definitely_authors(line: str) -> bool:
    """Strict author-line check: requires comma/ampersand/'and'/initial AND
    every word starts with uppercase (excluding name particles like 'de',
    'von'). Rejects title continuations like 'Potentially Lethal Bacterium,
    Serratia marcescens' where 'marcescens' is lowercase."""
    if not looks_like_authors(line):
        return False
    if not re.search(r"[,&]|\band\b|\b[A-Z]\.", line):
        return False
    words = re.findall(r"\b[a-zA-Z][\w'\-]*\b", line)
    for w in words:
        if w.lower() in _NAME_PARTICLES:
            continue
        if w[0].islower():
            return False
    return True


def _parse_title_first(block: str) -> tuple[str, str, str]:
    """Title → Author(s) → Abstract.

    Handles both blank-line-separated paragraphs (most formats) and
    single-line-separated formats (e.g. 1995, where title/author/abstract
    are on consecutive lines with no intervening blank line).
    """
    paras = [p.strip() for p in re.split(r"\n\n+", block) if p.strip()]
    if not paras:
        return "", "", ""

    # ── Paragraph-separated case (most common) ──
    if len(paras) > 1:
        # Filter out page-number-only paragraphs (short, no alphabetic content)
        real_paras = [p for p in paras if re.search(r"[A-Za-z]", p) and len(p.strip()) > 3]
        if not real_paras:
            real_paras = paras

        # Handle first-paragraph structure
        first_para_lines = [l for l in real_paras[0].split("\n") if l.strip()]
        if len(first_para_lines) >= 3:
            # Looks like a merged title+author+abstract paragraph — use line-by-line
            merged = real_paras[0]
            remaining = "\n\n".join(real_paras[1:])
            if remaining:
                merged = merged + "\n\n" + remaining
            # Fall through to line-by-line below
            paras = [merged]
        elif len(first_para_lines) == 2 and _definitely_authors(first_para_lines[1]):
            # First para = title on line 1, authors on line 2.
            # Use stricter check to avoid mistaking a wrapped-title continuation
            # (e.g. species name "Gryllus integer") for authors.
            return (first_para_lines[0].strip(),
                    first_para_lines[1].strip(),
                    "\n\n".join(real_paras[1:]))
        else:
            title_parts = [real_paras[0]]
            authors_raw = ""
            abstract_parts: list[str] = []
            found_authors = False

            for para in real_paras[1:]:
                first_line = para.split("\n")[0]
                if not found_authors and looks_like_authors(first_line):
                    authors_raw = para
                    found_authors = True
                elif found_authors:
                    abstract_parts.append(para)
                else:
                    if len(para) < 120:
                        title_parts.append(para)
                    else:
                        abstract_parts.append(para)
                        found_authors = True

            return " ".join(title_parts), authors_raw, "\n\n".join(abstract_parts)

    # ── Single-paragraph: fall back to line-by-line ──
    lines = [l.strip() for l in paras[0].split("\n") if l.strip()]
    if not lines:
        return "", "", ""

    # Pre-scan: prefer the FIRST "definitely-authors" line as the title/author
    # boundary if one exists. This avoids promoting an ambiguous short
    # capitalised line (e.g. "School-Aged Children") into authors when a
    # clearer author line follows.
    author_boundary: int | None = None
    for i, line in enumerate(lines):
        if i > 0 and _definitely_authors(line):
            author_boundary = i
            break

    # State machine: collecting title → collecting authors → collecting abstract
    TITLE, AUTHORS, ABSTRACT = 0, 1, 2
    state = TITLE
    title_lines: list[str] = []
    author_lines: list[str] = []
    abstract_lines: list[str] = []

    for i, line in enumerate(lines):
        if state == TITLE:
            # If a confident author boundary exists, transition exactly there.
            # Otherwise, fall back to the loose looks_like_authors signal.
            if author_boundary is not None:
                if i == author_boundary:
                    state = AUTHORS
                    author_lines.append(line)
                else:
                    title_lines.append(line)
            elif title_lines and looks_like_authors(line):
                state = AUTHORS
                author_lines.append(line)
            else:
                title_lines.append(line)
        elif state == AUTHORS:
            if looks_like_authors(line):
                author_lines.append(line)
            else:
                state = ABSTRACT
                abstract_lines.append(line)
        else:
            abstract_lines.append(line)

    title = " ".join(title_lines)
    authors_raw = " ".join(author_lines)
    abstract = " ".join(abstract_lines)
    return title, authors_raw, abstract


def _truncate_at_next_entry_marker(abstract_paras: list[str]) -> list[str]:
    """Within multi-paragraph abstract content (years 1976-1991 author-first
    format), drop everything from the first paragraph that looks like an
    OCR-degraded next-entry marker — typically a short paragraph containing
    a digit and dominated by non-letter characters (the source's "4." or
    similar buried in OCR junk).
    """
    keep: list[str] = []
    for p in abstract_paras:
        s = p.strip()
        # Long enough to be real prose? keep.
        if len(s) >= 120:
            keep.append(p)
            continue
        # Short paragraph: check if it has the next-entry-marker signature
        if not s:
            keep.append(p)
            continue
        # Must contain at least one digit
        if not re.search(r"\d", s):
            keep.append(p)
            continue
        # And must have a name-like component (an initial pattern or a single
        # capitalised surname). E.g., "l 1-{<- 4 •   J.   Kruse" matches.
        if not re.search(
            r"\b[A-Z]\.\s*[A-Z][a-z]+|\b[A-Z][a-z]{2,}\s+(?:[A-Z]\.\s*)+",
            s,
        ):
            keep.append(p)
            continue
        # Low letter ratio suggests this is OCR-garbled marker, not real prose
        letters = sum(1 for c in s if c.isalpha())
        if letters / max(1, len(s)) < 0.55:
            break  # truncate here
        # If high letter ratio but very short and has author-like structure,
        # it could be a clean next-entry author paragraph — also truncate
        if len(s) < 80:
            break
        keep.append(p)
    return keep


def _parse_author_first(block: str) -> tuple[str, str, str]:
    """Author(s) → Title → Abstract.

    Multi-paragraph: Para 0 = authors, Para 1 = title, Para 2+ = abstract.
    Single-paragraph fallback: Line 0 = authors, Line 1 = title, Line 2+ = abstract.
    This handles years (e.g. 1981-1993) where no blank line separates the fields.
    """
    paras = [p.strip() for p in re.split(r"\n\n+", block) if p.strip()]
    if not paras:
        return "", "", ""

    if len(paras) >= 2:
        # 1985 quirk: paragraph 0 may contain BOTH authors (line 1) and title
        # (line 2+), with only a \n between them — no blank line. Detect and
        # peel the title into a new paragraph slot.
        p0_lines = [l for l in paras[0].splitlines() if l.strip()]
        if len(p0_lines) >= 2 and looks_like_authors(p0_lines[0]):
            authors_raw = p0_lines[0].strip()
            title = " ".join(l.strip() for l in p0_lines[1:])
            abstract_paras = paras[1:]
        else:
            authors_raw = paras[0]
            title = paras[1]
            abstract_paras = paras[2:]
        # Truncate the abstract at the first paragraph that looks like a
        # next-entry marker (short, has a digit, low letter ratio).
        abstract_paras = _truncate_at_next_entry_marker(abstract_paras)
        abstract = "\n\n".join(abstract_paras)
        # 1985-1994 quirk: title paragraph may include the abstract because
        # they're at different indent levels but separated by a single line break.
        # If we got no abstract and the title is multi-line, try splitting where
        # the line style shifts from title-case/caps to sentence prose.
        if not abstract and "\n" in title:
            t_lines = title.splitlines()
            # First line of title is the heading style; classify subsequent
            # lines by comparison
            first_caps = t_lines[0].strip().isupper() if t_lines else False
            split_at = None
            for i, ln in enumerate(t_lines):
                if i == 0:
                    continue
                s = ln.strip()
                if not s:
                    continue
                is_all_caps = s.isupper()
                # Style shift from ALL-CAPS title to mixed-case prose
                if first_caps and not is_all_caps:
                    split_at = i
                    break
                # Abstract-style: prose tells
                if (s[0].islower() or len(s) > 70
                        or re.match(r"^(?:The|This|These|Our|We|It|In|A|An|"
                                    r"Although|Because|Since|While|Studies?|"
                                    r"Studied|Research|Previous|Recent|"
                                    r"Subjects?|Participants?|Results?|Data)\s", s)):
                    split_at = i
                    break
            if split_at is not None:
                new_title = " ".join(l.strip() for l in t_lines[:split_at]).strip()
                new_abstract = " ".join(l.strip() for l in t_lines[split_at:]).strip()
                if new_title and new_abstract:
                    title = new_title
                    abstract = new_abstract
        return title, authors_raw, abstract

    # Single paragraph — fall back to line-by-line split
    lines = [l.strip() for l in paras[0].split("\n") if l.strip()]
    if not lines:
        return "", "", ""
    authors_raw = lines[0]
    # Title: lines 1 and 2 (titles sometimes wrap to a second line)
    title = " ".join(lines[1:3]) if len(lines) > 1 else ""
    abstract = " ".join(lines[3:]) if len(lines) > 3 else ""
    return title, authors_raw, abstract


def _parse_inline_early(block: str) -> tuple[str, str, str]:
    """
    1976-1980 inline formats:
      dash   (1976-1979): 'Author - Title\\n\\nAbstract'
      period (1980):      'Author. Title\\n\\nAbstract'
    Falls back to _parse_author_first if neither pattern matches.
    """
    lines = block.strip().splitlines()
    if not lines:
        return "", "", ""
    first = clean_ws(lines[0])
    rest_lines = lines[1:]

    # Dash separator (1976-1979): "Author - Title"
    m = re.match(r"^(.+?)\s+[-–]\s+(.+)$", first)
    if m:
        authors_raw = m.group(1).strip()
        title_start = m.group(2).strip()
    else:
        # Period separator (1980): last period that is followed by a capital letter
        # e.g. "R. Klein.  Does Saccadic..." or "G.V. Goddard et al.  Evidence..."
        # Use greedy match so (.+) reaches the LAST viable period.
        m = re.match(r"^(.+)\.\s+([A-Z].*)$", first)
        if m:
            authors_raw = m.group(1).strip()
            title_start = m.group(2).strip()
        else:
            return _parse_author_first(block)

    # Reassemble: title_start + any continuation lines, then split into paras
    remainder = title_start
    if rest_lines:
        remainder += "\n" + "\n".join(rest_lines)
    paras = [p.strip() for p in re.split(r"\n\n+", remainder) if p.strip()]
    title = paras[0] if paras else ""
    abstract = "\n\n".join(paras[1:]) if len(paras) > 1 else ""
    return title, authors_raw, abstract


# Keep old name as alias so nothing else breaks
_parse_inline_1976 = _parse_inline_early


_TITLE_CONNECTOR = re.compile(
    r"^(with|without|of|in|at|by|for|from|to|on|and|or|the|a|an|after|"
    r"before|during|while|between|among|within|across|via|under|over|"
    r"using|through|about|against|around|despite|following|regarding)\b",
    re.IGNORECASE,
)


def _rescue_authors_from_title(title: str, year: int = 9999) -> tuple[str, str]:
    """
    Fix 1.4: peel an author-list suffix from a concatenated title+author string.

    Only runs for title-first format years (≥ 1994), where title and authors
    sometimes end up on the same line.  Requires:
      - suffix starts with an uppercase letter (proper name)
      - suffix contains ≥ 1 comma (multiple names)
      - the word immediately before the suffix is NOT a title connector word
      - the remaining prefix is ≥ 25 chars
    """
    if year < 1994:
        return title, ""
    if len(title) < 50:
        return title, ""
    words = title.split()
    if len(words) < 6:
        return title, ""

    best = None
    for n in range(2, min(len(words) - 3, 16)):
        suffix = " ".join(words[-n:])
        prefix = " ".join(words[:-n])
        if len(prefix) < 25:
            break

        # Suffix must start with an uppercase letter (proper name, not sentence cont.)
        if not suffix[0].isupper():
            continue

        # The word just before the split should not be a connector (preposition etc.)
        # — if it is, the suffix is likely a title continuation, not authors
        pivot_word = words[-(n + 1)] if n + 1 < len(words) else ""
        if _TITLE_CONNECTOR.match(pivot_word):
            continue

        if "," in suffix and looks_like_authors(suffix):
            best = n
        elif best is not None:
            break

    if best is not None:
        return " ".join(words[:-best]).rstrip(","), " ".join(words[-best:])
    return title, ""


_AFFIL_KEYWORD = re.compile(
    r'(?i)\b(?:Departments?|Dept\.?|Universit(?:y|ies)|Institutes?|Hospitals?|'
    r'Facult(?:y|ies)|Schools?|Centres?|Centers?|Laborator(?:y|ies)|'
    r'Psychology|Psychiatry|Pharmacology|Anatomy|Physiology|Biology|'
    r'Chemistry|Neurology|Neuroscience|Neurobiology|'
    r'Halifax|Toronto|Montreal|Boston|Madrid|Spain|U\.S\.A\.|USA|'
    r'Canada|France|Germany|Italy|Japan|Sweden|Mexico|U\.K\.|'
    r'Nova\s+Scotia|Ontario|Quebec|New\s+York|Cambridge|Oxford)\b'
)


_TITLE_PROSE_MARKER = re.compile(
    r'\b(we\s+(?:found|examined|present|investigated|conducted|tested|hypothesi[sz]ed|'
    r'observed|report|propose|developed|studied|analy[sz]ed|measured)|'
    r'the\s+present\s+(?:study|paper|experiment|investigation|research)|'
    r'in\s+(?:this|the\s+present)\s+(?:study|paper|experiment)|'
    r'results?\s+(?:showed|indicate|suggest|demonstrated)|'
    r'these\s+(?:results?|findings?|data)|'
    r'our\s+(?:results?|findings?|data|study)|'
    r'this\s+study\s+(?:examined|tested|investigated)|'
    r'(?:has|have)\s+been\s+(?:shown|demonstrated|reported))\b',
    re.IGNORECASE,
)


def _split_overlong_title(title: str, abstract: str) -> tuple[str, str]:
    """If title runs > 220 chars and contains abstract-style prose, split it
    at the first sentence boundary that precedes the prose marker.
    Returns possibly-modified (title, abstract).
    """
    if len(title) < 220:
        return title, abstract
    # Try newline split first
    if "\n" in title:
        head, tail = title.split("\n", 1)
        head, tail = head.strip(), tail.strip()
        if 20 < len(head) < 220 and tail and _TITLE_PROSE_MARKER.search(tail):
            new_abs = tail + ("\n\n" + abstract if abstract else "")
            return head, new_abs
    # Find prose marker position; split at sentence end before it
    pm = _TITLE_PROSE_MARKER.search(title)
    if not pm:
        return title, abstract
    # Find last sentence-ending punctuation before the prose marker
    head_zone = title[:pm.start()]
    # Look for ". " or "? " or "! " followed by capital letter or end
    boundary = None
    for m in re.finditer(r"[.!?]\s+", head_zone):
        if 20 < m.end() < 220:
            boundary = m.end()
    if boundary is None:
        # Try just the first ". " / "? " / "! " in title under 220 chars
        m = re.search(r"[.!?]\s+", title[:220])
        if m and m.end() > 20:
            boundary = m.end()
    if boundary is None:
        return title, abstract
    head = title[:boundary].strip().rstrip(".!?")
    tail = title[boundary:].strip()
    if not head or not tail:
        return title, abstract
    new_abs = tail + ("\n\n" + abstract if abstract else "")
    return head, new_abs


def normalize_authors(authors: str) -> str:
    """Clean up authors_raw: uppercase lowercase initials, strip digit
    footnotes attached to names, truncate at first affiliation/place marker."""
    if not authors:
        return authors
    s = authors
    # 1. Uppercase lowercase initials: "v." → "V." (single lowercase letter
    #    followed by a period, at start or after whitespace/comma/separator)
    s = re.sub(r'(?:(?<=^)|(?<=[\s,;&/\-]))([a-z])(?=\.)',
               lambda m: m.group(1).upper(), s)
    # 2. Strip digit footnotes attached to names (no space): "Brown1,2" → "Brown"
    s = re.sub(r'(?<=[a-zA-Z])\d+(?:\s*,\s*\d+)*', '', s)
    # 2b. Strip whitespace-separated digit footnotes: "Dastur 1," → "Dastur,"
    #     (only when preceded by a letter and followed by comma/end/separator)
    s = re.sub(r'(?<=[a-zA-Z])\s+\d+(?=[\s,;&]|$)', '', s)
    # 2c. Strip parenthesized affiliation/place markers: "Vieira (Universidade ...)" → "Vieira"
    s = re.sub(r'\s*\([^()]*\)', '', s)
    # 3. Truncate at first affiliation keyword (before the punctuation that
    #    introduces it, if any).
    boundary: int | None = None
    if m := _AFFIL_KEYWORD.search(s):
        prefix = s[:m.start()]
        # back off through trailing whitespace/comma/semicolon to find a clean cut
        bk = len(prefix.rstrip())
        prefix_stripped = prefix[:bk]
        last_sep = max(prefix_stripped.rfind(','), prefix_stripped.rfind(';'))
        boundary = last_sep if last_sep != -1 else m.start()
    # 4. Truncate at first standalone 3+ digit cluster (zipcode/address)
    if dm := re.search(r'\b\d{3,}\b', s):
        prefix = s[:dm.start()]
        last_sep = max(prefix.rfind(','), prefix.rfind(';'))
        addr_boundary = last_sep if last_sep != -1 else dm.start()
        if boundary is None or addr_boundary < boundary:
            boundary = addr_boundary
    if boundary is not None:
        s = s[:boundary]
    # 5. Final cleanup
    s = re.sub(r'\s{2,}', ' ', s)
    s = re.sub(r'\s+([,;])', r'\1', s)
    return s.strip().strip(',;.')


def _rescue_authors_from_title_newline(title: str) -> tuple[str, str]:
    """If title contains an embedded newline and the line after looks like
    authors (optionally followed by trailing OCR garble), peel them out.

    Returns (cleaned_title, authors) or (title, "") if no rescue.
    """
    if "\n" not in title:
        return title, ""
    parts = title.split("\n", 1)
    head = parts[0].strip()
    tail = parts[1].strip()
    if not head or not tail:
        return title, ""
    # The tail's first chunk before any obvious junk (e.g. " - I I j/ f") is
    # the candidate author line. Trim trailing OCR-like garble.
    cand = re.split(r"\s+[-–]\s+\S{0,3}\s+", tail, maxsplit=1)[0]
    cand = re.sub(r"\s*[\\/{}|*][^a-zA-Z]*$", "", cand).strip()
    cand = re.sub(r"\s+\S{0,2}$", "", cand).strip()  # strip stray 1-2 char trailing tokens
    if not cand:
        return title, ""
    if looks_like_authors(cand):
        return head, cand
    return title, ""


# Author-list signal: initials-style name at start of text
_AUTHOR_LIST_START = re.compile(
    r'^\s*[A-Z]\.\s*(?:[A-Z]\.?\s*)?[A-Z][a-z]{2,}'  # F. M. Lastname / F. Lastname
    r'|^\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)+\s+[A-Z][a-z]+'  # Firstname M. Lastname
)
# Comma/ampersand-separated multi-name pattern
_AUTHOR_LIST_MULTI = re.compile(
    r'[A-Z][a-z]+(?:\s+[A-Z]\.?)*(?:\s+[A-Z][a-z]+)?\s*[,&](?:\s*[A-Z])'
)


def _looks_like_author_list_head(text: str) -> bool:
    """Stronger signal than `looks_like_authors`: first line/paragraph of
    text has a comma-or-&-separated name-list pattern, with initials or
    an affiliation marker nearby."""
    if not text:
        return False
    first_line = text.split("\n", 1)[0]
    if len(first_line) > 300 or len(first_line) < 8:
        return False
    # Must contain a list separator
    if not re.search(r'[,&;]|\band\b', first_line, re.IGNORECASE):
        return False
    # Must start with capital letter
    if not re.match(r'^\s*[A-Z]', first_line):
        return False
    # Must not look like prose
    if re.match(r'^\s*(?:The|We|This|These|Our|It|In|A|An|Although|Because|'
                r'Since|While|Studies?|Research|Results?|Subjects?|Participants?|'
                r'Data|Methods?|Analysis|Findings?)\s', first_line):
        return False
    # Heuristic: initials present anywhere in first 300 chars, OR an affiliation
    # word appears in the first 400 chars
    head = text[:400]
    has_initial = bool(re.search(r'\b[A-Z]\.', head))
    has_affil = bool(re.search(
        r'\b(?:Departments?|Universit(?:y|ies)|Institutes?|Hospitals?|'
        r'Facult(?:y|ies)|Schools?|Laborator(?:y|ies)|Centres?|Centers?)\b',
        head, re.IGNORECASE))
    return has_initial or has_affil


def _rescue_swap_title_continuation(title: str, authors_raw: str, abstract: str,
                                    year: int) -> tuple[str, str, str]:
    """If title got truncated at a line-wrap, with the continuation parked in
    authors_raw and the REAL authors at the head of the abstract, swap them.

    Signal:
      • authors_raw is short, with no comma/ampersand/'and' separators
        (single phrase rather than a real name list)
      • abstract starts with an initials-style author list (commas or
        affiliation markers)
    """
    if year < 1990 or not authors_raw or not abstract:
        return title, authors_raw, abstract
    # authors_raw should be a single short phrase, NOT a real list
    if re.search(r'[,&]|\band\b', authors_raw, re.IGNORECASE):
        return title, authors_raw, abstract
    if len(authors_raw.split()) > 5:
        return title, authors_raw, abstract
    if not _looks_like_author_list_head(abstract):
        return title, authors_raw, abstract
    # Pull authors from abstract head: first paragraph up to a blank line
    paras = re.split(r'\n\s*\n', abstract, maxsplit=1)
    head_para = paras[0]
    rest = paras[1] if len(paras) > 1 else ""
    # If head paragraph is very long, just take its first 2-3 lines (authors +
    # 1-2 affiliation lines)
    if len(head_para) > 400:
        return title, authors_raw, abstract
    new_title = (title + " " + authors_raw).strip()
    new_authors = head_para.strip()
    new_abstract = rest.strip()
    return new_title, new_authors, new_abstract


def _rescue_authors_from_abstract(abstract: str, year: int = 9999) -> tuple[str, str]:
    """If the abstract begins with a paragraph that looks like an author list
    (sometimes with affiliations), peel it out.

    Returns (cleaned_abstract, authors) or (abstract, "") if no rescue.
    """
    if not abstract or year < 1990:
        return abstract, ""

    paras = re.split(r"\n\s*\n", abstract, maxsplit=2)
    if len(paras) < 2:
        return abstract, ""
    first = paras[0].strip()
    if len(first) > 600:
        return abstract, ""

    lines = [l.strip() for l in first.splitlines() if l.strip()]
    if not lines:
        return abstract, ""

    # Candidate 1: first line alone
    line1 = lines[0]
    if looks_like_authors(line1):
        return "\n\n".join(paras[1:]), line1

    # Candidate 2: first paragraph joined (handles wrapped author lists)
    joined = " ".join(lines)
    # Truncate trailing affiliation text at "Department"/"Departments"/"School of"
    head = re.split(r"\s+(?:Department|Departments|School\s+of|Faculty\s+of|"
                    r"Institute\s+of|Centre\s+for|Center\s+for|University\s+of)",
                    joined, maxsplit=1)[0].strip()
    if head and head != joined and looks_like_authors(head):
        return "\n\n".join(paras[1:]), head
    if looks_like_authors(joined[:250]):
        return "\n\n".join(paras[1:]), joined

    return abstract, ""


# ── non-research filter ───────────────────────────────────────────────────────

_NON_RESEARCH_RE = re.compile(
    r"""(?ix)\b(
        introduction\s+and\s+(brief\s+)?history
        | brief\s+history\s+of\s+(the\s+)?convention
        | opening\s+remarks
        | welcome\s+to\s+the\s+(conference|convention)
        | closing\s+remarks
        | concluding\s+remarks
        | student\s+jeopardy
        | coffee\s+break
        | lunch\s+break
        | dinner\s+and\s+reception
        | awards?\s+ceremony
        | town\s+hall
        | historica[l]\s+(introduction|overview)
        | history\s+of\s+(the\s+)?(in[\s-]?house|conference|convention)
        | introduction\s+(to|and)\s+(the\s+)?(in[\s-]?house|conference|convention)
        | session\s+[A-Z]+\s+chair  # 1975: session markers leaked as entries
        | social\s+hour
    )\b""",
    re.VERBOSE | re.IGNORECASE,
)

# Standalone short non-research titles (whole-string match, not phrase search)
_NON_RESEARCH_STANDALONE = re.compile(
    r"^\s*(?:Coffee|Lunch|Dinner|Reception|Social\s+Hour|Break|Wine\s+(?:and|&)\s+Cheese)\s*$",
    re.IGNORECASE,
)


def is_non_research(title: str, abstract: str = "") -> bool:
    if not title and not abstract:
        return True
    if _NON_RESEARCH_RE.search(title or ""):
        return True
    if _NON_RESEARCH_STANDALONE.match(title or ""):
        return True
    if len((title or "").split()) <= 2 and not abstract:
        return True
    return False


def _make_record(year, label, block, author_first=False,
                 fmt="generic", title="", authors_raw="", abstract=""):
    label = re.sub(r"[^A-Z0-9]", "", label.upper())
    if not title:
        if author_first:
            title, authors_raw, abstract = _parse_author_first(block)
        else:
            title, authors_raw, abstract = _parse_title_first(block)
    title = clean_ws(title)
    authors_raw = clean_ws(re.sub(r"\n", " ", authors_raw))
    abstract = (abstract or "").strip()

    # Fix 1.4: if no author was found, try rescuing one from the title suffix
    if not authors_raw and title:
        title, authors_raw = _rescue_authors_from_title(title, year=year)
        title = clean_ws(title)
        authors_raw = clean_ws(authors_raw)

    # Additional rescue: title with embedded newline → second line is authors
    if not authors_raw and title and "\n" in title:
        title2, authors2 = _rescue_authors_from_title_newline(title)
        if authors2:
            title = clean_ws(title2)
            authors_raw = clean_ws(authors2)

    # Additional rescue: authors live in the first paragraph of the abstract
    if not authors_raw and abstract:
        abstract2, authors3 = _rescue_authors_from_abstract(abstract, year=year)
        if authors3:
            abstract = abstract2
            authors_raw = clean_ws(authors3)

    # Rescue: title got line-wrapped, "authors" is really title continuation,
    # and real authors are at head of abstract
    if title and authors_raw and abstract:
        title, authors_raw, abstract = _rescue_swap_title_continuation(
            title, authors_raw, abstract, year)
        title = clean_ws(title)
        authors_raw = clean_ws(re.sub(r"\n", " ", authors_raw))

    # Final author normalization: strip digit footnotes, affiliations, fix case
    if authors_raw:
        authors_raw = normalize_authors(authors_raw)

    # Split overlong titles that contain abstract-style prose
    if title and len(title) > 220:
        title, abstract = _split_overlong_title(title, abstract)
        title = clean_ws(title)

    # Final title cleanup: collapse newlines (any author-rescue that needs
    # the \n boundary has already run; remaining \n is a soft-wrap artifact)
    if title and "\n" in title:
        title = clean_ws(re.sub(r"\s*\n\s*", " ", title))

    if is_non_research(title, abstract):
        return None
    flags: list[str] = []
    if not abstract:
        flags.append("no-abstract")
    elif 0 < len(abstract) < 60:
        # Suspiciously short — likely truncated by a cleanup pass; flag for review
        flags.append("abstract-too-short")
    if not title:
        flags.append("no-title")
    if not authors_raw:
        flags.append("no-authors")
    return {
        "year": year,
        "entry_id": label,
        "presentation_type": _entry_type(label),
        "authors_raw": authors_raw,
        "title": title,
        "abstract": abstract,
        "parser_format": fmt,
        "confidence": "low" if len(flags) > 1 else ("medium" if flags else "high"),
        "qa_flags": flags,
    }


# ── format-specific parsers ───────────────────────────────────────────────────

def parse_1975(year: int, text: str) -> list[dict]:
    text = norm_text(text)
    time_pat = re.compile(r"(?m)^(\d{1,2}:\d{2})\s+")
    entries = []
    blocks = split_into_blocks(text, time_pat)
    for i, (label, block) in enumerate(blocks):
        block = clean_block(block)
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        first = lines[0]
        m = re.match(r"^(.+?):\s+(.+)$", first)
        if m:
            authors_raw = m.group(1).strip()
            title = m.group(2).strip()
            abstract_lines = lines[1:]
        else:
            authors_raw = first
            title = lines[1] if len(lines) > 1 else ""
            abstract_lines = lines[2:]
        abstract = " ".join(abstract_lines)
        if is_non_research(title, abstract):
            continue
        entries.append({
            "year": year, "entry_id": f"T{i+1}",
            "presentation_type": "talk",
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "1975_inline",
            "confidence": "medium" if abstract else "low",
            "qa_flags": (["no-abstract"] if not abstract else []),
        })
    return entries


def parse_numbered_plain(year: int, text: str) -> list[dict]:
    """
    1976-1992: plain numbered entries (1. 2. etc.).
    Format variants by year:
      1976-1980: inline 'Author - Title' or 'Author. Title' on one line
      1981-1992: author-first multi-paragraph
    Parse the entire document (ABSTRACTS section is not a reliable divider).
    """
    text = norm_text(text)
    author_first = True

    blocks = deduplicate_blocks(split_into_blocks(text, _PLAIN_NUM))
    # Also try T# dot in case (e.g., 1993 uses T# prefix)
    blocks_tx = deduplicate_blocks(split_into_blocks(text, _ENTRY_DOT))
    if len(blocks_tx) > len(blocks):
        blocks = blocks_tx
        author_first = (year <= 1993)

    entries = []
    for label, block in blocks:
        if not block or len(block) < 50:
            continue
        if year <= 1980:                    # Fix 1.1 & 1.2: inline format
            title, ar, abstract = _parse_inline_early(block)
        elif author_first:
            title, ar, abstract = _parse_author_first(block)
        else:
            title, ar, abstract = _parse_title_first(block)
        fmt = ("numbered_inline" if year <= 1980
               else f"numbered_{'author' if author_first else 'title'}_first")
        r = _make_record(year, label, block, fmt=fmt,
                         title=title, authors_raw=ar, abstract=abstract)
        if r:
            entries.append(r)
    return entries


def parse_tx_dot(year: int, text: str) -> list[dict]:
    """
    1993-2002: T#. format, title-first (1995+) or author-first (1993-1994).
    Parses the ENTIRE document (ABSTRACTS section is not a reliable divider).
    """
    text = norm_text(text)
    author_first = (year <= 1994)
    blocks = deduplicate_blocks(split_into_blocks(text, _ENTRY_DOT))
    entries = []
    for label, block in blocks:
        if not block or len(block) < 50:
            continue
        if author_first:
            title, ar, abstract = _parse_author_first(block)
        else:
            title, ar, abstract = _parse_title_first(block)
        r = _make_record(year, label, block,
                         fmt=f"tx_dot_{'author' if author_first else 'title'}_first",
                         title=title, authors_raw=ar, abstract=abstract)
        if r:
            entries.append(r)
    return entries


def parse_tx_paren(year: int, text: str) -> list[dict]:
    """
    2003-2017: T#) format, title-first.
    Also handles HP# for honours posters.
    Deduplicates: same T# in schedule vs abstract section → keep longest.
    """
    text = norm_text(text)
    if "TALK TITLE:" in text.upper() or "POSTER TITLE:" in text.upper():
        return parse_talk_title_format(year, text)
    blocks = deduplicate_blocks(split_into_blocks(text, _ENTRY_PAREN))
    entries = []
    for label, block in blocks:
        if not block or len(block) < 30:
            continue
        title, ar, abstract = _parse_title_first(block)
        r = _make_record(year, label, block, fmt="tx_paren_title_first",
                         title=title, authors_raw=ar, abstract=abstract)
        if r:
            entries.append(r)
    return entries


def parse_2018(year: int, text: str) -> list[dict]:
    """
    2018 PDF: tabular schedule + 'In-house Abstracts YYYY' section.
    Entries in abstract section use 'T#: Title\\nAuthor: ...\\nAbstract: ...'
    """
    text = norm_text(text)
    # Find the abstracts section
    sec_m = re.search(r"In-?house\s+Abstracts?\s+\d{4}", text, re.IGNORECASE)
    section = text[sec_m.end():] if sec_m else text
    blocks = deduplicate_blocks(split_into_blocks(section, _ENTRY_COLON))
    entries = []
    for label, block in blocks:
        if not block:
            continue
        # Structured labels in block
        title_m = re.match(r"^(?P<title>[^\n]+)", block)
        title = title_m.group("title").strip() if title_m else ""
        # Extract Author(s): line
        auth_m = re.search(r"(?i)^Authors?\s*:\s*(?P<auth>[^\n]+)", block, re.MULTILINE)
        authors_raw = auth_m.group("auth").strip() if auth_m else ""
        # Extract Abstract: text
        abs_m = re.search(r"(?i)^Abstract\s*:\s*(?P<abs>.+)", block, re.DOTALL | re.MULTILINE)
        abstract = abs_m.group("abs").strip() if abs_m else ""
        # If no structured labels: fall back to title-first
        if not authors_raw:
            title, authors_raw, abstract = _parse_title_first(block)
        r = _make_record(year, label, block, fmt="2018_colon",
                         title=title, authors_raw=authors_raw, abstract=abstract)
        if r:
            entries.append(r)
    return entries


def parse_2008(year: int, text: str) -> list[dict]:
    """
    2008 .doc: abstract submission forms separated by *** lines.
    First entry may be T1) format; others use Title:/TITLE:, Authors:/AUTHORS:,
    Summary:/Abstract:/ABSTRACT: labels (inconsistently capitalised).
    """
    text = norm_text(text)
    entries = []

    # Split by *** separator, then within each by 2+ blank lines (occasionally
    # two or three submission forms get glued without an explicit *** separator)
    raw_parts = _STAR_SEP.split(text)
    parts: list[str] = []
    for rp in raw_parts:
        # Triple-newline (≥2 blank lines) often separates merged forms; only
        # split when every sub-piece is large enough to look like a real entry.
        subparts = re.split(r"\n{3,}", rp)
        if len(subparts) > 1 and all(len(s.strip()) >= 200 for s in subparts if s.strip()):
            parts.extend(subparts)
        else:
            parts.append(rp)

    for part in parts:
        part = part.strip()
        if not part or len(part) < 80:
            continue

        # Detect T#) inline format (first entry)
        tp_m = _ENTRY_PAREN.match(part)
        if tp_m:
            label = tp_m.group("label").upper()
            block = part[tp_m.end():]
            title, ar, abstract = _parse_title_first(clean_block(block))
            r = _make_record(year, label, part, fmt="2008_tx_paren",
                             title=title, authors_raw=ar, abstract=abstract)
            if r:
                entries.append(r)
            continue

        # Structured submission form: look for TITLE: label
        title_m = re.search(r"(?i)^(?:TITLE|Title)\s*:\s*(?P<t>[^\n]+)", part, re.MULTILINE)
        auth_m = re.search(r"(?i)^(?:AUTHORS?|Investigators?)\s*:\s*(?P<a>[^\n]+)", part, re.MULTILINE)
        abs_m = re.search(r"(?i)^(?:ABSTRACT|Summary)\s*:\s*(?P<ab>.+?)(?=\n(?:TITLE|Title|AUTHORS?|Presentation\s+(?:format|type)|TIMES?\s*/?\s*DAY|EQUIPMENT)\s*:|\Z)",
                          part, re.DOTALL | re.MULTILINE)

        # Detect presentation type and strip trailers (also handles bare TALK/POSTER markers)
        cleaned_part, pt_detected = _strip_2008_trailers(part)

        if title_m:
            title = title_m.group("t").strip()
            authors_raw = auth_m.group("a").strip() if auth_m else ""
            abstract = abs_m.group("ab").strip() if abs_m else ""
            # Handle inline labels: "TITLE: x AUTHORS: y SUMMARY: z" all on one line
            if not authors_raw and re.search(r"(?i)\s+(?:AUTHORS?|Investigators?)\s*:\s*", title):
                pieces = re.split(r"(?i)\s+(?:AUTHORS?|Investigators?)\s*:\s*",
                                  title, maxsplit=1)
                title = pieces[0].strip().rstrip(".")
                rest_after_auth = pieces[1]
                # Now look for SUMMARY/ABSTRACT inline
                aspl = re.split(r"(?i)\s+(?:ABSTRACT|Summary)\s*:\s*",
                                rest_after_auth, maxsplit=1)
                authors_raw = aspl[0].strip()
                if len(aspl) > 1 and not abstract:
                    abstract = aspl[1].strip()
                # Abstract may continue on subsequent lines after the inline-label line
                if not abstract:
                    # Grab everything after the title_m line as the abstract candidate
                    tail = part[title_m.end():].strip()
                    tail, _ = _strip_2008_trailers(tail)
                    if tail:
                        abstract = tail.strip()
            # If authors or abstract missing, run heuristic on the post-TITLE remainder.
            # Layout after TITLE:line is author-first: authors paragraph, then abstract.
            if not authors_raw or not abstract:
                remainder = part[title_m.end():]
                remainder, _ = _strip_2008_trailers(remainder)
                remainder = re.sub(r"(?im)^(?:AUTHORS?|Investigators?|ABSTRACT|Summary)\s*:\s*",
                                   "", remainder)
                rem_paras = [p.strip() for p in re.split(r"\n\n+", clean_block(remainder)) if p.strip()]
                if rem_paras and not authors_raw:
                    first_para_lines = [l.strip() for l in rem_paras[0].splitlines() if l.strip()]
                    if first_para_lines and looks_like_authors(first_para_lines[0]):
                        authors_raw = first_para_lines[0]
                if not abstract and len(rem_paras) >= 2:
                    abstract = "\n\n".join(rem_paras[1:])
        else:
            # Unlabelled block: strip trailers and use title-first heuristic parsing.
            # Also strip "By " prefix from author candidates ("By Ron Hoffman and ...")
            cleaned_no_by = re.sub(r"(?m)^By\s+(?=[A-Z])", "", cleaned_part)
            title, authors_raw, abstract = _parse_title_first(clean_block(cleaned_no_by))

        # Clean residual trailer noise from abstract
        if abstract:
            abstract, _ = _strip_2008_trailers(abstract)
            abstract = abstract.strip()

        pres_type = pt_detected or "talk"
        idx = len(entries) + 1
        label = f"T{idx}" if pres_type == "talk" else f"P{idx}"

        if is_non_research(title, abstract):
            continue
        flags = []
        if not abstract:
            flags.append("no-abstract")
        if not authors_raw:
            flags.append("no-authors")
        entries.append({
            "year": year, "entry_id": label,
            "presentation_type": pres_type,
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "2008_submission_form",
            "confidence": "medium" if not flags else "low",
            "qa_flags": flags,
        })

    return entries


def parse_talk_title_format(year: int, text: str) -> list[dict]:
    """
    2022 and 2024: T#) TALK TITLE: ... / ABSTRACT: ...
                   P#) POSTER TITLE: ... / AUTHORS: ... / ABSTRACT: ...
    """
    text = norm_text(text)
    entries = []
    entry_pat = re.compile(
        r"(?m)^[ \t]*(?:(?P<label>(?:HP|SS|[TP])\d+)\s*\)\s*)?"
        r"(?:TALK|POSTER)\s+TITLE\s*:\s*(?P<title>[^\n]+)",
        re.IGNORECASE,
    )
    positions = [(m.start(), m.end(), m.group("label"), m.group("title").strip())
                 for m in entry_pat.finditer(text)]

    for i, (start, end, label_raw, title) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chunk = text[end:next_start]

        authors_raw = ""
        abstract = ""
        abs_m = re.search(r"(?i)^ABSTRACT\s*:\s*(?P<abs>.+)", chunk, re.DOTALL | re.MULTILINE)
        if abs_m:
            abstract = clean_block(abs_m.group("abs"))
        auth_m = re.search(r"(?i)^AUTHORS?\s*:\s*(?P<auth>[^\n]+)", chunk, re.MULTILINE)
        if auth_m:
            authors_raw = clean_ws(auth_m.group("auth"))

        if not label_raw:
            idx = len(entries) + 1
            etype = "talk" if "talk" in text[start:end].lower() else "poster"
            label = f"T{idx}" if etype == "talk" else f"P{idx}"
        else:
            label = re.sub(r"[^A-Z0-9]", "", label_raw.upper())

        if is_non_research(title, abstract):
            continue
        flags: list[str] = []
        if not abstract:
            flags.append("no-abstract")
        if not authors_raw:
            flags.append("no-authors")
        entries.append({
            "year": year, "entry_id": label,
            "presentation_type": _entry_type(label),
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "talk_title_abstract",
            "confidence": "high" if not flags else "medium",
            "qa_flags": flags,
        })
    return entries


def parse_2019(year: int, text: str) -> list[dict]:
    """
    2019 PDF (rescanned): tabular schedule followed by an 'In-House Abstracts'
    section. Abstract entries use TITLE: / AUTHORS: / ABSTRACT: labels with
    `------------` separator lines between them.
    """
    text = norm_text(text)
    # Find the abstracts section
    sec_m = re.search(r"In-?[Hh]ouse\s+Abstracts?\b", text)
    if not sec_m:
        return parse_schedule_only(year, text)
    section = text[sec_m.end():]

    entry_pat = re.compile(
        r"(?ms)^TITLE\s*:\s*(?P<title>.+?)\n\s*\n"
        r"AUTHORS?\s*:\s*(?P<authors>.+?)\n\s*\n"
        r"ABSTRACT\s*:\s*(?P<abstract>.+?)(?=\n-{5,}|\nTITLE\s*:|\nPOSTER\s+ABSTRACTS|\Z)"
    )
    entries: list[dict] = []
    t_idx = p_idx = 0
    # Track whether we're past the "POSTER ABSTRACTS" header
    poster_section = False
    pa_pos = section.find("POSTER ABSTRACTS")
    if pa_pos < 0:
        pa_pos = section.find("Poster Abstracts")
    for m in entry_pat.finditer(section):
        if pa_pos >= 0 and m.start() >= pa_pos:
            poster_section = True
        else:
            poster_section = False
        title = clean_ws(m.group("title").replace("\n", " "))
        authors_raw = clean_ws(m.group("authors").replace("\n", " "))
        abstract = clean_block(m.group("abstract"))
        if poster_section:
            p_idx += 1
            label = f"P{p_idx}"
            ptype = "poster"
        else:
            t_idx += 1
            label = f"T{t_idx}"
            ptype = "talk"
        if is_non_research(title, abstract):
            continue
        flags: list[str] = []
        if not abstract:
            flags.append("no-abstract")
        if not authors_raw:
            flags.append("no-authors")
        entries.append({
            "year": year, "entry_id": label,
            "presentation_type": ptype,
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "2019_abstracts_section",
            "confidence": "high" if not flags else "medium",
            "qa_flags": flags,
        })
    if not entries:
        return parse_schedule_only(year, text)
    return entries


def parse_2025(year: int, text: str) -> list[dict]:
    """
    2025: 'TALK ABSTRACTS' section + poster section.
    Each entry:  LastName, FirstName\\nTALK TITLE: ...\\nAUTHORS: ...\\nABSTRACT: ...
    """
    text = norm_text(text)
    entries = []

    # Combined pattern works for both talks and posters in 2025 format.
    # Allow "TALK TITLE" or "TALKTITLE" (2023 PDF extraction drops the space).
    # Presenter line may be indented and contain multi-word surnames
    # ("De Paola, Andrea") plus trailing OCR garbage we ignore.
    # Title may wrap onto continuation lines that themselves contain colons.
    # Up to a few junk lines may sit between presenter and TALK TITLE.
    entry_pat = re.compile(
        r"(?m)^[ \t]*(?P<presenter>"
        r"[A-Z][a-zA-ZáéíóúàèìòùäöüñçÄÖÜß\-]+(?:\s+[A-Z][a-zA-ZáéíóúàèìòùäöüñçÄÖÜß\-]+)*"
        r"(?:,\s*[A-Z][\w\s\-\.]*)?"
        r")[^\n]*\n"
        r"(?:[^\n]*\n){0,3}?"  # tolerate junk lines between presenter and TITLE
        r"\s*(?:TALK|POSTER)\s*TITLE\s*:\s*"
        r"(?P<title>[^\n]+(?:\n(?!\s*(?:AUTHORS?|ABSTRACT)\s*:)[^\n]+)*)\s*\n"
        r"\s*AUTHORS\s*:\s*(?P<authors>[^\n]+)\n"
        r"(?:(?!\s*ABSTRACT\s*:).*?\n)*?"
        r"\s*ABSTRACT\s*:\s*(?P<abstract>.+?)"
        r"(?=(?m:^[ \t]*[A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*,\s*[A-Z])|\Z)",
        re.DOTALL,
    )
    t_idx = p_idx = 0
    for m in entry_pat.finditer(text):
        # Title may span 2 lines in source (e.g. 2023). Collapse newlines.
        title = clean_ws(re.sub(r"\s*\n\s*", " ", m.group("title").strip()))
        authors_raw = clean_ws(m.group("authors").strip())
        abstract = clean_block(m.group("abstract"))
        is_poster = "poster" in text[m.start():m.start()+50].lower()
        if is_poster:
            p_idx += 1
            label = f"P{p_idx}"
            ptype = "poster"
        else:
            t_idx += 1
            label = f"T{t_idx}"
            ptype = "talk"
        if is_non_research(title, abstract):
            continue
        flags: list[str] = []
        if not abstract:
            flags.append("no-abstract")
        entries.append({
            "year": year, "entry_id": label, "presentation_type": ptype,
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "2025_combined",
            "confidence": "high" if not flags else "medium",
            "qa_flags": flags,
        })

    # Also catch any TALK TITLE entries not matched by the presenter-first pattern
    # (some talk entries may not have a "LastName, FirstName" header)
    if not entries:
        return parse_talk_title_format(year, text)

    return entries


_2009_BREAK_RE = re.compile(
    r"(?m)^(?:\d+:\d+-\d+:\d+\s+(?:Session|Coffee|Lunch|Open|Wine|Dinner)"
    r"|[A-Z][a-z]+day,?\s+[A-Z][a-z]+\s+\d+"
    r"|[A-Z][a-z]+day\s+[A-Z][a-z]+\s+\d+"
    r"|\s*Session\s+\d+\s+Chair)",
)

def _clean_2009_abstract(raw: str) -> str:
    """Strip schedule breaks, room/day headers, and stray timestamps from an
    abstract candidate. Truncate at the first such break line."""
    if not raw:
        return ""
    lines = raw.splitlines()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append(ln)
            continue
        # Day header (e.g., "Thursday, April 30—LSC 4258/4263")
        if re.match(r"^[A-Z][a-z]+day,?\s+[A-Z][a-z]+\s+\d+", s):
            continue
        # Time-range break (e.g., "3:15-3:45 Coffee Break—LSC 4212")
        if re.match(r"^\d+:\d+-\d+:\d+\s", s):
            break
        # Session header
        if re.match(r"^Session\s+\d+\s+Chair", s, re.IGNORECASE):
            break
        # Room/floor label alone (e.g., "—LSC 4212")
        if re.match(r"^-+\s*LSC", s) or re.match(r"^LSC\s+\d", s):
            continue
        out.append(ln)
    cleaned = "\n".join(out).strip()
    # Collapse internal blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def parse_2009(year: int, text: str) -> list[dict]:
    """
    2009: file contains a short schedule (titles + authors only) followed by
    a fuller schedule with abstracts inline. Talks appear as
        TIME\\tT#)\\tTitle\\n
        \\t\\tAuthors\\n
        \\n
        Abstract paragraph(s)
    Posters appear as P#) blocks with optional abstracts later in the file.
    Strategy: find every T#/P# occurrence, keep the version with the longest
    body (which is the abstracts-included copy).
    """
    text = norm_text(text)

    # Match: optional timestamp + label + title line, then indented authors line.
    # Title may wrap onto a second non-indented line (T8 2009 case).
    entry_pat = re.compile(
        r"(?m)^[ \t]*(?:\d+:\d+\s+)?"
        r"(?P<label>[TP]\d+)\s*\)\s*"
        r"(?P<title>[^\n]+(?:\n[A-Z][^\n]+)?)\n"
        r"[ \t]+(?P<authors>[^\n]+)",
    )

    # First pass: find all candidates
    matches = list(entry_pat.finditer(text))
    # Compute span end = start of next entry (for abstract extraction)
    candidates: dict[str, list[tuple[int, int, str, str]]] = {}
    for i, m in enumerate(matches):
        label = re.sub(r"[^A-Z0-9]", "", m.group("label").upper())
        title = clean_ws(m.group("title"))
        authors_raw = clean_ws(m.group("authors"))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        candidates.setdefault(label, []).append((body_start, body_end, title, authors_raw))

    entries: list[dict] = []
    for label in sorted(candidates,
                        key=lambda lab: (lab[0], int(re.sub(r"\D", "", lab) or 0))):
        cands = candidates[label]
        # Pick the candidate with the longest body — this is the one with abstract
        best = max(cands, key=lambda c: c[1] - c[0])
        body_start, body_end, title, authors_raw = best
        abstract = _clean_2009_abstract(text[body_start:body_end])
        if is_non_research(title, abstract):
            continue
        flags: list[str] = []
        if not abstract:
            flags.append("no-abstract")
            flags.append("schedule-only")
        entries.append({
            "year": year, "entry_id": label,
            "presentation_type": _entry_type(label),
            "authors_raw": authors_raw, "title": title, "abstract": abstract,
            "parser_format": "2009_schedule_with_abstracts",
            "confidence": "medium" if abstract else "low",
            "qa_flags": flags,
        })
    return entries


def parse_schedule_only(year: int, text: str) -> list[dict]:
    """
    Schedule-only years (2012, 2019, 2023).
    Extract whatever title/author is available.
    """
    text = norm_text(text)
    # Try T#) paren
    blocks = deduplicate_blocks(split_into_blocks(text, _ENTRY_PAREN))
    if not blocks:
        # 2019: T# on its own line then author then title
        blocks_bare = split_into_blocks(text, _ENTRY_BARE)
        for label, block in blocks_bare:
            lines = [l.strip() for l in block.splitlines() if l.strip()][:2]
            blocks.append((label, "\n".join(lines)))

    entries = []
    for label_raw, block in blocks:
        label = re.sub(r"[^A-Z0-9]", "", label_raw.upper())
        block = clean_block(block)
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if len(lines) == 1:
            title = lines[0]; authors_raw = ""
        elif looks_like_authors(lines[0]):
            authors_raw = lines[0]; title = " ".join(lines[1:])
        else:
            title = lines[0]; authors_raw = " ".join(lines[1:])

        # 2023 special: title is just "TIME Surname"; lift surname into authors.
        if year == 2023 and title and not authors_raw:
            m2 = re.match(r"^\s*\d{1,2}:\d{2}\s+(?P<name>[A-Z][\w'\-]+(?:[\s\-][A-Z][\w'\-]+)*)\s*$",
                          title)
            if m2:
                authors_raw = m2.group("name").strip()
                title = ""  # no real title available in tentative schedule

        # For 2023 (surnames-only), allow entries even without a real title
        if year != 2023 and is_non_research(title, ""):
            continue
        flags = ["no-abstract", "schedule-only"]
        if not authors_raw:
            flags.append("no-authors")
        if not title:
            flags.append("no-title")
        if year == 2023:
            flags.append("surnames-only")
        entries.append({
            "year": year, "entry_id": label,
            "presentation_type": _entry_type(label),
            "authors_raw": authors_raw, "title": title, "abstract": "",
            "parser_format": "schedule_only",
            "confidence": "low",
            "qa_flags": flags,
        })
    return entries


def parse_2026(year: int, text: str) -> list[dict]:
    """
    2026 introduced a session-letter naming scheme: entries are A-1, A-2, …,
    D-6.  The PDF carries the schedule (presenter only) followed by four
    'SESSION X TALK ABSTRACTS' blocks, each with full entries shaped like

        A-2   Julie Blais, Scott Pruysers, and Luke Mungall
              Personalized Persuasion? Testing the Efficacy of …
              Advertisements

              Before we can evaluate the harm that psychographic …

    Author lines can wrap onto a second line when the list is long; we detect
    wrapping by a trailing ',' or ' and'.  A blank line between authors and
    title is *sometimes* present (A-5) and sometimes not (everywhere else),
    so we treat author-block termination as the load-bearing signal.
    """
    text = norm_text(text)

    # Carve the four abstract blocks.  The header line is indented and
    # repeats "SESSION X TALK ABSTRACTS" with X in A–D.
    header_re = re.compile(r"(?m)^\s*SESSION\s+([A-D])\s+TALK\s+ABSTRACTS\s*$")
    headers = list(header_re.finditer(text))
    if not headers:
        return []

    entries: list[dict] = []
    for hi, h in enumerate(headers):
        letter = h.group(1)
        block_start = h.end()
        block_end = headers[hi + 1].start() if hi + 1 < len(headers) else len(text)
        block = text[block_start:block_end]

        # Within the block, find entry-marker lines like "A-3   ...".
        entry_re = re.compile(rf"(?m)^{letter}-(\d+)\b")
        ms = list(entry_re.finditer(block))
        for i, m in enumerate(ms):
            entry_id = f"{letter}-{m.group(1)}"
            start = m.start()
            end = ms[i + 1].start() if i + 1 < len(ms) else len(block)
            chunk = block[start:end]
            # Strip the leading "A-3   " marker so the first line begins with
            # the author list.
            first_nl = chunk.find("\n")
            head = chunk[:first_nl] if first_nl >= 0 else chunk
            head = re.sub(rf"^{letter}-\d+\s+", "", head)
            tail = chunk[first_nl + 1:] if first_nl >= 0 else ""

            lines = [head] + tail.split("\n")
            stripped = [ln.strip() for ln in lines]

            # Walk author lines.  An author line continues if it ends with ','
            # or with ' and' (case-insensitive).  Stop after the first line
            # that does not continue.
            i_line = 0
            authors_parts: list[str] = []
            while i_line < len(stripped):
                ln = stripped[i_line]
                if not ln:
                    i_line += 1
                    continue
                authors_parts.append(ln)
                if ln.endswith(",") or re.search(r"\band$", ln, re.IGNORECASE):
                    i_line += 1
                    continue
                i_line += 1
                break
            authors_raw = " ".join(authors_parts).strip()

            # Skip blank lines, then collect title until the next blank line.
            while i_line < len(stripped) and not stripped[i_line]:
                i_line += 1
            title_parts: list[str] = []
            while i_line < len(stripped):
                ln = stripped[i_line]
                if not ln:
                    break
                title_parts.append(ln)
                i_line += 1
            title = " ".join(title_parts).strip()

            # Remainder is the abstract.  Preserve paragraph breaks roughly
            # by inserting a space at blank lines.
            while i_line < len(stripped) and not stripped[i_line]:
                i_line += 1
            abstract = " ".join(ln for ln in stripped[i_line:] if ln).strip()
            abstract = re.sub(r"\s+", " ", abstract)

            flags: list[str] = []
            if not abstract or abstract.upper() == "TBD":
                flags.append("no-abstract")
            if not title or title.upper() == "TBD":
                flags.append("no-title")

            entries.append({
                "year": year,
                "entry_id": entry_id,
                "presentation_type": "talk",
                "authors_raw": authors_raw,
                "title": title,
                "abstract": abstract,
                "parser_format": "2026_session_letter",
                "confidence": "high" if not flags else "medium",
                "qa_flags": flags,
            })

    return entries


# ── dispatcher ────────────────────────────────────────────────────────────────

def get_parser(year: int, text: str):
    if year == 1975:
        return parse_1975
    if 1976 <= year <= 1992:
        return parse_numbered_plain
    if 1993 <= year <= 2002:
        # 1993-1994: T# dot, author-first; 1995-2002: T# dot, title-first
        return parse_tx_dot
    if year == 2003:
        return parse_tx_paren
    if 2004 <= year <= 2007:
        return parse_tx_paren
    if year == 2008:
        return parse_2008
    if year == 2009:
        return parse_2009
    if 2010 <= year <= 2017:
        # 2012 .doc source has T#) format like the others in this band
        return parse_tx_paren
    if year == 2018:
        return parse_2018
    if year == 2019:
        # 2019 PDF (rescanned): schedule + In-House Abstracts section
        return parse_2019
    if year == 2022:
        return parse_talk_title_format
    if year == 2023:
        # 2023 PDF (rescanned): schedule + TALK ABSTRACTS section in 2025 format
        return parse_2025
    if year == 2024:
        return parse_talk_title_format
    if year == 2025:
        return parse_2025
    if year == 2026:
        return parse_2026
    return parse_tx_paren  # fallback


def parse_year(year: int, text: str) -> list[dict]:
    parser = get_parser(year, text)
    if parser is None:
        return []
    records = parser(year, text)
    for r in records:
        r.setdefault("source_file", f"In-House Program {year}")
    return records


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Import clean_abstract from the export stage so records.jsonl already
    # contains cleaned abstract text (diagnostics + downstream code see the
    # same values).
    sys.path.insert(0, str(Path(__file__).parent))
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("export_bib", Path(__file__).parent / "03_export_bib.py")
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    clean_abstract = _mod.clean_abstract

    total = 0
    with RECORDS_FILE.open("w", encoding="utf-8") as fout:
        for txt_file in sorted(EXTRACTED.glob("*.txt")):
            year = int(txt_file.stem)
            text = txt_file.read_text(encoding="utf-8")
            records = parse_year(year, text)
            for r in records:
                ab = r.get("abstract") or ""
                if ab:
                    r["abstract"] = clean_abstract(ab)
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1
            flag = "  ← NO ENTRIES FOUND" if not records else ""
            print(f"  {year}: {len(records):>3} entries{flag}")

    # Summary stats (use decoder to handle multi-line strings in JSON)
    decoder = json.JSONDecoder()
    content = RECORDS_FILE.read_text(encoding="utf-8")
    all_records: list[dict] = []
    pos = 0
    while pos < len(content):
        while pos < len(content) and content[pos] in " \t\n\r":
            pos += 1
        if pos >= len(content):
            break
        obj, end = decoder.raw_decode(content, pos)
        all_records.append(obj)
        pos = end
    no_abs = sum(1 for r in all_records if "no-abstract" in r.get("qa_flags", []))
    print(f"\nTotal: {total} records → {RECORDS_FILE.name}")
    print(f"  no-abstract: {no_abs}  |  with-abstract: {total - no_abs}")


if __name__ == "__main__":
    main()
