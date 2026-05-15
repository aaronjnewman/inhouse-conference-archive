#!/usr/bin/env python3
"""
Stage 5: Generate a BibTeX file containing only entries that need manual
review. An entry is included if EITHER:
  • the diagnostic (04_diagnose.py) flagged it with any pattern, OR
  • the parser-stage qa_flags contain anything other than the "informational"
    flags (no-abstract / schedule-only / surnames-only).

Each entry is preceded by a comment block listing the reasons it was flagged,
so the reviewer can decide what to fix (in corrections.jsonl) or accept.

Usage: python3 pipeline/05_review.py
Output: review_needed.bib at the project root.
"""

from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

PIPE = Path(__file__).parent
ROOT = PIPE.parent
OUT_FILE = ROOT / "review_needed.bib"


def _load(name: str, fname: str):
    """Load a pipeline module by file path (avoids hyphen/numeric issues)."""
    spec = importlib.util.spec_from_file_location(name, PIPE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    export = _load("export_bib", "03_export_bib.py")
    diagnose_mod = _load("diagnose", "04_diagnose.py")

    records = export.load_records()
    records, patched, deleted = export.apply_corrections(records)
    if patched or deleted:
        print(f"Applied {patched} corrections, deleted {deleted} records "
              f"({len(records)} remain)")

    # Build citekeys the same way 03_export does
    used_keys: set[str] = set()
    citekeys: dict[tuple[int, str], str] = {}
    for r in sorted(records, key=lambda x: (x.get("year", 0), x.get("entry_id", ""))):
        citekeys[(r["year"], r["entry_id"])] = export.make_citekey(r, used_keys)

    # Flags that are purely informational — don't pull an entry into review
    # just because it has one of these.
    INFO_FLAGS = {"no-abstract", "schedule-only", "surnames-only",
                  "booktitle-inferred", "invited-speaker"}

    review_entries: list[tuple[dict, list[str]]] = []
    for r in records:
        tags = [t for t, _ in diagnose_mod.diagnose(r)]
        # Add real (non-informational) qa_flags as their own tags
        for f in r.get("qa_flags", []):
            if f not in INFO_FLAGS:
                tags.append(f"qa:{f}")
        if tags:
            review_entries.append((r, tags))

    # Write a BibTeX-compatible file. Lines starting with `%` are comments
    # in BibTeX, so reviewer-facing annotations are safe to inline.
    out: list[str] = [
        "% Dalhousie In-House Conference — Review Queue\n",
        "% Entries here were flagged by pipeline/04_diagnose.py or carry\n",
        "% qa_flags indicating a likely parse problem. Each entry is\n",
        "% preceded by a `% FLAGS:` comment listing the reasons.\n",
        "%\n",
        "% Workflow:\n",
        "%   1. Read each entry's flags and inspect title/author/abstract.\n",
        "%   2. To correct, append a patch to corrections.jsonl, e.g.:\n",
        "%      {\"year\": 1985, \"entry_id\": \"11\", \"patch\":\n"
        "%       {\"title\": \"...\", \"authors_raw\": \"...\", \"abstract\": \"...\"}}\n",
        "%   3. To delete a record entirely:\n"
        "%      {\"year\": 1985, \"entry_id\": \"11\", \"delete\": true}\n",
        "%   4. Re-run `python3 pipeline/03_export_bib.py` to update the\n",
        "%      main BibTeX file (inhouse_conference.bib).\n",
        "%   5. Re-run this script to refresh the review list.\n",
        f"%\n% Total flagged: {len(review_entries)} of {len(records)} records\n\n",
    ]

    # Sort by year, then entry_id (numeric-aware)
    import re as _re

    def _sort_key(item: tuple[dict, list[str]]):
        r = item[0]
        eid = r["entry_id"]
        m = _re.match(r"^([A-Z]*)(\d+)(.*)$", eid)
        if m:
            return (r["year"], m.group(1), int(m.group(2)), m.group(3))
        return (r["year"], eid, 0, "")

    review_entries.sort(key=_sort_key)

    # Tag-count summary at the top of the file
    from collections import Counter
    tag_counts: Counter[str] = Counter()
    for _, tags in review_entries:
        for t in tags:
            tag_counts[t] += 1
    out.append("% --- flag counts ---\n")
    for tag, count in tag_counts.most_common():
        out.append(f"%   {count:>4}  {tag}\n")
    out.append("%\n\n")

    for r, tags in review_entries:
        ck = citekeys.get((r["year"], r["entry_id"]), "?")
        out.append(f"% =====\n")
        out.append(f"% FLAGS: {', '.join(sorted(set(tags)))}\n")
        out.append(f"% year={r['year']}  entry_id={r['entry_id']}\n")
        # Render the bib entry
        out.append(export.record_to_bib(r, ck))
        out.append("\n")

    OUT_FILE.write_text("".join(out), encoding="utf-8")
    print(f"Review file → {OUT_FILE}")
    print(f"  {len(review_entries)} flagged of {len(records)} total")
    print(f"\nTop flag categories:")
    for tag, count in tag_counts.most_common(10):
        print(f"  {count:>4}  {tag}")


if __name__ == "__main__":
    main()
