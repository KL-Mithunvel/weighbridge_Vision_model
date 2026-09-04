# Standard Model Results Specification

**Rule (CLAUDE.md Gate 4): every model version that gets evaluated leaves the
same standard, comparable record in that model's own folder.** On
Tile_Sorting, three training platforms (Roboflow hosted, local YOLO, local
ViT) recorded results in one shared shape — that is the only reason
cross-model claims ("93.4% vs 85.5% vs 84.2%") were checkable. This spec
formalizes it, and `tools/standard_results.py` generates it.

## Folder layout

```
models/<model_name>/
├── results/                      # the model's current/native eval
│   ├── metrics.json              # committed
│   ├── predictions.json          # committed
│   ├── confusion_matrix.png      # gitignored, regenerable
│   ├── results_card.png          # gitignored, regenerable
│   └── results.md                # committed
└── results_vs_<baseline>/        # extra folder per additional eval set,
                                  # e.g. the common clean baseline split
```

One results folder = one (model version, eval set) pair. Never overwrite a
results folder with numbers from a *different* eval set — add a suffixed
folder (`results_vs_clean_baseline/` is the Tile_Sorting precedent).

## Required artifacts

### `predictions.json` — per-sample record

```json
[
  {"image": "val/3A/tile_012.jpg", "true": "3A", "pred": "3A", "confidence": 0.97}
]
```

Every evaluated sample, with the path relative to the eval set root. This is
what makes any aggregate number re-derivable and error inspection possible.

### `metrics.json` — the comparable summary

```json
{
  "model": "<architecture + checkpoint, human-readable>",
  "weights": "<path or hosted model id>",
  "eval_set": "<which split, n, provenance — e.g. 'clean 76-image val split, seed 42'>",
  "generated_at": "YYYY-MM-DDTHH:MM:SS",
  "accuracy": 0.934,
  "num_correct": 71,
  "num_total": 76,
  "confusion_matrix": [[...], ...],
  "classes": ["3A", "3B", "4", "5"],
  "per_class": {
    "3A": {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 28}
  },
  "macro_avg": {"precision": 0.93, "recall": 0.90, "f1": 0.91},
  "notes": "<caveats: label provenance, held-out vs full-dataset, ...>"
}
```

`model`, `weights`, and `eval_set` are **mandatory identity fields** — a
number without them is uninterpretable later.

### `confusion_matrix.png`

Annotated heatmap (counts in every cell), axes labelled true/predicted, title
carrying model name + accuracy + n. The off-diagonal *pattern* matters as
much as accuracy (Tile_Sorting: all errors were adjacent-grade confusions —
a qualitatively different situation from random confusion).

### `results_card.png` — the one-look standard result

A single composite image showing all the relevant data for the model:

- header: model name, weights, eval set, date, headline accuracy;
- the confusion matrix (as above);
- per-class precision/recall/F1 grouped bar chart with supports;
- a notes line for caveats.

This is the image to drop into reports/reviews instead of ad-hoc per-project
plots.

### `results.md`

Small committed markdown twin of the card (tables render in git hosting):
identity fields, accuracy, per-class table, notes. Written by the tool.

## Generating

```bash
python tools/standard_results.py \
    --predictions preds.json \
    --classes 3A 3B 4 5 \
    --model-name "cam_vit (google/vit-base-patch16-224-in21k, local fine-tune)" \
    --weights "runs/tile_grade_vit/best" \
    --eval-set "clean 76-image val split, seed 42" \
    --notes "labels are capture-time folders, not validated grading" \
    --output-dir models/cam_vit/results
```

Or from a pipeline's own `val.py`, import and call
`standard_results.write_standard_results(...)` directly — per-pipeline
`val.py` scripts should produce their rows and delegate the artifact writing
to this module rather than reimplementing it.

## Reporting rules

1. **Name the eval set with every number.** Full-dataset scores are
   training-set fit (98.1% vs the honest 84.2% on Tile_Sorting) — allowed
   only for error analysis, and labelled as such in `eval_set`/`notes`.
2. **Comparisons only on a common split.** Models evaluated on different
   splits get re-evaluated on one clean baseline before any "better/worse"
   claim (the `results_vs_<baseline>/` mechanism).
3. **Small val sets ⇒ small deltas are noise.** State counts (`71/76`), not
   just percentages, so the reader can see the resolution of the comparison.
4. **Commit the JSONs and results.md in the same commit as the work**; PNGs
   stay gitignored (regenerate anytime by re-running `standard_results.py`
   against the committed `predictions.json`, or the pipeline's `val.py`).
5. Failed/negative experiments get the same treatment — their results folder
   and a README entry are what stop them being re-run next month.
