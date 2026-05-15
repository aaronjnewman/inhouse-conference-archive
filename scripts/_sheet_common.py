"""Shared helpers for push_to_sheet.py and pull_from_sheet.py.

Auth, sheet schema, record loading. See scripts/README.md for setup.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
RECORDS_FILE = ROOT / "records.jsonl"
CORRECTIONS_FILE = ROOT / "corrections.jsonl"
SOURCES_DIR = ROOT / "source_programs"

# ── Sheet schema ─────────────────────────────────────────────────────────────
# Column order is significant: push_to_sheet writes rows in this order and
# pull_from_sheet reads them by index. Don't reorder without updating both.

COLUMNS: tuple[str, ...] = (
    # Read-only identity + context (frozen, white background)
    "year",                 # 0
    "entry_id",             # 1
    "presentation_type",    # 2
    "parser_format",        # 3
    "qa_flags",             # 4
    "source_pdf",           # 5
    # Read-only current values (frozen, white background)
    "title",                # 6
    "authors_raw",          # 7
    "abstract",             # 8
    # Editable: reviewer types corrections here (yellow)
    "title_fix",            # 9
    "authors_fix",          # 10
    "abstract_fix",         # 11
    # Editable: meta (light blue)
    "delete?",              # 12
    "reviewer",             # 13
    "notes",                # 14
    "status",               # 15
    # Hidden: snapshot of read-only values at push time (collision detection)
    "_snapshot_title",      # 16
    "_snapshot_authors",    # 17
    "_snapshot_abstract",   # 18
)

FROZEN_COL_COUNT = 9        # columns 0..8 frozen on scroll
FIX_COLS = ("title_fix", "authors_fix", "abstract_fix")
SNAPSHOT_COLS = ("_snapshot_title", "_snapshot_authors", "_snapshot_abstract")
HIDDEN_COLS = SNAPSHOT_COLS

STATUS_OPTIONS = ("untouched", "checked-ok", "fixed", "needs-help", "merged")
DEFAULT_STATUS = "untouched"

# Visual styling
COLOR_FIX = {"red": 1.0, "green": 0.95, "blue": 0.70}      # warm yellow
COLOR_META = {"red": 0.86, "green": 0.92, "blue": 1.0}     # light blue
COLOR_READONLY = {"red": 0.96, "green": 0.96, "blue": 0.96}  # near-white
COLOR_HEADER = {"red": 0.18, "green": 0.29, "blue": 0.63}    # deep blue
COLOR_HEADER_TEXT = {"red": 1.0, "green": 0.83, "blue": 0.0}  # Dalhousie gold

# GitHub blob URL for source-program links. Update if repo moves.
GITHUB_BLOB = "https://github.com/aaronjnewman/inhouse-conference-archive/blob/main"


def col_index(name: str) -> int:
    return COLUMNS.index(name)


# ── Records loading ──────────────────────────────────────────────────────────

def load_records() -> list[dict]:
    """Streaming JSONL loader compatible with the multi-line entries in records.jsonl."""
    if not RECORDS_FILE.exists():
        sys.exit(
            f"Missing {RECORDS_FILE}. Run `bash pipeline/run_pipeline.sh` to "
            "regenerate (or commit records.jsonl so CI can read it)."
        )
    decoder = json.JSONDecoder()
    content = RECORDS_FILE.read_text(encoding="utf-8")
    out: list[dict] = []
    pos = 0
    while pos < len(content):
        while pos < len(content) and content[pos] in " \t\n\r":
            pos += 1
        if pos >= len(content):
            break
        obj, pos = decoder.raw_decode(content, pos)
        out.append(obj)
    return out


def load_corrections_raw() -> list[dict]:
    """Return every non-comment line of corrections.jsonl as a parsed dict."""
    if not CORRECTIONS_FILE.exists():
        return []
    out: list[dict] = []
    for raw in CORRECTIONS_FILE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def apply_corrections(records: list[dict], ops: list[dict]) -> list[dict]:
    """Mirror of pipeline/03_export_bib.py:apply_corrections (patch+delete+add)."""
    by_key: dict[tuple[int, str], dict] = {(r["year"], r["entry_id"]): dict(r) for r in records}
    to_delete: set[tuple[int, str]] = set()
    for op in ops:
        key = (op.get("year"), op.get("entry_id"))
        if op.get("delete"):
            to_delete.add(key)
            continue
        if op.get("add"):
            new_rec = {k: v for k, v in op.items() if k != "add"}
            new_rec.setdefault("presentation_type", "talk")
            new_rec.setdefault("authors_raw", "")
            new_rec.setdefault("title", "")
            new_rec.setdefault("abstract", "")
            new_rec.setdefault("parser_format", "manual_correction")
            new_rec.setdefault("confidence", "manual")
            new_rec.setdefault("qa_flags", [])
            by_key[key] = new_rec
            continue
        rec = by_key.get(key)
        if not rec:
            continue
        if "patch" in op:
            for k, v in op["patch"].items():
                rec[k] = v
        elif "field" in op:
            rec[op["field"]] = op.get("value", "")
    return [r for k, r in by_key.items() if k not in to_delete]


def current_bib_state() -> list[dict]:
    """Return records as they appear in inhouse_conference.bib (post-corrections)."""
    return apply_corrections(load_records(), load_corrections_raw())


# ── Source-program links ─────────────────────────────────────────────────────

_SOURCE_INDEX: dict[str, str] | None = None


def source_pdf_url(record: dict) -> str:
    """Return a GitHub blob URL to the source program PDF (or other format)."""
    global _SOURCE_INDEX
    if _SOURCE_INDEX is None:
        _SOURCE_INDEX = {}
        if SOURCES_DIR.is_dir():
            # Prefer PDF when multiple formats exist for the same year.
            preferred = {".pdf": 0, ".docx": 1, ".doc": 2, ".rtf": 3, ".txt": 4}
            for p in sorted(SOURCES_DIR.iterdir(),
                            key=lambda q: preferred.get(q.suffix.lower(), 99)):
                stem = p.stem  # e.g. "In-House Program 1985"
                _SOURCE_INDEX.setdefault(stem, p.name)
    name = _SOURCE_INDEX.get(record.get("source_file", ""), "")
    if not name:
        return ""
    return f"{GITHUB_BLOB}/source_programs/{quote(name)}"


# ── Hashing / deduplication ──────────────────────────────────────────────────

def row_hash(year: int, entry_id: str, title_fix: str, authors_fix: str,
             abstract_fix: str, delete_flag: bool) -> str:
    """Stable short hash of a reviewer's edits to one row."""
    payload = json.dumps(
        {"y": int(year), "e": str(entry_id),
         "t": title_fix or "", "a": authors_fix or "", "ab": abstract_fix or "",
         "d": bool(delete_flag)},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def existing_sheet_hashes() -> set[str]:
    """All _sheet_hash values already in corrections.jsonl."""
    return {op["_sheet_hash"] for op in load_corrections_raw()
            if isinstance(op.get("_sheet_hash"), str)}


# ── Google Sheets auth ───────────────────────────────────────────────────────

def get_client():
    """Return an authenticated gspread client.

    Looks for credentials in this order:
      1. GOOGLE_SA_KEY env var (raw service-account JSON, used by CI)
      2. GOOGLE_SA_KEY_FILE env var (path to JSON file)
      3. ~/.config/gspread/service_account.json (gspread default)
    """
    try:
        import gspread
    except ImportError:
        sys.exit("Missing dependency: `pip install gspread`")
    raw = os.environ.get("GOOGLE_SA_KEY", "").strip()
    if raw:
        return gspread.service_account_from_dict(json.loads(raw))
    path = os.environ.get("GOOGLE_SA_KEY_FILE", "").strip()
    if path:
        return gspread.service_account(filename=path)
    default = Path.home() / ".config" / "gspread" / "service_account.json"
    if default.exists():
        return gspread.service_account(filename=str(default))
    sys.exit(
        "No Google credentials. Set GOOGLE_SA_KEY (raw JSON) or "
        "GOOGLE_SA_KEY_FILE (path to JSON), or place a service-account file "
        "at ~/.config/gspread/service_account.json. See scripts/README.md."
    )


def get_spreadsheet():
    sheet_id = os.environ.get("CORRECTIONS_SHEET_ID", "").strip()
    if not sheet_id:
        sys.exit(
            "Missing CORRECTIONS_SHEET_ID. Set it to the spreadsheet's ID "
            "(the long string in its URL between /d/ and /edit)."
        )
    return get_client().open_by_key(sheet_id)
