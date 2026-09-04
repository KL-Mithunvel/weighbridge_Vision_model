# <model_name>/ — model folder template

Copy this folder to `models/<model_name>/` when starting a new model
experiment. It follows the Tile_Sorting `camera_models/<name>/` convention:
one folder per model family, standard entry points, everything tunable in
`config.yaml`, results recorded to the standard (`docs/RESULTS_STANDARD.md`).

Before writing any code here, the `CLAUDE.md` gates apply: data audit done
(Gate 1), compute survey run (Gate 2), deployment target + export format
decided (Gate 3).

## Standard contents

| File | Role |
|---|---|
| `config.yaml` | ALL tunable parameters — dataset paths, class list, split seed/fraction/oversampling, checkpoint, hyperparameters, augmentation. Nothing hardcoded in scripts. |
| `prepare_dataset.py` | Builds `dataset/train/<class>/`, `dataset/val/<class>/` from the source dataset. Fixed seed; **splits by source-image group** so augmented/near-duplicate variants never straddle the split. Rerunnable. |
| `train.py` | Fine-tunes the configured checkpoint. Auto-selects GPU when available. Writes runs to `runs/<name>/`. |
| `val.py` | Evaluates a checkpoint on `val/`, builds prediction rows, and delegates artifact writing to `tools/standard_results.py` → `results/`. |
| `predict.py` | Runs a checkpoint on one image or a folder; prints prediction + confidence. |
| `export_onnx.py` | Exports to the format Gate 3 decided (ONNX/TFLite). After export: spot-check ≥20 images against the original and record file size. |
| `dataset/`, `runs/` | Generated — gitignored. |
| `results/` | Standard results for the current eval; extra `results_vs_<baseline>/` folders for other eval sets. JSONs committed, PNGs not. |

## This README is the experiments log

Keep an experiments table here (run name, backbone, device, headline metric,
per-class recall) — including failed and negative results, with numbers, so
they are never re-run out of ignorance. Record every deliberate divergence
from a reference config, and why.

| Run (`runs/<name>`) | Model | Device | top1 | notes |
|---|---|---|---|---|
| _example_ | | | | |
