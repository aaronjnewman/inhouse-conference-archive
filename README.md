# Dalhousie In-House Conference Archive (1975–2026)

A reproducible pipeline that turns ~50 years of Dalhousie Department of
Psychology & Neuroscience **In-House Conference** programs into a single
structured BibTeX archive, plus tooling and a 50th-anniversary talk built
on the resulting data.

The conference was founded in **1975** and has been the **Graham Goddard
In-House Conference** since 2011 (named for Dr. Graham V. Goddard, 1938–1987,
who developed the kindling model of epilepsy at Dalhousie). The 2020 and
2021 conferences were not held due to COVID; 2026 is the 50th.

## What's in this repository

### Source data (the hard-to-replace stuff)

| Path | Description |
|---|---|
| `source_programs/In-House Program YYYY.{pdf,doc,docx,rtf,txt}` | One program per year, 1975–2026 (no 2020/2021). Rescued from filing cabinets and email archives by **Richard Brown**, **Suzanne King**, and **Susan Lowerison**. |
| `corrections.jsonl` | Human-curated patch/add/delete operations applied on top of the parser output. |
| `descriptions of specific issues to fix.md` | Reviewer-supplied breakpoint markers used by the entry-splitter to disambiguate records the OCR fused together. |
| `slides/figures/{GrahamGoddard_photo.jpg, Hebb.jpg, klein_graphic.png, program_1975*.{jpg,png}}` | Hand-curated source images embedded in the slide deck. |

### Pipeline (regenerates everything else)

| Path | Stage |
|---|---|
| `pipeline/01_extract.py` | Source files → `extracted/YYYY.txt` (one UTF-8 text file per year). |
| `pipeline/02_parse.py` | Extracted text → `records.jsonl` (structured records, one per presentation). |
| `pipeline/03_export_bib.py` | Records + `corrections.jsonl` → `inhouse_conference.bib` + `qa_report.md`. |
| `pipeline/04_diagnose.py` | Records → `diagnostics.md` (per-record QA flags). |
| `pipeline/05_review.py` | Records + diagnose → `review_needed.bib` (subset for human review). |
| `pipeline/06_diff_review.py` | Diff a hand-edited `reviewed_and_fixed.bib` back into `corrections.jsonl` patches. |
| `pipeline/07_split_entries.py` | Apply reviewer-supplied breakpoints to split fused records. |
| `pipeline/booktitles.py` | Per-year conference title lookup. |
| `pipeline/run_pipeline.sh` | Convenience runner for the three core stages. |

### Final output (tracked for convenience)

- `inhouse_conference.bib` — 2,155 `@inproceedings` entries covering 50 conferences.

### Talk deck

| Path | Description |
|---|---|
| `slides/slides.md` | Marp markdown source for the 50th-anniversary talk. |
| `slides/analyze.py` | Reads `inhouse_conference.bib`, writes `slides/figures/0[1-5]_*.png` and `slides/stats.json`. |
| `slides/figures/` | Source images committed; generated figures gitignored. |

## How to rebuild from scratch

```bash
# 1. Run the pipeline (extract → parse → export)
bash pipeline/run_pipeline.sh

# 2. Generate the talk figures + stats
python3 slides/analyze.py

# 3. Render the slide deck (requires marp-cli)
cd slides && npx --yes @marp-team/marp-cli@latest --allow-local-files --html slides.md -o slides.pdf
```

`extracted/`, `records.jsonl`, `qa_report.md`, `diagnostics.md`, and the
generated figures are deliberately not tracked — they are pure functions
of the source files + pipeline scripts and can be rebuilt in ~30 seconds.

## License

- **Code** (`pipeline/`, `slides/analyze.py`) — MIT, see [`LICENSE-CODE`](LICENSE-CODE).
- **Data and program scans** (source PDFs/docs, `inhouse_conference.bib`, `corrections.jsonl`, image files) — CC BY 4.0, see [`LICENSE-DATA`](LICENSE-DATA). Original copyright in each abstract remains with its author(s).

## Provenance

See `CLAUDE.md` for the detailed format-group breakdown (14+ distinct
parser dialects across the 50-year corpus) and `SESSION_HANDOFF.md` for the
state of the cleanup effort as of May 2026 (~10% of records still flagged
for review).
