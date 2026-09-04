# claude_MV — Machine Vision Project Baseline

Template repository for every future machine vision / model development project.
It captures the process, rules, and tooling that were proven on the
**Tile_Sorting** project (ceramic tile inspection & grading — classical CV
calibration, Roboflow-hosted training, local YOLO/ViT fine-tuning, ONNX export
for edge deployment) so new projects start from that baseline instead of
re-learning it.

## What's in here

| Path | Purpose |
|---|---|
| `CLAUDE.md` | The **machine-vision baseline rules** Claude must follow in every project created from this template — including the **four mandatory gates** (data understanding, compute survey, deployment-target-first, standard results). Layers on top of the generic library under `.CLAUDE/`. |
| `.CLAUDE/` | The pre-existing generic rules library: `CLAUDE.md` (fill-in project-brief skeleton for any project), `CLAUDE-COMMON.md` (universal workflow rules: companion files, dev-machine-first deployment model, documentation discipline), `PROJ_STARTER.md` (owner's personal preferences), `skill/` (reusable skills). |
| `docs/MV_WORKFLOW.md` | The standard end-to-end machine vision project procedure (phases, checkpoints, and what to record at each). |
| `docs/TILE_SORTING_CASE_STUDY.md` | The process actually followed in Tile_Sorting, chronologically, with every lesson learned and the rule each lesson produced. |
| `docs/DEPLOYMENT_TARGETS.md` | The deployment-target-first decision guide: questions to answer *before* choosing a training platform or architecture, with size/compute budget tables. |
| `docs/RESULTS_STANDARD.md` | The standard model-results specification — what every trained model's results folder must contain. |
| `tools/compute_survey.py` | Detects and reports all available compute (CPU, RAM, disk, GPU/VRAM, CUDA) before local model development starts. |
| `tools/standard_results.py` | Generates the standard results folder for any model: `metrics.json`, `predictions.json`, `confusion_matrix.png`, a composite `results_card.png`, and `results.md`. |
| `templates/model_dir/` | Skeleton for a per-model folder (`config.yaml` + README) following the Tile_Sorting `camera_models/<name>/` convention. |

## Starting a new project from this template

1. Create the new repo from this template (or copy the contents).
2. Fill in root `CLAUDE.md`'s **Project Overview** section for the new
   project; the rules sections stay as they are. (For a non-MV project, use
   the generic skeleton at `.CLAUDE/CLAUDE.md` instead.)
3. Reset `TODO.md` and `Claude_log.md` (keep the section skeletons).
4. On the first working session, Claude must clear the four gates in
   `CLAUDE.md` **in order** before writing any model/pipeline code:
   1. **Data understanding** — audit whatever data exists; write it down.
   2. **Compute survey** — run `python tools/compute_survey.py`; record it.
   3. **Deployment target** — answer the questions in
      `docs/DEPLOYMENT_TARGETS.md`; record the decision.
   4. **Standard results** — every model trained later gets its results folder
      via `tools/standard_results.py` (see `docs/RESULTS_STANDARD.md`).

## Provenance

Distilled from the Tile_Sorting repository (`kl-mithunvel/tile_sorting`) as of
2026-08-27. See `docs/TILE_SORTING_CASE_STUDY.md` for the full history and
evidence behind each rule.

## License

MIT — see `LICENSE`.
