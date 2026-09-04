# Case Study — Tile_Sorting: the process actually followed

The record of how vision models were developed on the Tile_Sorting project
(`kl-mithunvel/tile_sorting`, snapshot 2026-08-27): what was done, in what
order, what went wrong, and which baseline rule each lesson produced. This is
the evidence base for `CLAUDE.md`'s four gates and `docs/MV_WORKFLOW.md`.

Problem: automated inspection/grading of ceramic/terracotta tiles (cracks,
broken corners, grade classification `3A/3B/4/5`) for Sree Murugan Tile
Works, as part of a larger sorting system (camera + acoustic tap-testing +
pick-and-place). This case study covers the vision-model track.

---

## 1. Classical CV pipeline first (`camera_node/`)

Before any learned model, a classical pipeline was built and tested:

- `segment_tile()` — HSV color-range threshold + largest contour isolates the
  tile from the background.
- `detect_cracks()` — grayscale → blur → Canny → keep long, thin contours;
  severity from measured length.
- `detect_broken_corner()` — contour area vs its own min-area-rect
  (`fill_ratio`), later plus a distance-transform depth check.
- `TileTracker` — debounced presence state machine counting tiles crossing
  the frame; the expensive per-tile analysis runs once per tile, on the
  largest-area (best) sighting, not every frame.

**Structure that made it work**: every detector is a pure function with no
I/O, covered by pytest with synthetic images; hardware access (webcam, video
files) lives in thin wrappers; every threshold lives in `config.yaml`.

→ Baseline rules: pure-logic/hardware split; no hardcoded parameters;
classical baseline before learned models.

## 2. Data collection and the data audit (`data/`, `development/`)

~380 real tile photos were collected (single tiles on a checkerboard
calibration sheet), kept in a gitignored `data/` folder. Two calibration
tools were built, both calling the **real** production functions:

- `analyze_dataset.py` — batch: runs every photo through segmentation/crack/
  corner modules, derives recommended thresholds statistically
  (percentiles + margin), auto-excludes off-center photos *with a reported
  count*, filters hue sampling to well-lit pixels.
- `tile_param_tuner.py` — interactive GUI: sliders, live preview of each
  pipeline stage, save/load parameters as XML.

What the audit revealed — and would never have been known otherwise:

- **All ~380 photos were of intact tiles** → calibration could only set a
  false-positive floor ("don't flag a healthy tile"), saying *nothing* about
  whether real defects get caught. Exactly one real crack photo existed in
  the whole set (found manually), giving crack detection a single
  true-positive data point and corner detection none.
- **Hue is meaningless on near-gray/glare pixels** — naive sampling gave a
  useless hue range (2–125) vs the real 6–15 after filtering.
- **Absolute-pixel values don't transfer** across resolution/camera distance
  (`min_tile_area_px`, `border_margin_px`), unlike color ranges and shape
  ratios.

→ Gate 1 (understand the data first; state what the data does NOT contain).

## 3. Bugs found only because the data was measured

- **Border-silhouette crack false positives**: `detect_cracks()` ran Canny on
  the tight bounding-box crop, so the tile's own edge sat at the crop border —
  a long thin high-contrast line indistinguishable from a crack.
  **~98–100% false-positive rate** on known-intact tiles, at any Canny
  threshold. Fix: `border_margin_px` blanks a border band of the edge map →
  FP rate ~2–11%.
- **Diagonal corner chips under-caught by `fill_ratio`**: a triangular chip
  (how ceramic actually breaks) removes far less *area* than a square notch
  reaching the same depth — a chip reaching halfway across the tile edge only
  dropped fill_ratio to ~0.87, above the 0.83 threshold. Fix: a second,
  independent depth check (`missing_extent_fraction` via distance transform),
  plus real-inch measurements using the tile's known 9×9 in size as its own
  scale reference.

→ Rules: calibrate against the dataset in batch (bugs show up as measured
rates); crop-based edge detectors need border exclusion; document debt
loudly ("still unvalidated for true positives") instead of minimising it.

## 4. Training dataset preparation

