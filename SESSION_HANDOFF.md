# Session Handoff — last updated 2026-05-15 (post-50th-talk session)

## Where we left off

The dataset is **good enough to use** for the 50th-anniversary talk and is
now published as a public GitHub repo. Active cleanup is paused. This doc
captures the state of the **data-cleaning** effort so a future session can
pick up surgically. (For *slide-deck* maintenance see `slides/README.md`.)

## Current state

| Metric | Value |
|---|---|
| Total records in `inhouse_conference.bib` | **2,155** |
| With abstract | **2,108 (97.8%)** |
| No abstract (real schedule-only / OCR loss) | 47 |
| No title | 1 |
| No authors | 4 |
| Flagged for review | **223** (≈10.3% of records) |
| Years covered | **1975–2026** (no 2020, 2021 — COVID) |
| Working location | `~/dev/inhouse-conference-archive` (NOT OneDrive) |
| GitHub remote | https://github.com/aaronjnewman/inhouse-conference-archive |

## What's been done across the project

Five rounds of manual review + automated cleanup completed by Aaron + Claude:

1. **Tiers 1–5 of the original cleanup plan** (parser fixes, page-footer
   stripping, OCR garbage stripping, author normalization, booktitle
   verification, special-decision handling for invited speakers / session
   markers / 1975 non-research entries).
2. **Diagnostic + review system built** (`04_diagnose.py`, `05_review.py`,
   `06_diff_review.py`, `07_split_entries.py`).
3. **Four review rounds**:
   - Round 1: 9 manual patches (1975–1978 OCR corrections).
   - Round 2: 126 diff patches + 41 first-tier splits + 63 new sub-entries.
   - Round 3: 12 diff patches + 25 second-tier splits + 36 new sub-entries.
   - Round 4: 15 diff patches + 2 deletes + 14 third-tier splits + 23 new
     sub-entries.
4. **Re-imported with rescanned 1975–1979 PDFs** and newly-added 2012,
   2019, 2023 program sources.
5. **Performance fix**: replaced catastrophic-backtracking whitespace-
   tolerant regex in `07_split_entries.py` with linear normalised string
   scan.
6. **2026 added** (May 2026 session): new `parse_2026` handles the
   `A-1…D-6` session-letter scheme; 22 entries from the 50th conference
   merged into the corpus.

## What's left to do — by priority

### Priority 1 — finish the review queue (223 flagged entries)

Open `review_needed.bib`. The flag-count summary at the top groups them.
The dominant category is still **`qa:needs-split-review` (128 entries)** —
these are auto-generated sub-splits from rounds 2–4 that need verification:

- Most are correctly inferred (title, author, abstract all parsed cleanly).
- Some have title↔author swaps from the heuristic guessing wrong on
  whether the user's breakpoint was an author name vs. a title.
- A handful need OCR-degraded text corrected.

Quick workflow:
```bash
cp review_needed.bib reviewed_and_fixed.bib
# edit reviewed_and_fixed.bib in your editor
python3 pipeline/06_diff_review.py --apply
python3 pipeline/03_export_bib.py
python3 pipeline/05_review.py
```

### Priority 2 — three persistent "breakpoint not found" warnings

These three descriptions reference text that's no longer in the parent
abstract (re-parsing changed the content after the description was written):

- **1978/17-split3-split1** "N. tllen & J. Barresi" — likely "N. Allen"
  with OCR "tllen" but spelling differs from current abstract content.
- **1995/T26-split2** "T29. Sex Differences" — current abstract starts
  "differences in the brain anatomy …" (lowercase d, no T29 prefix).
- **1995/T26-split2** also has "T19. Beyond Immediate Self-Interest…"
  that may not match current content.

Easiest fix: open the parent abstract in `review_needed.bib`, find the
actual text where the split should happen, and update the description
file. Or just apply the split manually via a `corrections.jsonl` add op.

### Priority 3 — remaining diagnostic categories

After `needs-split-review`, the next-biggest pure-diagnostic flags are:

