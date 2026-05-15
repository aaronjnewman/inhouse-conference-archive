# Dalhousie Psychology & Neuroscience In-House Conference — BibTeX Archive

## What this is

A reproducible pipeline that converts ~50 years (1975–2025) of Dalhousie
Department of Psychology & Neuroscience In-House Conference programs into a
single structured BibTeX file. Output is intended for archival use and
data-mining (e.g. trends in topics, authorship networks, collaboration
patterns over time).

The conference was founded in 1975. From 2011 onward it has been the
**Graham Goddard In-House Conference**, named after Dr. Graham V. Goddard
(1938–1987), the Dalhousie researcher who developed the kindling model of
epilepsy and originally organised the conference.

Two years were not held due to COVID: **2020 and 2021** (so 2022 is the 46th
annual, not 47th — the counter paused rather than skipping).

## Source files

- `In-House Program YYYY.{pdf,doc,docx,rtf,txt}` — one per year, ~49 years.
- Format varies across the 50-year span; the pipeline dispatches a
  year-appropriate parser for each (see "Format groups" below).
- 1975–1979 were rescanned at higher quality in 2026-05.
- 2002 uses a pre-OCR'd `.txt` (the original PDF was unreadable).
- 2012, 2019, 2023 were initially excluded as schedule-only stubs but were
  later supplied with full-program sources.

## Pipeline

All scripts live in `pipeline/`. Run end-to-end with `bash pipeline/run_pipeline.sh`
or individually:

| Stage | Script | Reads | Writes |
|---|---|---|---|
| 1 | `01_extract.py` | `In-House Program *.{pdf,doc,…}` | `extracted/YYYY.txt` |
| 2 | `02_parse.py` | `extracted/*.txt` | `records.jsonl` |
| 3 | `03_export_bib.py` | `records.jsonl`, `corrections.jsonl` | `inhouse_conference.bib`, `qa_report.md` |
| 4 | `04_diagnose.py` | `records.jsonl` | `diagnostics.md` |
| 5 | `05_review.py` | `records.jsonl` + diagnose | `review_needed.bib` |
| 6 | `06_diff_review.py` | `reviewed_and_fixed.bib` vs `review_needed.bib` | `corrections_from_diff.jsonl` |
| 7 | `07_split_entries.py` | `descriptions of specific issues to fix.md` | `corrections_from_splits.jsonl` |

Stage 6/7 support `--apply` to append directly into `corrections.jsonl`.

## Key files (at project root)

- **`inhouse_conference.bib`** — the canonical output. Load this in
  reference managers or BibTeX-aware tools.
- **`records.jsonl`** — intermediate structured form (one record per
  presentation). Multi-line JSON values; load with `json.JSONDecoder().raw_decode()`
  in a loop, not line-by-line.
- **`corrections.jsonl`** — manual overrides. Three op types:
  - Patch: `{"year": N, "entry_id": "T5", "patch": {"title": "...", "authors_raw": "...", "abstract": "..."}}`
  - Add:   `{"year": N, "entry_id": "INV1", "add": true, ...full record fields...}`
  - Delete: `{"year": N, "entry_id": "T5", "delete": true}`
- **`qa_report.md`** — per-year summary + flagged entries list.
- **`diagnostics.md`** — detailed per-record flag report from
  `pipeline/04_diagnose.py`.
- **`review_needed.bib`** — entries currently flagged for manual review.
  Subset of the main bib annotated with `% FLAGS:` comments.
- **`descriptions of specific issues to fix.md`** — human-readable
  breakpoint markers for entries that contain multiple buried sub-entries.
  Read by `pipeline/07_split_entries.py`.

## Record schema (`records.jsonl`)

```json
{
  "year": 1985,
  "entry_id": "11",
  "presentation_type": "talk",
  "authors_raw": "D. Nicol & I. Meinertzhagen",
  "title": "The Cell Lineage of the Ascidian Neural Plate",
  "abstract": "Ascidians, or sea-squists ...",
  "source_file": "In-House Program 1985",
  "parser_format": "1985_inline",
  "confidence": "high",
  "qa_flags": []
}
```

`entry_id` may be plain numeric (1976-1992), `T#`/`P#`/`HP#`/`SS#`, or a
hierarchical split-suffix like `8-split1`, `T44-split1-split2` for entries
that were manually split from a contaminated parent.

## Format groups (per year)

1. 1975: Time-based inline OCR format
2. 1976-1992: Plain numbered abstracts (`1. Author Name`)
3. 1993-1994: T#. dot format, author-first
4. 1995-2002: T#. dot format, title-first
5. 2003-2017: T#) paren format, title-first (2012 is .doc, others PDF)
6. 2008: Asterisk-separated submission forms (mixed labeled/unlabeled)
7. 2009: Tabular schedule + inline abstracts
8. 2018: T#: colon format with "In-House Abstracts YYYY" section header
9. 2019: PDF — schedule + "In-House Abstracts" section with TITLE:/AUTHORS:/ABSTRACT: labels separated by `---` rules
10. 2022, 2024: T#) TALK TITLE: ... / AUTHORS: ... / ABSTRACT: ...
11. 2023, 2025: `Lastname, Firstname` presenter line + TALKTITLE:/AUTHORS:/ABSTRACT:

## Custom features built during cleanup

- **`corrections.jsonl` override system** preserves parser reproducibility
  while capturing human fixes out-of-band.
- **OCR-tolerant entry-marker recognition** in `02_parse.py`: `Tl0`
  → `T10`, `TS` → `T5`, `S.` → `5.` at paragraph starts only.
- **Cross-page-footer stripping** removes "Psychology Department In-House
  Conference April 2003 PAGE 7" and similar leakage.
- **OCR-garbage line detection** drops lines dominated by non-letter chars
  (figure scanner noise).
- **Title↔abstract style-shift detection** rescues entries where the OCR
  collapsed the paragraph break between an all-caps title and prose abstract.
- **Entry-splitter** (`07_split_entries.py`) takes a markdown file of
  reviewer-supplied breakpoints and emits patches + new records, inferring
  title/author/abstract structure year-by-year.
- **Diff-from-edited-bib workflow** (`06_diff_review.py`) lets a reviewer
  edit `reviewed_and_fixed.bib` directly and automatically generates
  `corrections.jsonl` patches.

## Working-directory conventions

- Don't commit `extracted/` if running fresh — it's regenerable from
  source files via `01_extract.py`.
- Don't commit `corrections.jsonl.bak` — created by ad-hoc rollback.
- Manual edits should go through `corrections.jsonl`, never edit
  `records.jsonl` directly (it's regenerated by stage 2).
- BibTeX-breaking characters (`{`, `}`, `\`) are stripped from field
  values at export, not escaped — the OCR sources produce these as
  garbage, not legitimate braces.

## Conference-number derivation

`pipeline/booktitles.py` computes the conference number per year:
`year - 1974`, minus 1 for each of {2020, 2021}. So:
- 1975 = 1st
- 2011 = 37th (first Graham Goddard year)
- 2019 = 45th
- 2022 = 46th (counter paused through COVID)
- 2025 = 49th

The booktitle for each year is hardcoded in `BOOKTITLES` with a `verified`
or `inferred` source flag (5 years still `inferred` — see
`pipeline/booktitles.py` comments).
