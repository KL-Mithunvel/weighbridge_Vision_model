# Claude Log

## 2026-09-04 — Project scope + Gate 1 data audit (weighbridge fraud detection)
- User described the actual project for the first time: a company
  weighbridge monitored by camera. Vehicles bring in firewood, get weighed
  loaded ("gross"), dump the load, get weighed empty ("tare"). Payment is
  tied to declared firewood weight — fraud incentive. Models needed:
  (1) identify the truck, (2) classify load state (loaded/empty),
  (3) if loaded, is it firewood or something else (flag if not),
  (4) if empty, is it truly empty or is there leftover material (rope,
  wood debris) — flag if not. Filled this into root `CLAUDE.md` → Project
  Overview.
- User provided `wb_ai_reports.sqlite3` (this explains the file that
  appeared unexplained earlier in this session — resolved, not a mystery).
  Moved it to `data/wb_ai_reports.sqlite3` (gitignored, per this template's
  "datasets never committed" rule — it's real company transaction data).
- Ran the Gate 1 audit against it and wrote up `docs/DATA_AUDIT.md`. Key
  findings:
  - It's an **existing LLM-based audit system's text verdicts** about
    photos already analyzed per transaction — not raw images, and not
    human-verified ground truth. `report_json` in `weighment_ai_reports`
    has exactly the same 8 fields as the unpacked `ai_report_fields`
    table, confirmed by inspection — no hidden image refs or bounding
    boxes.
  - 769 rows / 765 distinct transactions (transaction_id 1 has 4 duplicate
    re-run rows, 154 has 2 — dedupe by `serial`, keep latest `created_at`,
    if this table is ever used for labels).
  - `feedback` column is non-null in 635/769 (82%) rows — contradicts the
    "usually NULL" description given; sampled values are generic
    process-improvement boilerplate, not incident-specific.
  - **Load-bearing gap**: zero rows describe a non-firewood load — every
    transaction's `load_assessment` mentions "firewood," no row matches
    "not firewood"/"different material" phrasing. This dataset alone
    cannot establish true-positive sensitivity for a "is this actually
    firewood" classifier (same shape as the Tile_Sorting known-intact-only
    calibration gap already documented in root `CLAUDE.md`).
  - Material variety is narrow (Karuvai wet firewood: 552/765 mentions;
    no other species named in free text).
  - "Not truly empty" signal exists (rope/debris/residual mentions in a
    meaningful minority of rows) but the free text conflates two things:
    rope used to tie down the *load* (normal, seen in gross photos) vs.
    leftover material found in *tare/empty* photos (the actual signal) —
    would need a dedicated re-read to separate.
  - No AWS image inventory yet — Gate 1 is **not** complete; this audit
    covers only the SQL side. Logged as the next required step.
- Updated `TODO.md` (Gate 1 now "In Progress," AWS image access + join
  question + non-firewood-negatives sourcing added as open items).

## 2026-09-04 — Roboflow plugin wiring
- User asked to plug in Roboflow (github.com/roboflow/computer-vision-skills)
  and its skills. Investigated first: the `roboflow` plugin (v0.1.1) is
  already installed at **user/global scope** on this machine — its
  marketplace source is confirmed as
  `github.com/roboflow/computer-vision-skills` (`known_marketplaces.json`),
  and all 9 skills (`api-reference`, `cloud-storage`,
  `custom-weights-upload`, `data-management`, `inference`,
  `plans-and-pricing`, `product-navigation`, `training-and-evaluation`,
  `universe`) plus the `mcp__plugin_roboflow_roboflow__*` MCP tools were
  already visible in-session — no install step was needed.
- The MCP server (`https://mcp.roboflow.com/mcp`) was failing to connect
  (`CONNECTION_CLOSED`) because `ROBOFLOW_API_KEY` was unset anywhere in the
  environment. Cannot fix this myself — the key is the user's Roboflow
  account credential and must never be pasted into chat.
- Added `.env.example` (root) and `docs/ROBOFLOW_INTEGRATION.md` documenting
  install status, the key requirement, and how it interacts with Gate 3
  (hosted training exports no weights — matters if this project's target is
  local/offline/edge). Added a TODO item to set the key.
- Open decision handed to the user: keep the shared user-scope install, or
  switch this project to `claude plugin install roboflow --scope local` for
  a project-isolated API key (relevant once workspace/key needs diverge
  across projects on this machine).
- User confirmed .env approach, then asked to "add all the roboflow
  skills." Ran `npx skills add roboflow/computer-vision-skills` to install
  all 10 skills project-locally (`.agents/skills/roboflow-*` with
  `.claude/skills/roboflow-*` symlinks + `skills-lock.json`), so the repo is
  self-contained for any collaborator rather than depending on this
  machine's global plugin. Picked up one skill (`batch-processing`) not yet
  in the cached global plugin.
  - **Caught and reverted an unrelated side effect**: the installer staged
    a rename of `templates/model_dir/` → `docs/templates/model_dir/` in the
    git index (0 content diff — a clean move, not data loss) that had
    nothing to do with skills. Undid it (`git restore --staged`, moved
    files back) before it could reach a commit. Suspected cause: this
    repo's `.CLAUDE/` (uppercase) rules library and Claude Code's own
    `.claude/` (lowercase) resolve to the same physical folder on this
    Windows/NTFS case-insensitive filesystem, which the installer's
    `.claude/skills/` write path may have interacted with unexpectedly.
    Root cause not fully confirmed. Documented in
    `docs/ROBOFLOW_INTEGRATION.md` with a standing rule: diff `git status`
    after any skills/plugin installer run in this repo before committing.
  - Nothing committed yet at that point.
