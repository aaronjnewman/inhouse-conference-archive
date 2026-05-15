#!/usr/bin/env bash
# Run all three pipeline stages end-to-end.
# Run from the In-House/ directory: bash pipeline/run_pipeline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo "=== Stage 1: Extract text from source files ==="
python3 pipeline/01_extract.py

echo ""
echo "=== Stage 2: Parse entries into JSONL records ==="
python3 pipeline/02_parse.py

echo ""
echo "=== Stage 3: Export to BibTeX ==="
python3 pipeline/03_export_bib.py

echo ""
echo "Done. Outputs:"
echo "  extracted/           – intermediate UTF-8 text files"
echo "  records.jsonl        – structured parsed records"
echo "  inhouse_conference.bib – final BibTeX file"
echo "  qa_report.md         – quality-assurance report"
