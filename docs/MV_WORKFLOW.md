# The Standard Machine Vision Project Workflow

The end-to-end procedure for any project that develops vision models, distilled
from the Tile_Sorting project (see `TILE_SORTING_CASE_STUDY.md` for the
concrete history behind each step). Phases run roughly in order; the four
gates from `CLAUDE.md` are marked where they bind.

---

## Phase 0 — Frame the problem and the target  *(Gate 3)*

Before any code or training:

1. Write down what is being detected/classified/measured, for whom, and what
   decision the model's output drives in the end system.
2. **Answer the deployment-target questions** (`DEPLOYMENT_TARGETS.md`):
   where inference runs, online/offline, latency budget, weight-export
   requirements, device compute/memory budget. Record the decision.
3. Choose candidate architectures and training platforms **that satisfy the
   target**, not the other way round. Keep a designated lightweight fallback
   if the target is edge-class.

Output: a short recorded decision (project charter / `Claude_log.md` entry)
naming target, export format, candidate models, fallback.

## Phase 1 — Classical baseline before learned models

Where the problem allows it, build a classical CV pipeline first (e.g.
segmentation by color/threshold, edge/contour analysis):

- It forces real understanding of the imaging conditions.
- It gives a measurable baseline any learned model must beat.
- Its pure functions become the reusable preprocessing for dataset prep
  (Tile_Sorting's `segment_tile()` later produced the training crops).

Structure it as **pure, synthetic-input-testable functions** behind thin
hardware wrappers, all parameters in `config.yaml`, pytest coverage on the
pure parts.

## Phase 2 — Collect and audit data  *(Gate 1)*

1. Collect real samples under conditions as close to production as available;
   record capture conditions (device, distance, lighting, background).
2. Keep raw data under `data/` — **gitignored, never committed**.
3. Run a **data audit** before using the data for anything: counts, per-class
   balance, resolutions, label provenance, known gaps (e.g. "no damaged
   examples exist yet — only a false-positive floor can be calibrated").
   Automate it (`development/analyze_dataset.py` pattern: run the real
   pipeline modules over every file, derive recommendations statistically,
   report exclusions instead of silently dropping them).
4. Write the audit's conclusions down. Every later accuracy claim inherits
   the label-provenance caveat discovered here.

## Phase 3 — Calibrate / tune on data, not by guessing

- Derive thresholds from the dataset (percentiles with margin), not by eye.
- Pair a **batch analyzer** (statistics over the whole set) with an
  **interactive tuner** (sliders on one image at a time) that both call the
  *real* production functions — never a reimplementation.
- Distinguish scale-independent values (color ranges, shape ratios — transfer
  across cameras) from absolute-pixel values (areas, margins — must be
  re-derived per resolution/distance).
- Expect this phase to find real bugs (Tile_Sorting found two detector bugs
  only because the batch run measured false-positive rates).

## Phase 4 — Prepare the training dataset

1. A **script** builds the training set from raw data (cropping via the real
   segmentation, organizing by label) — reproducible, never manual file
   shuffling. Commit the script and a manifest CSV (source → output mapping);
   not the images.
2. Splits: fixed seed, fixed val fraction, **split by source-image group** so
   near-duplicates/augmented variants never straddle train/val.
3. Class imbalance: handle explicitly (oversample minority classes in train
   after the split, or weighted sampling) and document it.
4. If a hosted platform (Roboflow) is used for dataset management/labeling,
   keep the local raw data authoritative and the upload scripted.

## Phase 5 — Train, as recorded experiments  *(Gates 2 & 4)*

1. **Run the compute survey first** (`tools/compute_survey.py`); install
   CUDA torch if a GPU exists — iteration speed determines how many
   experiments are affordable.
2. One folder per model family (`models/<name>/`), from
   `templates/model_dir/`: `config.yaml` holds *every* hyperparameter;
   `prepare_dataset.py` / `train.py` / `val.py` / `predict.py` /
   `export_onnx.py` are the standard entry points.
3. Change one thing at a time; keep an **experiments table** in the model
   README (run name, backbone, device, top1, per-class recall). Keep failed
   runs in the table.
4. On small datasets: expect run-to-run variance; use early stopping; watch
   val accuracy, not train loss; treat one-image deltas as noise.
5. Augmentation: prefer online augmentation reflecting real invariances of
   the domain (e.g. tiles have no canonical "up" → full rotation). Test any
   offline augmentation or preprocessing against a clean held-out baseline
   before adopting it.

## Phase 6 — Evaluate to the standard  *(Gate 4)*

- Every evaluated model version gets the standard results folder
  (`tools/standard_results.py`, spec in `RESULTS_STANDARD.md`).
- Always evaluate on the held-out split; a full-dataset number may be
  collected only to find systematic errors and must be labelled as
  training-set fit.
- Cross-model comparisons happen on one common clean split — re-evaluate on
  the common baseline when models were trained on different data.
- Commit `metrics.json` / `predictions.json`; PNGs are regenerable.

## Phase 7 — Export and verify

1. Export to the format the target needs (`export_onnx.py` → `.onnx`,
   `.tflite`, …) — this only exists if Gate 3 chose a weight-exporting
   training path.
2. **Verify the export is faithful**: spot-check N images through the
   exported model vs the original; results must be consistent with the val
   accuracy. Record the exported file size — it is a deployment parameter.

## Phase 8 — Profile on the real target, then deploy

1. Profile latency/memory on the actual device (e.g. Edge Impulse BYOM
   on-device profiling, or a direct onnxruntime benchmark on the board)
   **before** integrating into the runtime pipeline.
2. If too slow/big: fall back to the designated smaller architecture (that's
   why Phase 0 named one), not to hacking the pipeline.
3. Deployment follows the staged model in `.CLAUDE/CLAUDE-COMMON.md`: all
   logic dev-machine-tested first; hardware smoke test on the device; fixes
   go back through the dev machine, never patched live on the device.

## Phase 9 — Close the loop

- Persist per-item snapshots/records in production runs — they are tomorrow's
  training data.
- Route low-confidence/misclassified samples back into the dataset for
  review (active-learning loop, hosted or manual).
- More **real** data is almost always the biggest accuracy lever — schedule
  collection of the classes/conditions the audit showed missing (especially
  true-positive examples of the defects being detected).
