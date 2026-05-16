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

Total time: ~15 minutes. No billing required — Sheets + Drive APIs are free
at our usage level.

### 1. Create the spreadsheet (30 sec)

- Go to <https://sheets.new>.
- Sign in with the Google account that should own the spreadsheet.
- Name it something like *In-House Conference Corrections*.
- Copy the long **spreadsheet ID** from the URL — the part between `/d/`
  and `/edit`:
  `https://docs.google.com/spreadsheets/d/`**`1AbCd...XyZ`**`/edit`.
  Save it; we'll use it twice.

### 2. Create a Google Cloud project (2 min)

- Go to <https://console.cloud.google.com/projectcreate>.
- **Project name:** `inhouse-conference-sync` (or anything — just a label).
- **Organization / Location:** leave defaults; "No organization" is fine.
- Click **Create**, wait ~10 seconds, confirm the new project is selected
  in the top-bar dropdown.
- If GCP nags you about billing, **skip it** — Sheets API has a free tier
  far above what we'll use.

### 3. Enable the Sheets and Drive APIs (1 min)

The service account needs both:

- <https://console.cloud.google.com/apis/library/sheets.googleapis.com> →
  click **Enable**.
- <https://console.cloud.google.com/apis/library/drive.googleapis.com> →
  click **Enable**.

(gspread uses Drive API to look up spreadsheets by ID.)

### 4. Create the service account (2 min)

- Go to <https://console.cloud.google.com/iam-admin/serviceaccounts/create>.
- **Service account name:** `sheet-sync` — the ID auto-fills.
- **Description (optional):** *Sync corrections.jsonl with reviewer sheet*.
- Click **Create and continue**.
- "Grant this service account access to project" → **just click Continue.**
  No project-level IAM role needed; the service account gets access by
  being shared into the spreadsheet (step 6).
- "Grant users access to this service account" → **click Done.**

You'll land on the service-accounts list. Click into the one you just
made and copy its **email address** — looks like
`sheet-sync@inhouse-conference-sync.iam.gserviceaccount.com`. You'll need
it in a moment.

### 5. Generate a JSON key (1 min)

Still on the service-account detail page:

- Click the **Keys** tab.
- **Add Key → Create new key**.
- Key type: **JSON**.
- Click **Create**. A file downloads, named something like
  `inhouse-conference-sync-abc123.json`.
- Treat it like a password — don't email it, don't commit it to git.

### 6. Share the spreadsheet with the service account (30 sec)

- Open the spreadsheet from step 1.
- Click the green **Share** button (top-right).
- Paste the service-account email from step 4 into the people field.
- Permission: **Editor**.
- **Uncheck** "Notify people" (the service account doesn't have a real
  inbox).
- Click **Share**.

### 7. Wire up local credentials (1 min)

```sh
mkdir -p ~/.config/gspread
mv ~/Downloads/inhouse-conference-sync-*.json ~/.config/gspread/service_account.json
chmod 600 ~/.config/gspread/service_account.json
```

(Or set `GOOGLE_SA_KEY_FILE=/path/to/key.json` if you'd rather keep it
elsewhere.)

Add the sheet ID to your shell rc (`~/.zshrc` or `~/.bashrc`):

```sh
export CORRECTIONS_SHEET_ID="paste-the-id-from-step-1"
```

Then `source ~/.zshrc` (or open a fresh terminal).

### 8. Wire up GitHub Actions credentials (2 min)

- Open **Settings → Secrets and variables → Actions** in the repo on
  GitHub.
- Click **New repository secret**, twice:

| Secret name | Value |
|---|---|
| `GOOGLE_SA_KEY` | The **entire contents** of the JSON key file. Open it in a text editor and paste the whole `{ ... }` blob. |
| `CORRECTIONS_SHEET_ID` | The ID from step 1. |

### 9. Track `records.jsonl` so CI can read it (1 min)

The sync scripts need `records.jsonl` to detect collisions and to know
what the current bib says. It's gitignored by default. To enable the
scheduled workflows, first open `.gitignore` and delete (or comment out)
the `records.jsonl` line, then:

```sh
git add records.jsonl .gitignore
git commit -m "Track records.jsonl for CI sync"
git push
```

Treat it as a build artifact (like a lockfile): re-commit whenever you
re-run the parser locally.

### 10. First push (2 min)

First, install the Python dependencies:

```sh
pip install "gspread>=6.0" "google-auth>=2.20"
```

Then smoke-test on a single year before doing the full sync:

```sh
python3 scripts/push_to_sheet.py --year=2025
```

If that works, open the sheet — you should see a `2025` tab with
formatted rows. Then run the full push:

```sh
python3 scripts/push_to_sheet.py
```

This takes a few minutes (one tab per year, lots of formatting calls).
After it finishes, share the spreadsheet with your reviewers (just like
any other Google Doc — by their personal email, Editor access) and send
them the workflow blurb at the top of this README.

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