`prepare_roboflow_dataset.py` cropped every photo to just the tile **via the
real `segment_tile()`** and organized crops by grade into
`data/roboflow_dataset/<grade>/` (3A=140, 3B=109, 4=74, 5=53 — imbalanced),
plus contact sheets for manually flagging damage, plus a committed manifest
CSV. Key caveat recorded at the time: **grade labels come from how photos
were organized during capture, not a validated grading pass** — so these are
grade classifiers, not defect detectors.

→ Rules: scripted, reproducible dataset prep; commit manifests not images;
record label provenance.

## 5. Hosted training on Roboflow — and its two big lessons

The dataset was uploaded to Roboflow (`tile-grade-classification`, ViT-based
hosted training). `evaluate_grade_model.py` evaluated versions against a
fixed 19-image held-out set via the hosted inference API, writing
`metrics.json` / `predictions.json` / `confusion_matrix.png` per version.

Results and lessons:

- **v2 (brightness/exposure augmentation): 84.2% held-out.**
- **v3 (same + CLAHE contrast preprocessing): 63.2%** — the preprocessing
  *hurt*, concentrated in worst-grade recall, plausibly by erasing the tonal
  cues (staining/darkening) the model used. → never add preprocessing
  without a held-out re-test.
- **Full-dataset eval of v2: 98.1%** — inflated training-set fit (only 19 of
  376 images were held out). Useful for spotting systematic errors only.
  → always label which eval set a number comes from.
- **Roboflow's hosted ViT training exports no weights** — inference API only.
  The end target (edge board on the sorting line) needs local, offline
  inference, so the hosted model could never be the production model.
  → Gate 3: decide export requirements before training. This single
  discovery motivated both local pipelines below.

## 6. Local pipeline #1 — `cam_yolo` (YOLO26 classification)

Fine-tuned Ultralytics `yolo26*-cls` checkpoints locally on the same crops,
with a scripted split (seed 42, val_fraction 0.2) and minority-class
oversampling. A 4-way experiment table was kept in the README:

| Run | Model | Device | top1 |
|---|---|---|---|
| baseline | yolo26n-cls | CPU | 0.803 |
| +aug/balance | yolo26n-cls | CPU | 0.829 |
| same config re-run | yolo26n-cls | GPU | 0.776 |
| **+aug/balance, bigger backbone** | **yolo26s-cls** | GPU | **0.855** |

Lessons:

- **Compute survey mattered**: the dev machine had an RTX 1000 Ada that
  CPU-only torch ignored. CUDA torch gave **15–20x speedup** and made the
  experiment matrix affordable. → Gate 2.
- Augmentation reflected a real domain invariance (tiles have no canonical
  "up" → full rotation + flips), plus head dropout for the small dataset.
- The small backbone couldn't absorb augmentation + class balancing without
  trading classes off against each other; the bigger backbone resolved it.
- Identical configs on CPU vs GPU differed 0.829 vs 0.776 — **run-to-run
  variance is real on ~400-image datasets**; don't over-read single runs.
- "Can RL improve this?" was asked and answered: no — static supervised
  classification improves through more data, augmentation, transfer
  learning, regularization, and active-learning loops, not RL.

## 7. Local pipeline #2 — `cam_vit` (ViT-Base, the exportable Roboflow twin)

To keep Roboflow-v2's proven recipe but with real weights, the exact hosted
config was pulled via the Roboflow API and mirrored locally
(`google/vit-base-patch16-224-in21k`, same augmentation), with every
deliberate divergence documented in a table (native 224 resize instead of
Roboflow's 640; class-balancing oversampling instead of the uniform 3×
multiplier). Result: **93.4% top1** on the clean 76-image val split — beating
both cam_yolo (85.5%) and hosted v2 (84.2%), with all errors adjacent-grade
confusions.

Hard-won environment lessons, recorded as pins/procedures:

- **`transformers` v5 silently loads ViT with a randomly-initialized
  backbone** (renamed parameter names; no error, only a missable warning) —
  pinned `transformers==4.46.3` with a one-line verification command.
  → pin dependencies that silently break, with the reason.
- HuggingFace downloads were flaky on the dev connection — documented the
  `curl -C - --retry` + local-cache fallback and `HF_HUB_OFFLINE=1` workflow.

## 8. Offline augmentation experiment — a properly-run negative result

