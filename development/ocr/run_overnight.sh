#!/usr/bin/env bash
# Sequential on purpose: this laptop has no page file, so two model processes
# at once hit MemoryError / paging-file errors (2026-11-13).
set -u
cd "$(dirname "$0")/../.."
source .venv/Scripts/activate
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4
python development/ocr/plates_detect.py
for e in rapidocr doctr easyocr; do python development/ocr/run_engine.py "$e"; done
echo ALL_DONE
