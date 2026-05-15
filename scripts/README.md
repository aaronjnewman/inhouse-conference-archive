# Crowdsourced corrections — Google Sheet sync

This directory contains the bridge between **`corrections.jsonl`** (the
canonical patch-list applied during bib export) and a **Google Sheet** that
non-technical reviewers can edit directly.

Round trip:

```
records.jsonl + corrections.jsonl          ── push_to_sheet.py ──▶   Google Sheet (1 tab / year)
                                                                                │
                                                                       reviewers edit yellow cells
                                                                                ▼
                          ◀── pull_from_sheet.py ──         status = "fixed"
                                                            (appends a patch to corrections.jsonl)
```

The push is **non-destructive**: reviewer-typed columns are preserved across
syncs. The pull is **idempotent**: every row is hashed and re-imports are
deduped, so running it twice is safe.

## What reviewers see

A single Google Sheet, one tab per year (`1975`, `1976`, … `2026`, skipping
2020/2021). Each row is one presentation. Columns:

| Section | Columns | Notes |
|---|---|---|
| **Identity** (read-only) | year, entry_id, presentation_type, parser_format, qa_flags, source_pdf | First 6 cols, frozen. `source_pdf` links straight to the program on GitHub. |
| **Current values** (read-only) | title, authors_raw, abstract | What the bib says today. |
| **Fixes** (yellow, editable) | title_fix, authors_fix, abstract_fix | Reviewer types the corrected value. Blank = no change. |
| **Meta** (light blue, editable) | delete?, reviewer, notes, status | `status` is a dropdown; `delete?` is a checkbox. |
| **Snapshot** (hidden) | _snapshot_* | Collision detection. Do not edit. |

The reviewer workflow: open a year tab, scan rows, fix what's wrong, set
`status` to `fixed` (or `checked-ok` if nothing needed changing), put their
name in `reviewer`, save. That's it — no git, no GitHub account required.

## One-time setup

### 1. Create the spreadsheet

Make a new Google Sheet (any title — e.g. *In-House Conference Corrections*).
Note its **ID**: the long string between `/d/` and `/edit` in its URL.

### 2. Create a service account

In Google Cloud Console (free tier is fine):

1. Create a new project, e.g. *inhouse-conference-sync*.
2. Enable the **Google Sheets API** and **Google Drive API** for the project.
3. Create a service account (IAM & Admin → Service Accounts → Create).
4. On the account's *Keys* tab, **Add Key → Create new key → JSON**. A
   JSON file downloads — keep it private.

### 3. Share the sheet with the service account

Open the JSON key file and copy the `client_email` value (looks like
`<name>@<project>.iam.gserviceaccount.com`). In Google Sheets, share the
spreadsheet with that email, **Editor** access.

### 4. Provide credentials locally

Easiest:

```sh
mkdir -p ~/.config/gspread
cp ~/Downloads/<service-account>.json ~/.config/gspread/service_account.json
```

(Or set `GOOGLE_SA_KEY_FILE=/path/to/key.json`.)

Also export the sheet ID:

```sh
export CORRECTIONS_SHEET_ID="1AbCdEf...your-id..."
```

### 5. Provide credentials in GitHub Actions

In the repo's **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `GOOGLE_SA_KEY` | The **entire contents** of the service-account JSON file (paste raw). |
| `CORRECTIONS_SHEET_ID` | The spreadsheet ID. |

### 6. Make `records.jsonl` available to CI

The sync scripts read `records.jsonl` to detect collisions and to know
what the bib currently says. It's gitignored by default. To enable the
scheduled workflows:

```sh
git rm --cached records.jsonl 2>/dev/null  # if it was ever tracked
# Edit .gitignore — remove or comment out the `records.jsonl` line.
git add records.jsonl .gitignore
git commit -m "Track records.jsonl for CI sync"
```

Treat it as a build artifact (like a lockfile): re-commit whenever the
parser changes.

## Local commands

Install dependencies once:

```sh
pip install "gspread>=6.0" "google-auth>=2.20"
```

Push the current bib state to the sheet (do this first — populates the tabs):

```sh
python3 scripts/push_to_sheet.py
```

Single year (faster while iterating):

```sh
python3 scripts/push_to_sheet.py --year=1985
```

Skip formatting (fast re-syncs after the sheet has been styled once):

```sh
python3 scripts/push_to_sheet.py --no-format
```

Pull reviewer fixes back:

```sh
python3 scripts/pull_from_sheet.py
```

The pull appends to `corrections.jsonl` and writes a `pull_report.md`
summary at the repo root.

## Scheduled flow (CI)

Two workflows under `.github/workflows/`:

- **`sync_corrections.yml`** — runs Mondays 09:00 Halifax time (and on
  manual dispatch). Pulls from the sheet and opens a PR titled *Sync
  corrections from Google Sheet*. You review and merge.
- **`rebuild_bib.yml`** — runs on every push to `main` that changes
  `corrections.jsonl`. Regenerates `inhouse_conference.bib` +
  `qa_report.md` and commits them.

You can also push to the sheet on demand by adding a manual workflow —
push is intentionally not automated since it overwrites the sheet's
read-only columns and you might want it gated on a parser change.

## What this sync deliberately doesn't handle

- **Adding entirely new entries** that the OCR missed → use a manual
  `{"add": true, ...}` op in `corrections.jsonl`, same as before.
- **Splitting fused entries** (one record that's actually two
  presentations) → use `pipeline/07_split_entries.py` with
  `descriptions of specific issues to fix.md`.
- **Parser fixes** (the OCR is misreading whole years) → that stays in
  your hands.

The sheet only handles **content corrections to existing records** —
exactly the bounded scope reviewers signed up for.

## Collision detection

Each pushed row records snapshot copies of `title`, `authors_raw`, and
`abstract` in hidden columns. When pulling, if the current bib values
differ from the snapshot, the row is flagged in `pull_report.md` as
**stale** and *not* applied — the reviewer's fix was based on a version
of the entry that has since changed (maybe someone hand-edited
`corrections.jsonl` between pushes). Re-push the sheet and ask the
reviewer to re-check that row.

## Troubleshooting

**`Missing CORRECTIONS_SHEET_ID environment variable`** — Export it (see
step 1). In CI it comes from the repo secret of the same name.

**`Permission denied` opening the sheet** — Service account isn't shared
in (step 3). Share with the `client_email` from the JSON key.

**`Schema mismatch` warning on pull** — The sheet's header row no longer
matches `_sheet_common.COLUMNS`. Re-run `push_to_sheet.py` to rewrite the
tab.

**Pull says "0 patches"** but the sheet has fixes — Check that reviewers
set `status` to `fixed` (not `checked-ok`). Only `fixed` rows produce
patches.

**Reviewer accidentally edited a read-only column** — Just re-push; the
read-only columns get overwritten from the canonical bib state every push.
