# CLAUDE.md — Machine Vision Baseline Rules

> This repo (`claude_MV`) is the **template** for all machine vision / model
> development projects. When a project is created from it, fill in the
> Project Overview below and keep every rules section intact.
>
> Read `.CLAUDE/CLAUDE-COMMON.md` (universal process rules: companion files,
> deployment model, CLAUDE.md skeleton) and `.CLAUDE/PROJ_STARTER.md` (owner's
> personal preferences) — both apply in full. Anything here overrides them
> only where explicitly stated.

---

## Project Overview

A company weighbridge, monitored by camera, handles vehicles bringing in
firewood: a truck is weighed loaded ("gross"), dumps its load, and is
weighed again empty ("tare"). Payment is based on the declared firewood
weight, which creates a fraud incentive — this is an integrity/fraud check,
not a quality-grading task. False negatives (missing an actual load
substitution, or a truck that wasn't fully unloaded) are the costly failure
mode.

Vision models to build:

1. **Identify the truck** in frame.
2. **Classify load state**: loaded vs. empty.
3. **If loaded**: is the visible material firewood, or something else?
   Flag if not firewood.
4. **If empty**: is it *actually* empty, or does it still have leftover
   material (rope, wood debris, etc.)? Flag if not truly empty.

- Owner: kl mithunvel (klm@smtw.in)
- License, runtime (Python version, venv location), entry points: TBD.
- Current build phase: **Gate 1 (data understanding) in progress.** An
  existing LLM-based audit system's text verdicts (769 reports, SQL) have
  been audited — see `docs/DATA_AUDIT.md`. Raw camera images live in AWS
  and have not yet been inventoried; Gate 1 is not complete until that
  happens.

---

## The Four Gates (mandatory, in order)

These gates exist because skipping each of them cost real time on the
Tile_Sorting project (see `docs/TILE_SORTING_CASE_STUDY.md` for the evidence).
**Claude must not write or modify model/pipeline code until the gates that
apply have been cleared and their outcome recorded** (in `Claude_log.md`, and
in the relevant doc under `docs/` if it's a durable decision).

### Gate 1 — Understand the data before changing anything

Before making **any** change that touches data handling, thresholds, dataset
preparation, training, or evaluation, Claude must first build (or refresh) a
factual picture of the data that actually exists, and write it down:

- **Inventory**: how many images/samples, where they live, folder layout,
  file formats, resolutions, capture conditions (lighting, background,
  distance, device).
- **Label provenance**: where each label comes from and how trustworthy it is.
  (Tile_Sorting's `3A/3B/4/5` grades came from how photos were *organized
  during capture*, not a validated grading pass — every downstream accuracy
  number inherits that caveat.)
- **Class balance**: per-class counts. Imbalance changes training strategy
  (oversampling, weighted loss) and how metrics must be read.
- **What the data does NOT contain**: Tile_Sorting calibrated its defect
  detectors on ~380 photos of *known-intact* tiles — so calibration could only
  establish a false-positive floor, never true-positive sensitivity. State
  this kind of gap explicitly instead of letting results imply more than the
  data supports.
- **Splits**: how train/val/test are made, the seed, and whether any
  augmented/near-duplicate variants of the same source image could leak
  across the split (they must not — split by source-image group).
- **Scale-dependence**: which measured/calibrated values are absolute pixels
  (do not transfer across resolution/camera distance) vs scale-independent
  ratios/colors (transfer, but still re-check under new lighting).

If the data hasn't been looked at yet in the current project, the first task
is a data audit script or notebook (Tile_Sorting's `development/analyze_dataset.py`
is the pattern: run the *real* pipeline modules over the whole dataset and
derive recommendations statistically, reporting what was excluded and why).

**Datasets never get committed to git.** `.gitignore` covers `data/`, images,
audio, and model weights. Small derived JSON records (metrics, manifests) ARE
committed — they are the audit trail.

### Gate 2 — Survey the available compute before local model development

Before starting any local training/experimentation work, run:

```bash
python tools/compute_survey.py            # prints a report
python tools/compute_survey.py --json out.json   # optionally save it
```

and record the result in `Claude_log.md`. Then act on it:

- **If an NVIDIA GPU exists, install CUDA-enabled torch before iterating.**
  On Tile_Sorting, CPU-only torch (the `requirements.txt` default) silently
  ignored an RTX 1000 Ada; installing CUDA torch gave a **15–20x speedup**
  (~12 min → ~3 min per run) — which is what made a 4-way experiment
  comparison practical at all. `requirements.txt` cannot express the CUDA
  index, so this is a documented manual step:
  `pip install torch==<ver>+cu124 torchvision==<ver>+cu124 --index-url https://download.pytorch.org/whl/cu124`
- Check VRAM against the intended model/batch size; check free disk against
  dataset + runs/checkpoints; check RAM for dataloader workers.
- Note what the survey found vs. what the code will actually use (e.g.
  `fp16=torch.cuda.is_available()` style auto-selection) — don't leave free
  compute idle, and don't assume compute that isn't there.

### Gate 3 — Ask where the model must ultimately run, FIRST

**Always question the final system architecture before choosing a training
platform or model architecture.** Work through `docs/DEPLOYMENT_TARGETS.md`
and record the answers. The two failure modes this prevents (both hit or
narrowly avoided on Tile_Sorting):

1. **Training somewhere the weights can't leave.** Roboflow's hosted ViT
   training exports **no weights** — only a hosted inference API. If the end
   system must run locally/offline/on-edge, a hosted-only model is a dead
   end regardless of its accuracy. Decide export requirements *before*
   training, not after.
2. **Training something the target can't run.** A model must fit the final
   device's compute/memory budget: Tile_Sorting's ViT-Base ONNX export is
   **328MB** vs YOLO26s-cls at **21MB** — on an edge board with no vision NPU
   (Arduino UNO Q / Raspberry Pi class), the small classification head is the
   viable candidate and the ViT is the risky one, whatever the val accuracy
   says. If the target is a Raspberry Pi–class device, the development must
   be constrained to architectures light enough to run there, from day one.

Minimum questions to answer and record (full list in the doc):

- Where does inference run in the end system? (cloud API / on-prem PC /
  laptop / SBC / MCU) Online or offline? Latency and throughput needed?
- Does that target require exportable weights? In what format
  (`.pt`/`.onnx`/`.tflite`)? Does the chosen training platform provide them?
- What are the target's CPU/GPU/NPU, RAM, and storage budgets — and does the
  candidate model fit with headroom?
- What is the profiling plan on the real target hardware, and the fallback
  architecture if the first candidate is too slow?

It is fine to use a hosted platform (e.g. Roboflow) for **dataset management,
labeling, and quick baselines** even when the target is edge — but the
production model path must be one whose weights are exportable to the target.

### Gate 4 — Every trained model gets the standard results folder

Every model version that gets evaluated must leave behind the same standard,
comparable record, next to that model's folder — see `docs/RESULTS_STANDARD.md`
for the full spec. Generate it with:

```bash
python tools/standard_results.py \
    --predictions <predictions.json> \
    --classes <cls1> <cls2> ... \
    --model-name "<model + checkpoint>" \
    --eval-set "<which split, n, and provenance>" \
    --output-dir <model_dir>/results
```

Produces: `metrics.json`, `predictions.json`, `confusion_matrix.png`,
`results_card.png` (one composite image: confusion matrix + per-class
precision/recall/F1 + run metadata), and `results.md`. JSON artifacts are
committed; PNGs are gitignored but regenerable from the committed JSON.

Reporting rules that go with it:

- **Always state which eval set a number comes from.** A full-dataset score
  is training-set fit (Tile_Sorting: 98.1% full-dataset vs 84.2% held-out for
  the same model) — never present it as generalization.
- **Comparisons must be apples-to-apples**: same images, same split. If two
  models were evaluated on different splits, re-evaluate on a common clean
  baseline split before claiming one is better.
- On small val sets, treat small deltas as noise (70/76 vs 71/76 is one
  image, not an improvement).

---

## Standard Project Layout

Follow the Tile_Sorting shape (adapt names, keep the separations):

```
<project>/
├── CLAUDE.md, TODO.md, Claude_log.md      # rules + companion files
├── requirements.txt                        # pinned deps
├── <station>_node/                         # per-hardware-station runtime code
│   └── python/<pkg>/                       #   pure logic + thin hardware wrappers
├── models/<model_name>/                    # one folder per model experiment
│   ├── config.yaml                         #   ALL tunables (see templates/model_dir/)
│   ├── prepare_dataset.py train.py val.py predict.py export_onnx.py
│   ├── results/                            #   standard results (Gate 4)
│   ├── dataset/  runs/                     #   generated, gitignored
│   └── README.md                           #   experiments log + decisions
├── development/                            # dev-only calibration/analysis tooling
├── data/                                   # datasets — gitignored, never committed
├── docs/  or  documents/                   # non-code artifacts, filed same-commit
└── tests/                                  # pytest, synthetic-input tests of pure logic
```

---

## Development Rules

1. **Hardware I/O stays separate from pure logic.** Every module touching real
   hardware (camera, mic, sensors, actuators) is a thin wrapper around pure,
   synthetic-input-testable functions. Pure logic gets pytest coverage;
   wrappers get smoke tests.
2. **No hardcoded parameters.** Device indices, thresholds, HSV ranges,
   hyperparameters, paths — all in a module-local `config.yaml`, never inline.
3. **Dev machine first, hardware last** — full staged deployment model in
   `.CLAUDE/CLAUDE-COMMON.md`. Every hardware driver needs a simulated
   equivalent that runs on the dev machine.
4. **Split hygiene**: train/val splits use a fixed seed, are reproducible from
   a script (`prepare_dataset.py`), and split by **source-image group** so
   augmented variants of one photo never straddle the split.
5. **Offline augmentation is an experiment, not a default.** Verify it against
   a clean, non-augmented baseline val split before adopting (on Tile_Sorting
   it produced no measurable gain — more *real* data was the lever). The same
   goes for preprocessing: Roboflow's CLAHE/contrast step *dropped* held-out
   accuracy 84.2% → 63.2%; never add preprocessing without a held-out re-test.
6. **Provisional thresholds are labelled provisional.** Anything calibrated on
   substitute hardware/lighting is marked as such in code + docs until
   recalibrated on the real station.
7. **Pin dependencies that silently break.** Record exact-version pins with
   the reason and a verification command (Tile_Sorting: `transformers` pinned
   `<5` because v5 silently loads a ViT backbone as randomly-initialized —
   no error, just a missable warning).
8. **Record failed experiments as thoroughly as successes** — in the model
   folder's README with the numbers, so the next session doesn't re-run them.
9. **New non-code artifacts get filed under `docs/`/`documents/` in the same
   commit that produced them.**
10. **Model weights and datasets are never committed**; small JSON
    metrics/manifests always are.

---

## Companion Files

Per `.CLAUDE/CLAUDE-COMMON.md`: maintain `TODO.md` (task tracker — move items
Not Started → In Progress → Done, never delete) and `Claude_log.md` (dated
session log) in the repo root, committed alongside the work they describe.
Gate outcomes (data audit summary, compute survey, deployment-target decision)
are logged there.

---

## User Rules

Copied per convention from `.CLAUDE/CLAUDE-COMMON.md` → Standard User Rules
and `.CLAUDE/PROJ_STARTER.md` — read both files in full; summary of the
always-active ones:

- **Open every response with "ok KLM"** followed by a one-line statement of
  what you are about to do or answer. Never skip this opener.
- **Every git commit includes** `Co-authored-by: kl mithunvel <klm@smtw.in>`
  as a trailer.
- **Documentation discipline** (full section in `CLAUDE-COMMON.md`):
  decisions and incidental facts get written down in the same session;
  multi-phase plans are written in full before execution; docs update in the
  same commit as the code — a task with stale docs is not done.
- **Explain before acting**: describe planned changes (files + what changes)
  and wait for confirmation before editing, unless the user has explicitly
  asked for autonomous completion of a stated task.
- Always activate the project venv before any Python command. Track deps in
  `requirements.txt` (pin at least major versions); flag `uv` as the planned
  migration when suggesting packaging steps.
- DRY, tests with pytest in `tests/`, explicit over clever, proper error
  handling, no deprecated APIs.
- Config in YAML; SQLite for local app data; Flask/FastAPI backends; commit
  messages in imperative mood, ≤72-char subject, never vague.

### Project-Specific Overrides

_None — add below as needed._
