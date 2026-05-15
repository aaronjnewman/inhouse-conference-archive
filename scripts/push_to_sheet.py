#!/usr/bin/env python3
"""Push current bib state → Google Sheet (one tab per year).

Reads records.jsonl + corrections.jsonl, merges them (same logic as the bib
export), and upserts a row per record into the year tab. Preserves any
reviewer-typed columns from the previous push.

Usage:
    CORRECTIONS_SHEET_ID=<id> GOOGLE_SA_KEY_FILE=<path> python3 scripts/push_to_sheet.py

See scripts/README.md for setup.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sheet_common import (  # noqa: E402
    COLUMNS, DEFAULT_STATUS, FIX_COLS, FROZEN_COL_COUNT, HIDDEN_COLS,
    STATUS_OPTIONS, COLOR_FIX, COLOR_HEADER, COLOR_HEADER_TEXT, COLOR_META,
    COLOR_READONLY, col_index, current_bib_state, get_spreadsheet, source_pdf_url,
)


def build_row(rec: dict, preserved: dict[str, str]) -> list:
    """Compose one sheet row. `preserved` is the prior reviewer-typed values for this entry."""
    row = [""] * len(COLUMNS)
    row[col_index("year")] = rec["year"]
    row[col_index("entry_id")] = rec["entry_id"]
    row[col_index("presentation_type")] = rec.get("presentation_type", "")
    row[col_index("parser_format")] = rec.get("parser_format", "")
    row[col_index("qa_flags")] = ", ".join(rec.get("qa_flags", []) or [])
    row[col_index("source_pdf")] = source_pdf_url(rec)
    row[col_index("title")] = rec.get("title", "")
    row[col_index("authors_raw")] = rec.get("authors_raw", "")
    row[col_index("abstract")] = rec.get("abstract", "")
    # Reviewer-editable columns: preserve prior values, default empty/false
    for c in FIX_COLS:
        row[col_index(c)] = preserved.get(c, "")
    row[col_index("delete?")] = preserved.get("delete?", False)
    row[col_index("reviewer")] = preserved.get("reviewer", "")
    row[col_index("notes")] = preserved.get("notes", "")
    row[col_index("status")] = preserved.get("status", DEFAULT_STATUS)
    # Snapshot the current values so the puller can detect stale rows.
    row[col_index("_snapshot_title")] = rec.get("title", "")
    row[col_index("_snapshot_authors")] = rec.get("authors_raw", "")
    row[col_index("_snapshot_abstract")] = rec.get("abstract", "")
    return row


def read_preserved(ws) -> dict[str, dict[str, str]]:
    """Read existing fix/meta values from a worksheet, keyed by entry_id."""
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return {}
    header = values[0]
    if header != list(COLUMNS):
        # Schema drift — don't try to preserve from a malformed sheet.
        return {}
    preserved: dict[str, dict[str, str]] = {}
    entry_id_idx = col_index("entry_id")
    keep_cols = list(FIX_COLS) + ["delete?", "reviewer", "notes", "status"]
    for row in values[1:]:
        if len(row) <= entry_id_idx:
            continue
        eid = row[entry_id_idx]
        if not eid:
            continue
        entry: dict[str, str] = {}
        for c in keep_cols:
            ci = col_index(c)
            entry[c] = row[ci] if ci < len(row) else ""
        # Normalize the checkbox column to bool
        v = str(entry.get("delete?", "")).strip().upper()
        entry["delete?"] = v == "TRUE"
        preserved[eid] = entry
    return preserved


def col_letter(idx0: int) -> str:
    """0-based column index → A1 letter (A, B, ..., Z, AA, ...)."""
    s = ""
    n = idx0
    while True:
        s = chr(ord("A") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


def format_worksheet(ws, n_rows: int) -> None:
    """Apply header style, frozen panes, column colors, validation, hidden cols."""
    n_cols = len(COLUMNS)
    last_col = col_letter(n_cols - 1)

    # Header row formatting
    ws.format(f"A1:{last_col}1", {
        "backgroundColor": COLOR_HEADER,
        "textFormat": {"foregroundColor": COLOR_HEADER_TEXT, "bold": True},
        "horizontalAlignment": "LEFT",
        "wrapStrategy": "CLIP",
    })

    # Freeze identity+context+current columns, plus header row.
    sheet_id = ws.id
    requests: list[dict] = [{
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": 1,
                    "frozenColumnCount": FROZEN_COL_COUNT,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }]

    # Hide the snapshot columns.
    for col_name in HIDDEN_COLS:
        ci = col_index(col_name)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": ci,
                    "endIndex": ci + 1,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        })

    # Data validation: status dropdown
    status_ci = col_index("status")
    requests.append({
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": n_rows + 1,
                "startColumnIndex": status_ci,
                "endColumnIndex": status_ci + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    })

    # Data validation: delete? checkbox
    delete_ci = col_index("delete?")
    requests.append({
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": n_rows + 1,
                "startColumnIndex": delete_ci,
                "endColumnIndex": delete_ci + 1,
            },
            "rule": {
                "condition": {"type": "BOOLEAN"},
                "strict": True,
            },
        }
    })

    # Set row heights so abstracts wrap usefully.
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": 1,
                "endIndex": n_rows + 1,
            },
            "properties": {"pixelSize": 120},
            "fields": "pixelSize",
        }
    })

    # Column widths — narrow for IDs, wider for text columns.
    widths = {
        "year": 60, "entry_id": 75, "presentation_type": 80,
        "parser_format": 110, "qa_flags": 120, "source_pdf": 180,
        "title": 280, "authors_raw": 200, "abstract": 380,
        "title_fix": 280, "authors_fix": 200, "abstract_fix": 380,
        "delete?": 70, "reviewer": 120, "notes": 200, "status": 110,
    }
    for name, px in widths.items():
        ci = col_index(name)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": ci,
                    "endIndex": ci + 1,
                },
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    ws.spreadsheet.batch_update({"requests": requests})

    # Per-column background colors for the body rows.
    body_range_for = lambda name: (
        f"{col_letter(col_index(name))}2:"
        f"{col_letter(col_index(name))}{n_rows + 1}"
    )
    for ro_col in ("year", "entry_id", "presentation_type", "parser_format",
                   "qa_flags", "source_pdf", "title", "authors_raw", "abstract"):
        ws.format(body_range_for(ro_col), {
            "backgroundColor": COLOR_READONLY,
            "wrapStrategy": "WRAP",
            "verticalAlignment": "TOP",
            "textFormat": {"fontSize": 9},
        })
    for fix_col in FIX_COLS:
        ws.format(body_range_for(fix_col), {
            "backgroundColor": COLOR_FIX,
            "wrapStrategy": "WRAP",
            "verticalAlignment": "TOP",
            "textFormat": {"fontSize": 9},
        })
    for meta_col in ("delete?", "reviewer", "notes", "status"):
        ws.format(body_range_for(meta_col), {
            "backgroundColor": COLOR_META,
            "wrapStrategy": "WRAP",
            "verticalAlignment": "TOP",
            "textFormat": {"fontSize": 9},
        })


def upsert_year_tab(sh, year: int, recs: list[dict], skip_format: bool) -> int:
    """Create or update a worksheet for one year. Returns number of rows written."""
    title = str(year)
    try:
        ws = sh.worksheet(title)
        preserved = read_preserved(ws)
    except Exception:  # gspread.WorksheetNotFound or similar
        ws = sh.add_worksheet(title=title, rows=max(len(recs) + 10, 50),
                              cols=len(COLUMNS))
        preserved = {}

    rows = [list(COLUMNS)]
    for r in sorted(recs, key=lambda x: x.get("entry_id", "")):
        rows.append(build_row(r, preserved.get(r["entry_id"], {})))

    # Resize before writing so the update fits.
    needed_rows = len(rows)
    if ws.row_count < needed_rows:
        ws.resize(rows=needed_rows + 10, cols=len(COLUMNS))
    elif ws.row_count > needed_rows + 50:
        ws.resize(rows=needed_rows, cols=len(COLUMNS))

    # Clear lingering rows beyond the new data, then write.
    ws.clear()
    ws.update(values=rows, range_name="A1",
              value_input_option="USER_ENTERED")

    if not skip_format:
        format_worksheet(ws, len(rows) - 1)

    return len(rows) - 1


def main() -> None:
    skip_format = "--no-format" in sys.argv
    only_years: set[int] | None = None
    for arg in sys.argv[1:]:
        if arg.startswith("--year="):
            only_years = {int(y) for y in arg.split("=", 1)[1].split(",")}

    print("Loading records + corrections…")
    records = current_bib_state()
    by_year: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        by_year[r["year"]].append(r)
    if only_years:
        by_year = {y: rs for y, rs in by_year.items() if y in only_years}
    print(f"  {len(records)} records across {len(by_year)} years")

    sh = get_spreadsheet()
    print(f"Pushing to spreadsheet: {sh.title}")

    for year in sorted(by_year):
        n = upsert_year_tab(sh, year, by_year[year], skip_format)
        print(f"  {year}: {n} rows")

    print("Done.")


if __name__ == "__main__":
    main()