`augment_dataset.py` expanded 376 → 1000 images (mild affine + perspective
via albumentations, originals copied byte-for-byte). Retraining cam_vit on it:

- On the augmented set's own val split: 88.1% — **not comparable** (that
  split contains distorted images; a lower number ≠ worse model).
- On the same clean 76-image baseline split: **92.1% vs 93.4%** — a one-image
  difference. **Conclusion: no measurable improvement**; more *real* tiles,
  not re-transformed copies, is the lever.
- Critical guard added: split **by source-image group**, or augmented
  variants of a val image leak into train and inflate accuracy.

→ Rules: evaluate augmentation against a clean baseline; group-aware splits;
record negative results with numbers so they aren't re-run.

## 9. Deployment-target analysis (the Gate 3 payoff)

The end target is an Arduino UNO Q (Qualcomm QRB2210: quad-core CPU, Adreno
702 GPU, **no dedicated vision NPU**, 2–4GB RAM, Debian) — Raspberry Pi
class. Both local models were exported to ONNX and sanity-checked against
their originals on 20-image spot checks (exports faithful):

| Model | Val top1 | ONNX size | Edge verdict |
|---|---|---|---|
| cam_vit (ViT-Base, 86M params) | 93.4% | **328 MB** | Risky — likely too heavy without an NPU |
| cam_yolo (yolo26s-cls, 5.4M) | 85.5% | **21 MB** | Safe candidate |
| yolo26n-cls (1.5M) | 0.78–0.83 | ~3–11 MB | Designated fallback |
| Roboflow hosted v2 | 84.2% | — no weights — | Cannot run on target at all |

The most accurate model is not the deployable one until the board profiling
says so — and the hosted model was never in the running. On-device profiling
(Edge Impulse BYOM) was identified as the next step, blocked only on board
access + an API key, with the fallback chain already decided.

→ Gate 3 in full: target's compute budget shapes architecture choice;
"most accurate" ≠ "deployable"; name the fallback before you need it.

## 10. Standard results convention (the Gate 4 origin)

By the end, **three different training platforms** (Roboflow hosted, local
YOLO, local ViT) all recorded results the same way — per model version:

- `predictions.json` — per-image `{image, true, pred, confidence}`
- `metrics.json` — model/weights/eval-set identity + accuracy + per-class
  precision/recall/F1/support
- `confusion_matrix.png` — annotated heatmap titled with model + accuracy + n
- version-comparison bar charts where multiple versions existed
- JSONs committed (small, the audit trail); PNGs gitignored but regenerable

This is what made every cross-model claim above checkable. `claude_MV`
standardizes it as `tools/standard_results.py` + `docs/RESULTS_STANDARD.md`,
adding a single composite `results_card.png` per model.

---

## The lessons → rules map

| # | Lesson (evidence above) | Baseline rule |
|---|---|---|
| 1 | Calibration data contained zero defect examples; nobody knew until audited | Gate 1: audit data + state what it lacks, before changes |
| 2 | Grade labels were capture-time folder names, not validated ground truth | Gate 1: record label provenance |
| 3 | GPU sat idle under CPU-only torch; 15–20x speedup unlocked experimentation | Gate 2: compute survey before local training |
| 4 | Hosted ViT exports no weights; target needs local inference | Gate 3: deployment target & export path decided before training |
| 5 | 328MB ViT vs 21MB YOLO for an NPU-less edge board | Gate 3: model must fit target budget; keep a fallback |
| 6 | 98.1% full-dataset vs 84.2% held-out for the same model | Gate 4: always name the eval set |
| 7 | Three platforms, one results format made comparisons possible | Gate 4: standard results folder per model |
| 8 | CLAHE preprocessing dropped accuracy 84→63% | Re-test any preprocessing on held-out data |
| 9 | Offline augmentation: no gain; leakage risk without group splits | Clean-baseline evals; group-aware splits |
| 10 | ~100% crack FP rate from crop-border silhouette | Batch-measure detectors against the dataset |
| 11 | fill_ratio missed diagonal chips | Multiple independent checks for physically different failure shapes |
| 12 | transformers v5 silently un-pretrained the backbone | Pin + verification command for silent breakers |
| 13 | CPU vs GPU same-config runs differed by 5pp | Treat small deltas on small datasets as noise |
