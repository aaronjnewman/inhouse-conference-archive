#!/usr/bin/env python3
"""
Stage 1: Extract text from all source files.

Writes one UTF-8 .txt file per source file into ../extracted/.
Prints a diagnostics table (year, source format, char count, notes).
Files with < 2000 chars are flagged as needing manual review.
"""

from __future__ import annotations
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXTRACTED = ROOT / "extracted"
EXTRACTED.mkdir(exist_ok=True)

LOW_TEXT_THRESHOLD = 2000

# Priority order when multiple source files exist for the same year:
# use the file with the most useful text content.
# For 2002: PDF was post-OCR'd and .txt already exists (same content) — use .txt
# For 2022: PDF has better structure than .rtf
PREFER_FOR_YEAR: dict[int, str] = {
    2002: ".txt",  # pre-extracted OCR text
    2022: ".pdf",  # better structured than .rtf
}


def extract_pdf(src: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(src), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def extract_doc(src: Path) -> str:
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(src)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def extract_txt(src: Path) -> str:
    return src.read_text(encoding="utf-8", errors="replace")


def extract_rtf(src: Path) -> str:
    return extract_doc(src)  # textutil handles .rtf too


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".doc": extract_doc,
    ".docx": extract_doc,
    ".txt": extract_txt,
    ".rtf": extract_rtf,
}


def get_year(path: Path) -> int | None:
    m = re.search(r"(\d{4})", path.name)
    return int(m.group(1)) if m else None


def gather_sources() -> dict[int, list[Path]]:
    """Collect all source files grouped by year."""
    sources: dict[int, list[Path]] = {}
    for p in sorted(ROOT.glob("In-House Program *.*")):
        if p.suffix not in EXTRACTORS:
            continue
        year = get_year(p)
        if year is None:
            continue
        sources.setdefault(year, []).append(p)
    return sources


def choose_source(year: int, candidates: list[Path]) -> Path:
    """Pick the best source file when multiple exist for a year."""
    if len(candidates) == 1:
        return candidates[0]
    preferred_ext = PREFER_FOR_YEAR.get(year)
    if preferred_ext:
        for c in candidates:
            if c.suffix == preferred_ext:
                return c
    # Fallback: prefer PDF > docx > doc > txt > rtf
    ext_priority = [".pdf", ".docx", ".doc", ".txt", ".rtf"]
    for ext in ext_priority:
        for c in candidates:
            if c.suffix == ext:
                return c
    return candidates[0]


def main() -> None:
    sources = gather_sources()
    print(f"{'Year':>6}  {'Ext':>6}  {'Chars':>8}  {'Flag':<20}  Source file")
    print("-" * 80)

    all_ok = True
    for year in sorted(sources):
        candidates = sources[year]
        chosen = choose_source(year, candidates)
        skipped = [c for c in candidates if c != chosen]

        extractor = EXTRACTORS[chosen.suffix]
        text = extractor(chosen)

        # Minimal normalisation: unify line endings, strip form-feeds
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")

        char_count = len(text)
        flags: list[str] = []
        if char_count < LOW_TEXT_THRESHOLD:
            flags.append("LOW-TEXT")
            all_ok = False
        if skipped:
            flags.append(f"skipped {', '.join(s.suffix for s in skipped)}")

        out_path = EXTRACTED / f"{year}.txt"
        out_path.write_text(text, encoding="utf-8")

        flag_str = "; ".join(flags) if flags else "ok"
        print(
            f"{year:>6}  {chosen.suffix:>6}  {char_count:>8,}  {flag_str:<20}  {chosen.name}"
        )

    if not all_ok:
        print("\nWARNING: Some files are flagged LOW-TEXT. Review manually.")
        sys.exit(1)
    else:
        print(f"\nExtracted {len(sources)} files to {EXTRACTED}/")


if __name__ == "__main__":
    main()