| Tag | Count | Notes |
|---|---|---|
| `abstract-suspicious-long` | 50 | Many will be legit long abstracts; spot-check |
| `abstract-too-short` | 44 | Diagnostic-source short flag |
| `title-too-long` | 30 | Some are real long titles (1980s symposia); spot-check |
| `qa:abstract-too-short` | 27 | Truncated by a cleanup pass; likely needs manual reconstruction from source |
| `title-has-newline` | 26 | Mostly benign wrap artifacts in 2023 |
| `abstract-affiliation-head` | 17 | Author affiliations leaked into abstract start |
| `multi-entry-numerated` | 12 | Possibly more buried entries to split |
| `title-is-abstract` | 8 | Title got the abstract content; needs swap |
| `author-has-digit` | 7 | OCR-garbled author names (deep OCR issues; mostly unfixable) |

### Priority 4 — five booktitles still "inferred"

In `pipeline/booktitles.py`, these years have `"inferred"` rather than
`"verified"`:

- **1983** — program prints "Eighth" but ordinal is Ninth; verified
  authoritatively but flagged as inferred since the program itself is
  wrong.
- **1995** — title page not legible in OCR output.
- **1999** — schedule appears on page 1, no title page in OCR.
- **2019** — docx title page not clearly readable.
- **2023** — was added late; cover page exists in PDF.

Spot-check 2019 and 2023 since we now have better source files; the
others are likely permanent.

### Priority 5 — long-term wishlist (not blocking anything)

- **Author normalisation**: many authors still appear as `J.A. McNulty`
  vs `J.A. McNult.v` vs `J. A. McNulty` — would benefit from a
  canonicalisation pass using a curated author list. Would also clean up
  the co-authorship-network figure considerably.
- **Department-affiliation extraction**: 2019+ entries carry rich
  affiliation info that's currently discarded. Could be useful for
  collaboration-network analysis.
- **Conference-honours-poster flag**: 2019 introduced HP# entries; later
  years may have lost this distinction. 2026 has no posters at all.
- **DOI lookup**: cross-reference titles against PubMed / Google Scholar
  to find published versions.
- **GitHub Pages**: stand up a searchable web UI on top of the bib
  (promised on the closing slide of the 50th-anniversary talk).
- **Borealis deposit**: package + register a DOI for the dataset.

## Pickup script

When resuming:

```bash
cd ~/dev/inhouse-conference-archive   # NOT the OneDrive path
git pull                              # in case anything moved while you were away

# Confirm current state:
bash pipeline/run_pipeline.sh         # regenerates extracted/, records.jsonl, bib, qa_report.md
python3 pipeline/04_diagnose.py
python3 pipeline/05_review.py
head -15 qa_report.md
grep -c '% FLAGS:' review_needed.bib

# Snapshot for next review round:
cp review_needed.bib reviewed_and_fixed.bib

# (edit reviewed_and_fixed.bib + descriptions file)

# Apply:
python3 pipeline/06_diff_review.py --apply
python3 pipeline/07_split_entries.py --apply
python3 pipeline/03_export_bib.py
python3 pipeline/05_review.py
```

## Visualization-ready slices

For talks and data-mining the cleanest cuts of the data are:

- **1976–2018**: parser handles these reliably; >99% have abstracts.
- **2008–2026 abstracts**: nearly all clean; great for text mining.
- **1975 + 2019 + 2023**: keep flagged as lower-confidence in any
  longitudinal analysis. 1975 has OCR garble in author names; 2019
  and 2023 had late-added sources with split sub-entries still in review.
- **2026**: only 22 entries (talks only, no posters); fewer than a typical
  recent year so be careful about year-over-year normalisation.

`records.jsonl` is the easiest input for Python-based analysis (pandas,
NetworkX, etc.). The schema is documented in `CLAUDE.md`. For
slide-grade plots, see `slides/analyze.py` which goes the bib-first route
(applies corrections at parse time).

## Key context preserved for future sessions

- The "user edits `reviewed_and_fixed.bib` by hand" workflow lets Aaron do
  surgical fixes without writing JSON. The diff tool translates edits into
  `corrections.jsonl` patches automatically.
- The descriptions file (`descriptions of specific issues to fix.md`) uses
  a free-form markdown syntax: each entry is `% year=N entry_id=X`
  followed by bullet lines with breakpoint markers (in quotes or plain
  text). The splitter is tolerant of reviewer prose around the markers.
- The pipeline is fully reproducible: nuking `extracted/`, `records.jsonl`,
  `inhouse_conference.bib` and running `bash pipeline/run_pipeline.sh` will
  rebuild everything from the source programs + `corrections.jsonl`.
- The committed `inhouse_conference.bib` is the *current* canonical output
  after corrections; treat it as authoritative if the pipeline ever
  drifts on a re-run.
