"""Generate the standard model-results folder (CLAUDE.md Gate 4).

Given per-sample predictions for one (model version, eval set) pair, writes
the artifacts specified in docs/RESULTS_STANDARD.md:

    metrics.json          committed — comparable summary with identity fields
    predictions.json      committed — per-sample {image, true, pred, confidence}
    confusion_matrix.png  gitignored — annotated heatmap
    results_card.png      gitignored — one composite image: header + confusion
                          matrix + per-class precision/recall/F1 bars + notes
    results.md            committed — markdown twin of the card

Usage (CLI):
    python tools/standard_results.py \
        --predictions preds.json \
        --classes 3A 3B 4 5 \
        --model-name "cam_vit (google/vit-base-patch16-224-in21k)" \
        --weights "runs/tile_grade_vit/best" \
        --eval-set "clean 76-image val split, seed 42" \
        --notes "labels are capture-time folders, not validated grading" \
        --output-dir models/cam_vit/results

`preds.json` is a list of {"image": ..., "true": ..., "pred": ..., "confidence": ...}
rows — the same shape Tile_Sorting's val.py scripts produce.

Usage (library, from a pipeline's val.py):
    from standard_results import write_standard_results
    write_standard_results(output_dir, rows, classes,
                           model_name=..., weights=..., eval_set=..., notes=...)

Requires numpy + matplotlib.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def summarize(rows: list[dict], classes: list[str]) -> dict:
    """Accuracy, confusion matrix, and per-class precision/recall/f1/support."""
    if not rows:
        raise ValueError("no prediction rows given")
    unknown = {r[k] for r in rows for k in ("true", "pred")} - set(classes)
    if unknown:
        raise ValueError(f"labels in predictions but not in --classes: {sorted(unknown)}")

    matrix = np.zeros((len(classes), len(classes)), dtype=int)
    for r in rows:
        matrix[classes.index(r["true"]), classes.index(r["pred"])] += 1
    correct = int(np.trace(matrix))

    per_class = {}
    for i, cls in enumerate(classes):
        tp = int(matrix[i, i])
        support = int(matrix[i, :].sum())
        predicted = int(matrix[:, i].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[cls] = {"precision": precision, "recall": recall, "f1": f1, "support": support}

    macro = {
        metric: float(np.mean([per_class[c][metric] for c in classes]))
        for metric in ("precision", "recall", "f1")
    }
    return {
        "accuracy": correct / len(rows),
        "num_correct": correct,
        "num_total": len(rows),
        "confusion_matrix": matrix.tolist(),
        "per_class": per_class,
        "macro_avg": macro,
    }


def _draw_confusion(ax, matrix: np.ndarray, classes: list[str]) -> None:
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes)
    ax.set_yticklabels(classes)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    threshold = matrix.max() / 2 if matrix.max() else 0.5
    for i in range(len(classes)):
        for j in range(len(classes)):
            color = "white" if matrix[i, j] > threshold else "black"
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color=color)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def plot_confusion_matrix(summary: dict, classes: list[str], title: str, out_path: Path) -> None:
    matrix = np.array(summary["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(5.5, 5))
    _draw_confusion(ax, matrix, classes)
    ax.set_title(f"{title}\naccuracy={summary['accuracy']:.1%} (n={summary['num_total']})")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_results_card(summary: dict, classes: list[str], metadata: dict, out_path: Path) -> None:
    """One composite image: header + confusion matrix + per-class P/R/F1 bars."""
    fig = plt.figure(figsize=(12, 6.5))
    grid = fig.add_gridspec(2, 2, height_ratios=[1, 5], hspace=0.35, wspace=0.3)

    header = fig.add_subplot(grid[0, :])
    header.axis("off")
    lines = [
        f"MODEL: {metadata['model']}",
        f"weights: {metadata['weights']}    eval set: {metadata['eval_set']}    generated: {metadata['generated_at']}",
        f"ACCURACY: {summary['accuracy']:.1%}  ({summary['num_correct']}/{summary['num_total']})"
        f"    macro F1: {summary['macro_avg']['f1']:.3f}",
    ]
    if metadata.get("notes"):
        lines.append(f"notes: {metadata['notes']}")
    header.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=10, family="monospace")

    ax_cm = fig.add_subplot(grid[1, 0])
    _draw_confusion(ax_cm, np.array(summary["confusion_matrix"]), classes)
    ax_cm.set_title("Confusion matrix")

    ax_bar = fig.add_subplot(grid[1, 1])
    x = np.arange(len(classes))
    width = 0.27
    for offset, metric in zip((-width, 0.0, width), ("precision", "recall", "f1")):
        values = [summary["per_class"][c][metric] for c in classes]
        bars = ax_bar.bar(x + offset, values, width, label=metric)
        ax_bar.bar_label(bars, fmt="%.2f", fontsize=7, padding=1)
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels([f"{c}\n(n={summary['per_class'][c]['support']})" for c in classes])
    ax_bar.set_ylim(0, 1.12)
    ax_bar.set_title("Per-class metrics")
    ax_bar.legend(loc="lower right", fontsize=8)

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def write_results_md(summary: dict, classes: list[str], metadata: dict, out_path: Path) -> None:
    per_class_rows = "\n".join(
        f"| {c} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['support']} |"
        for c, m in ((c, summary["per_class"][c]) for c in classes)
    )
    header = "| " + " | ".join([""] + classes) + " |"
    divider = "|" + "---|" * (len(classes) + 1)
    matrix_rows = "\n".join(
        f"| **{classes[i]}** | " + " | ".join(str(v) for v in row) + " |"
        for i, row in enumerate(summary["confusion_matrix"])
    )
    notes = f"\n**Notes:** {metadata['notes']}\n" if metadata.get("notes") else ""
    out_path.write_text(
        f"""# Results — {metadata['model']}

