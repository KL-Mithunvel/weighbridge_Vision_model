#!/usr/bin/env bash
# Waits for run_overnight.sh, then retries the (resumable) plate detector until
# it completes; MemoryError from the no-page-file commit limit is transient.
cd "$(dirname "$0")/../.."
source .venv/Scripts/activate
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4
until grep -q ALL_DONE data/ocr_runs/overnight.log; do sleep 30; done
for i in 1 2 3 4 5 6 7 8; do
  python development/ocr/plates_detect.py > data/ocr_runs/plates_det.log 2>&1 && break
  sleep 20
done
echo STAGE2_DONE >> data/ocr_runs/overnight.log
