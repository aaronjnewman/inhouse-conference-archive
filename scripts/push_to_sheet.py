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
import time
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


_READONLY_COLS = (
    "year", "entry_id", "presentation_type", "parser_format",
    "qa_flags", "source_pdf", "title", "authors_raw", "abstract",
)
_META_COLS = ("delete?", "reviewer", "notes", "status")
_COL_WIDTHS = {
    "year": 60, "entry_id": 75, "presentation_type": 80,
    "parser_format": 110, "qa_flags": 120, "source_pdf": 180,
    "title": 280, "authors_raw": 200, "abstract": 380,
    "title_fix": 280, "authors_fix": 200, "abstract_fix": 380,
    "delete?": 70, "reviewer": 120, "notes": 200, "status": 110,
}


def _body_cell_request(sheet_id: int, n_rows: int, col_name: str,
                       background: dict) -> dict:
    """One repeatCell request that paints body cells of a column."""
    ci = col_index(col_name)
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": n_rows + 1,
                "startColumnIndex": ci,
                "endColumnIndex": ci + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": background,
                    "wrapStrategy": "WRAP",
                    "verticalAlignment": "TOP",
                    "textFormat": {"fontSize": 9},
                }
            },
            "fields": ("userEnteredFormat.backgroundColor,"
                       "userEnteredFormat.wrapStrategy,"
                       "userEnteredFormat.verticalAlignment,"
                       "userEnteredFormat.textFormat"),
        }
    }


def format_worksheet(ws, n_rows: int) -> None:
    """Apply all formatting in ONE batch_update API call (header, frozen
    panes, hidden columns, data validation, row heights, column widths,
    body coloring). Keeps the per-tab write count low enough to clear
    Google's 60-writes-per-minute quota when syncing 50 years."""
    sheet_id = ws.id
    n_cols = len(COLUMNS)
    requests: list[dict] = []

    # Header row coloring + bold text.
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 1,
                "startColumnIndex": 0, "endColumnIndex": n_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER,
                    "horizontalAlignment": "LEFT",
                    "wrapStrategy": "CLIP",
                    "textFormat": {
                        "foregroundColor": COLOR_HEADER_TEXT,
                        "bold": True,
                    },
                }
            },
            "fields": ("userEnteredFormat.backgroundColor,"
                       "userEnteredFormat.horizontalAlignment,"
                       "userEnteredFormat.wrapStrategy,"
                       "userEnteredFormat.textFormat"),
        }
    })

    # Freeze panes (header row + identity/current columns).
    requests.append({
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
    })

    # Hide snapshot columns.
    for col_name in HIDDEN_COLS:
        ci = col_index(col_name)
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        })

    # Dropdown on status.
    status_ci = col_index("status")
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1,
                      "endRowIndex": n_rows + 1,
                      "startColumnIndex": status_ci,
                      "endColumnIndex": status_ci + 1},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS],
                },
                "showCustomUi": True, "strict": False,
            },
        }
    })

    # Checkbox on delete?.
    delete_ci = col_index("delete?")
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1,
                      "endRowIndex": n_rows + 1,
                      "startColumnIndex": delete_ci,
                      "endColumnIndex": delete_ci + 1},
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True},
        }
    })

    # Body row heights.
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": n_rows + 1},
            "properties": {"pixelSize": 120},
            "fields": "pixelSize",
        }
    })

    # Column widths.
    for name, px in _COL_WIDTHS.items():
        ci = col_index(name)
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Body cell backgrounds (read-only / yellow fix / blue meta).
    for c in _READONLY_COLS:
        requests.append(_body_cell_request(sheet_id, n_rows, c, COLOR_READONLY))
    for c in FIX_COLS:
        requests.append(_body_cell_request(sheet_id, n_rows, c, COLOR_FIX))
    for c in _META_COLS:
        requests.append(_body_cell_request(sheet_id, n_rows, c, COLOR_META))

    ws.spreadsheet.batch_update({"requests": requests})


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
    start_from: int | None = None
    for arg in sys.argv[1:]:
        if arg.startswith("--year="):
            only_years = {int(y) for y in arg.split("=", 1)[1].split(",")}
        elif arg.startswith("--start-from="):
            start_from = int(arg.split("=", 1)[1])

    print("Loading records + corrections…")
    records = current_bib_state()
    by_year: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        by_year[r["year"]].append(r)
    if only_years:
        by_year = {y: rs for y, rs in by_year.items() if y in only_years}
    if start_from is not None:
        by_year = {y: rs for y, rs in by_year.items() if y >= start_from}
    print(f"  {len(records)} records across {len(by_year)} years")

    sh = get_spreadsheet()
    print(f"Pushing to spreadsheet: {sh.title}")

    years = sorted(by_year)
    for i, year in enumerate(years):
        n = upsert_year_tab(sh, year, by_year[year], skip_format)
        print(f"  {year}: {n} rows", flush=True)
        # Small breather between tabs to stay well under the 60-writes-per-
        # minute write quota even with retries. ~4 writes per tab + 1.5s
        # idle ≈ 24 tabs per minute, plenty of headroom.
        if i < len(years) - 1:
            time.sleep(1.5)

    print("Done.")


if __name__ == "__main__":
    main()