- **Weights:** `{metadata['weights']}`
- **Eval set:** {metadata['eval_set']}
- **Generated:** {metadata['generated_at']}
- **Accuracy:** {summary['accuracy']:.1%} ({summary['num_correct']}/{summary['num_total']}) — macro F1 {summary['macro_avg']['f1']:.3f}
{notes}
## Per-class

| class | precision | recall | f1 | support |
|---|---|---|---|---|
{per_class_rows}

## Confusion matrix (rows = true, columns = predicted)

{header}
{divider}
{matrix_rows}
"""
    )


def write_standard_results(
    output_dir: Path,
    rows: list[dict],
    classes: list[str],
    *,
    model_name: str,
    weights: str,
    eval_set: str,
    notes: str = "",
) -> dict:
    """Write the full standard results folder; returns the metrics dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows, classes)
    metadata = {
        "model": model_name,
        "weights": weights,
        "eval_set": eval_set,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
    }

    (output_dir / "predictions.json").write_text(json.dumps(rows, indent=2))
    metrics = {**metadata, "classes": classes, **summary}
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    plot_confusion_matrix(summary, classes, model_name, output_dir / "confusion_matrix.png")
    plot_results_card(summary, classes, metadata, output_dir / "results_card.png")
    write_results_md(summary, classes, metadata, output_dir / "results.md")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", type=Path, required=True, help="JSON list of {image,true,pred,confidence}")
    parser.add_argument("--classes", nargs="+", required=True, help="Class names, in display order")
    parser.add_argument("--model-name", required=True, help="Architecture + checkpoint, human-readable")
    parser.add_argument("--weights", default="", help="Path to weights or hosted model id")
    parser.add_argument("--eval-set", required=True, help="Which split, n, and provenance")
    parser.add_argument("--notes", default="", help="Caveats: label provenance, held-out vs full-dataset, ...")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.predictions.read_text())
    metrics = write_standard_results(
        args.output_dir,
        rows,
        args.classes,
        model_name=args.model_name,
        weights=args.weights,
        eval_set=args.eval_set,
        notes=args.notes,
    )
    print(f"accuracy: {metrics['num_correct']}/{metrics['num_total']} = {metrics['accuracy']:.4f}")
    print(f"Wrote metrics.json, predictions.json, confusion_matrix.png, results_card.png, results.md to {args.output_dir}")


if __name__ == "__main__":
    main()
