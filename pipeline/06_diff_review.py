#!/usr/bin/env python3
"""
Stage 6: Diff a hand-edited review bib (reviewed_and_fixed.bib) against the
canonical review_needed.bib, and emit corrections.jsonl patch lines for the
changed fields.

Per-round workflow:
  1. cp review_needed.bib reviewed_and_fixed.bib       # snapshot baseline
  2. <edit reviewed_and_fixed.bib in your editor>      # change titles/authors/abstracts
  3. python3 pipeline/06_diff_review.py                # generates patches
  4. python3 pipeline/06_diff_review.py --apply        # appends to corrections.jsonl

Then re-export and refresh:
  python3 pipeline/03_export_bib.py
  python3 pipeline/05_review.py

Output: corrections_from_diff.jsonl at the project root.
With --apply: also appends to corrections.jsonl with a dated batch header.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ORIG = ROOT / "review_needed.bib"
EDIT = ROOT / "reviewed_and_fixed.bib"
OUT = ROOT / "corrections_from_diff.jsonl"


# Match a single bib entry with its preceding `% year=N  entry_id=X` header
# Optional FLAGS comment line is fine.
ENTRY_RE = re.compile(
    r"%\s*year=(?P<year>\d+)\s+entry_id=(?P<entry_id>\S+)\s*\n"
    r"@inproceedings\{(?P<citekey>[^,]+),\n"
    r"(?P<body>.*?)\n\}",
    re.DOTALL,
)


def _extract_fields(body: str) -> dict[str, str]:
    """Parse the `  field = {value},` lines inside an entry body."""
    fields: dict[str, str] = {}
    # Find each `name = {...}` block. Values may span multiple lines.
    for m in re.finditer(
        r"^\s*(?P<name>\w+)\s*=\s*\{(?P<value>.*?)\}\s*,?\s*$",
        body,
        re.MULTILINE | re.DOTALL,
    ):
        fields[m.group("name").lower()] = m.group("value")
    return fields


def _parse_bib(text: str) -> dict[tuple[int, str], dict]:
    """Return a dict keyed by (year, entry_id) → {fields, citekey}."""
    out: dict[tuple[int, str], dict] = {}
    for m in ENTRY_RE.finditer(text):
        year = int(m.group("year"))
        entry_id = m.group("entry_id")
        citekey = m.group("citekey")
        fields = _extract_fields(m.group("body"))
        out[(year, entry_id)] = {
            "citekey": citekey,
            "fields": fields,
            "raw": m.group(0),
        }
    return out


# Map bib-field names → records.jsonl field names for the patch
BIB_TO_REC = {
    "title": "title",
    "author": "authors_raw",  # bib `author` becomes `authors_raw` in records
    "abstract": "abstract",
    "note": None,  # ignored — auto-generated from qa_flags + presentation_type
    "booktitle": None,  # ignored — from booktitles.py
    "year": None,
}


def _normalise_for_compare(s: str) -> str:
    """Collapse whitespace runs for comparison only (avoids whitespace-only
    diffs flagging as a change)."""
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    if not ORIG.exists() or not EDIT.exists():
        print(f"Missing one of:\n  {ORIG}\n  {EDIT}", file=sys.stderr)
        sys.exit(1)

    orig = _parse_bib(ORIG.read_text(encoding="utf-8"))
    edit = _parse_bib(EDIT.read_text(encoding="utf-8"))

    print(f"Original: {len(orig)} entries")
    print(f"Edited:   {len(edit)} entries")

    patches: list[dict] = []
    deletes: list[tuple[int, str]] = []
    unchanged = 0

    for key, edited in edit.items():
        if key not in orig:
            print(f"  ⚠ edited entry not in original: {key}")
            continue
        original = orig[key]
        patch: dict[str, str] = {}
        for bib_name, rec_name in BIB_TO_REC.items():
            if rec_name is None:
                continue
            old = original["fields"].get(bib_name, "")
            new = edited["fields"].get(bib_name, "")
            if _normalise_for_compare(old) != _normalise_for_compare(new):
                patch[rec_name] = new.strip()
        if patch:
            patches.append({"year": key[0], "entry_id": key[1], "patch": patch})
        else:
            unchanged += 1

    # Entries in original but missing from edited → user deleted them
    for key in orig:
        if key not in edit:
            deletes.append(key)

    # Write the corrections.jsonl-format output
    import json
    lines: list[str] = [
        "# Auto-generated from `pipeline/06_diff_review.py`.\n",
        "# Diff: reviewed_and_fixed.bib vs review_needed.bib (freshly regenerated).\n",
        f"# {len(patches)} patches, {len(deletes)} deletes.\n",
        "#\n",
        "# Inspect each line, then append (or merge) into corrections.jsonl,\n",
        "# then re-run `python3 pipeline/03_export_bib.py`.\n\n",
    ]
    for p in sorted(patches, key=lambda x: (x["year"], x["entry_id"])):
        lines.append(json.dumps(p, ensure_ascii=False) + "\n")
    for yr, eid in sorted(deletes):
        lines.append(json.dumps(
            {"year": yr, "entry_id": eid, "delete": True}
        ) + "\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(f"  Patches:   {len(patches)}")
    print(f"  Deletes:   {len(deletes)}")
    print(f"  Unchanged: {unchanged}")
    if patches:
        print("\nPatch summary (first 10):")
        for p in patches[:10]:
            fields = list(p["patch"].keys())
            print(f"  {p['year']} {p['entry_id']:<5}  changed: {', '.join(fields)}")

    if "--apply" in sys.argv:
        _append_to_corrections(patches, deletes)


def _append_to_corrections(patches: list[dict], deletes: list[tuple[int, str]]) -> None:
    """Append the diff output to corrections.jsonl with a dated batch header."""
    import datetime, json
    target = ROOT / "corrections.jsonl"
    if not (patches or deletes):
        print("\nNothing to apply.")
        return
    header = (
        f"\n# ── Manual review batch {datetime.date.today().isoformat()} "
        f"(via 06_diff_review.py) — {len(patches)} patches, {len(deletes)} deletes ──\n"
    )
    with target.open("a", encoding="utf-8") as f:
        f.write(header)
        for p in sorted(patches, key=lambda x: (x["year"], x["entry_id"])):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
        for yr, eid in sorted(deletes):
            f.write(json.dumps(
                {"year": yr, "entry_id": eid, "delete": True}
            ) + "\n")
    print(f"\nAppended to {target.name}.")
    print("Now run:")
    print("  python3 pipeline/03_export_bib.py")
    print("  python3 pipeline/05_review.py")


if __name__ == "__main__":
    main()