- User pushed back: didn't want `.agents/` at all, wanted everything in the
  *existing* skill folder, and asked why a second `skills` (plural) folder
  had appeared in `.claude/` alongside the existing `skill` (singular) one.
  Consolidated: deleted `.agents/`, `.claude/skills/` (symlinks), and
  `skills-lock.json`; copied the real Roboflow skill content into
  `.claude/skill/roboflow-*` next to the pre-existing `grill-me`, `PDF`,
  `update-docs`. Flagged in the same turn that `.claude/skill/` (singular)
  wasn't actually being auto-loaded by Claude Code at session start (only
  `.claude/skills/`, plural, is) — none of the 3 pre-existing skills showed
  up in the available-skills list either.
- User confirmed: rename everything to `.claude/skills/` (plural, the real
  Claude Code convention). Moved all 13 skills there
  (`git mv` for the 3 pre-existing tracked ones, preserving history; plain
  `mv` + `git add` for the 10 new Roboflow ones). Hit two Windows/git
  quirks along the way, both resolved:
  - `git mv` on this setup does not auto-create the destination directory —
    had to `mkdir -p .claude/skills` first.
  - `git add` on this case-insensitive filesystem silently re-cased new
    paths back to the pre-existing `.CLAUDE` (uppercase) directory entry
    unless run as `git -c core.ignorecase=false add ...` — used that to
    keep `.claude/skills/roboflow-*` correctly lowercase in the git index,
    so it resolves correctly on a case-sensitive checkout too (not just
    Windows). Full explanation in `docs/ROBOFLOW_INTEGRATION.md`.
  - Also noticed `wb_ai_reports.sqlite3` appear untracked at the repo root
    partway through (mtime 2026-08-27, predates this repo's init commit) —
    didn't touch it, don't know its origin; flagged to the user rather than
    assumed-safe-to-ignore or deleted.
  - Still nothing committed — `.claude/skills/*` (13 skills),
    `.env.example`, `docs/ROBOFLOW_INTEGRATION.md` are staged/ready,
    awaiting explicit commit instruction.

## 2026-08-27 — Bootstrap claude_MV as the machine-vision baseline/template repo
- Read the entire Tile_Sorting repo (classical CV pipeline, calibration
  tooling, Roboflow-hosted training, local cam_yolo/cam_vit pipelines, ONNX
  export + UNO Q deployment analysis, `.CLAUDE/` rules library) to extract the
  process and lessons.
- Wrote root `CLAUDE.md` — the baseline rules for every future MV project,
  centered on four mandatory gates: (1) fully understand the available data
  before making any changes; (2) survey available compute before local model
  development; (3) question the final deployment architecture before choosing
  a training platform/model (weight exportability + target compute budget);
  (4) standard results folder for every trained model.
- Wrote `docs/`: `MV_WORKFLOW.md` (the standard end-to-end procedure),
  `TILE_SORTING_CASE_STUDY.md` (the documented process/procedure followed in
  Tile_Sorting, with the lessons→rules map), `DEPLOYMENT_TARGETS.md`
  (target-first questionnaire + budget tables), `RESULTS_STANDARD.md` (results
  spec).
- Wrote `tools/compute_survey.py` (CPU/RAM/disk/GPU/CUDA report + recommended
  actions) and `tools/standard_results.py` (metrics.json, predictions.json,
  confusion_matrix.png, composite results_card.png, results.md — modeled on
  the shared artifact shape of Tile_Sorting's val.py / evaluate_grade_model.py,
  extended with confusion matrix in metrics, macro averages, and the one-look
  results card).
- Added `templates/model_dir/` (config.yaml + README skeleton following the
  `camera_models/<name>/` convention), `.gitignore` (datasets/weights never
  committed), and `requirements.txt`. The pre-existing `.CLAUDE/` library
  (generic project-brief skeleton, CLAUDE-COMMON, PROJ_STARTER, skills) was
  kept untouched — its copies are newer than Tile_Sorting's (they carry the
  Documentation Discipline section and the "ok KLM" opener rule), so the new
  root `CLAUDE.md` layers the MV baseline on top of it rather than replacing
  it.
- Verified both tools run: compute_survey against this container,
  standard_results against cam_vit's committed predictions.json (accuracy
  reproduced exactly; all five artifacts written).
- Decision: rules live in root `CLAUDE.md` (auto-loaded by Claude Code) with
  the general library kept under `.CLAUDE/`, rather than Tile_Sorting's
  `.CLAUDE/CLAUDE.md` placement — a template repo wants the binding rules
  where the tooling reads them by default.
