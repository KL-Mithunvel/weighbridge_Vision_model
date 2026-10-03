# Claude Log

## 2026-09-06 — AWS S3 access + Gate 1 image-inventory tooling
- Owner pasted the S3 access instructions for bucket `smtw-weighbridge-archive`
  (read-only IAM access, personal access key per laptop, region TBD — example
  `ap-south-1`). Task: build the access/inventory tooling and document the
  instructions in full.
- Documented everything in `docs/AWS_ACCESS.md`: IAM key creation, region
  lookup, the three credential-passing options, list/download examples, the
  error→meaning troubleshooting table, the security rules, how it maps to the
  repo, and the Roboflow `cloud-storage` mirror as an alternative path (with the
  Gate 3 weight-export caveat).
- New tooling under `development/` (dev-only analysis, Gate 1 pattern):
  - `config.yaml` — bucket/region/prefixes/sample size/output paths, no
    hardcoding.
  - `aws_s3.py` — network I/O (`make_client`, `list_objects`,
    `download_object`, `head_object`) kept separate from pure logic
    (`credentials_status`, `summarize_objects`, `pair_gross_tare`,
    `extract_key_facets`, key helpers). `S3AccessError` maps botocore errors to
    the troubleshooting-table hints.
  - `inventory_s3.py` — paginated crawl → `data/s3_inventory/s3_objects.jsonl`
    (gitignored) + `docs/data_inventory/s3_summary.json` (committed aggregate,
    no image content) + seeded resolution sample via Pillow + console report.
    Exits cleanly with instructions when `.env` has no keys.
  - `README.md` — run order and outputs.
- `tests/test_aws_s3.py` (+ `tests/conftest.py`) — 19 pytest cases over the
  pure layer, no network. All pass. `py_compile` clean.
- Deps: added `boto3`, `python-dotenv`, `pillow`, `pytest` to
  `requirements.txt` (installed in `.venv`). Added `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` to `.env.example`.
- Updated `TODO.md` (tooling done; owner to create key + fill `.env`; run
  pending) and `docs/DATA_AUDIT.md` ("What's missing" item 1 now points at the
  tooling, still blocked on credentials).
- **Gate 1 still not complete** — the crawl has not run (no credentials yet).
- Owner committed the 12 files as `1939156` ("AWS tooling anf boto 3v").

### Evaluated `aws/agent-toolkit-for-aws` (owner asked to check for useful plugins/skills)
- **What it is**: an AWS MCP server (`call_aws` = authenticated read/write to
  300+ services, `run_script` = sandboxed Python, `search_documentation`,
  `retrieve_skill`), four Claude Code plugins (`aws-core`, `aws-agents`,
  `aws-data-analytics`, `aws-agents-for-devsecops`) from the official
  marketplace, and ~13 core + specialized skills (IaC/CDK, serverless,
  containers, billing, CloudWatch, Bedrock, …). Requires `uv`.
- **S3-relevant skills**: only two — `securing-s3-buckets` (bucket-admin
  hardening: policy/encryption/CloudTrail) and `troubleshooting-s3-files` (the
  S3 *mount* product, not the API). Neither covers plain read-only
  list/download.
- **Decision: not added.** Reasons: (1) neither S3 skill fits a read-only
  image pull; (2) `call_aws` is write-capable across all of AWS — adding it
  contradicts this project's deliberately minimal read-only posture in
  `docs/AWS_ACCESS.md`; (3) CLAUDE.md favours minimal pinned testable tooling,
  and `development/aws_s3.py` (19 tests, offline) already covers the need;
  (4) adds a `uv` dependency and a second MCP server (the Roboflow one is
  already failing to connect this session).
- **Revisit if**: the project later needs to *provision* AWS infra (Lambda,
  IaC) or do data-lake / Athena / Glue work on the archive — then `aws-core`
  or `aws-data-analytics` become relevant.
- **Own S3-access skill?** Not worth it for this project — the tooling +
  `docs/AWS_ACCESS.md` is sufficient and a skill would just duplicate it. A
  small generic "Gate 1 cloud-bucket ingestion" skill *could* be worth adding
  to the `claude_MV` template-repo lineage if the pattern recurs across
  projects; logged as a low-priority template consideration, not a task here.

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

## 2026-09-20 — Gate 1: AWS image archive inventoried

Owner supplied the IAM access key, so the blocked half of Gate 1 ran.

**Access.** `.env` created from `.env.example` (gitignored; confirmed via
`git check-ignore` and a repo-wide grep that no key string reaches a tracked
file). Bucket region confirmed `ap-south-1` via `get_bucket_location`. List
and read both work — no KMS denial.

> **Security note:** the key pair was pasted into the chat session, which
> `docs/AWS_ACCESS.md` §6 explicitly forbids. Scope is read-only on one
> bucket, so exposure is limited, but the key should be rotated. Tracked in
> `TODO.md`.

**Crawl.** `python development/inventory_s3.py` →
`docs/data_inventory/s3_summary.json` (committed),
`data/s3_inventory/s3_objects.jsonl` (gitignored).

- 10,085 objects, all JPEG, **17.64 GB**, 700 serial folders,
  median 15 photos/serial (min 2, max 18).
- Layout `weighments-YYYYMM/<serial>/<YYYYMMDD_HHMMSS_hash8>.jpg`.
- Capture range 2026-03-06 → 2026-08-05. S3 `last_modified` (2026-07-04 →
  2026-09-19) is a bulk backfill, **not** capture time — do not use it as a
  date feature.

**Findings that change downstream work:**

1. **SQL ↔ image linkage resolved.** The S3 folder name *is* the report
   `serial`. Both sides carry two conventions (dashed `YYYY-MM-DD-NNN` and
   flat `YYYYMMDD-NNN`); normalising both to the flat form joins
   **687 serials / 9,987 photos (99.0%)**. Closes a long-standing TODO.
   `inventory.key_pattern` set in `development/config.yaml` to match both —
   `keys_unmatched` went 130 → 0.
2. **74 SQL reports (all August) have no images** — the archive stops
   2026-08-05 while reports run to 2026-08-26. Needs a question to the
   bucket admin.
3. **Gross/tare is not encoded anywhere in the key.** Timestamp clustering
   (split at a >5 min gap) puts **690/700 serials into exactly 2 visits**,
   median largest gap ~22 min — consistent with weigh-in → dump →
   weigh-out. Recorded as **PROVISIONAL** per rule 6: inferred from timing,
   never visually verified. Must be hand-checked before use as a weak label.
4. **Resolution is heterogeneous** — 26/40 sampled images are 4160x1920
   (ultra-wide 2.17:1, likely stitched), but the sample also contains
   1920x1080, several irregular sizes suggesting pre-cropping, and two
   **portrait** frames (1080x1920, 1920x4160). Aspect spans 0.46–2.17. This
   is a Gate 1 scale-dependence flag: absolute-pixel values will not
   transfer, and a naive square resize would distort the majority class.
5. **All 10,085 objects are `GLACIER_IR`.** Reads are instant but billed
   per-GB retrieved — a full 17.64 GB pull costs money. Pull once, keep it.
6. **Split rule is now concrete:** split by `serial`, never by photo — a
   serial is a median of 15 near-duplicate frames of one truck in one
   session. De-duplicate the 4 dual-format serials first.

**Gate 1 is not yet closed.** Capture conditions (lighting, angle, distance,
day/night) were not assessed — the crawl measured resolution only, and that
needs actually looking at images. Open items in `TODO.md`.

No model or pipeline code was written this session.

## 2026-09-20 (2) — One entry pulled end-to-end; code + SQL review

Committed the inventory as `f44bc59`, then pulled `serial 2026-03-19-001`
(15 photos, `data/s3_inventory/entry_20260319-001/`, gitignored) and read it
against its SQL row. New doc: `docs/ENTRY_ANATOMY.md`.

**The headline finding: a serial is not a bag of truck photos.** It holds
four distinct image roles from different sources:

1. `WB INDOOR` CCTV (2688x1520) — office + Essae weight indicator. No view of
   the truck. Useless for load state; a candidate for indicator OCR.
2. `WB PLATFORM IN_2` CCTV (1920x1080) — overhead weighbridge deck, plate
   legible, fixed geometry. Vehicle ID / plate source.
3. Handheld phone photos (4160x1920 + irregular) — operator walking the
   trailer. **These are what the four project models are actually about.**
4. Weigh-slip document photo — a phone shot of the printed slip.

Both CCTV classes carry burned-in camera-name and timestamp overlays; the
phone photos do not. That explains the resolution spread recorded this
morning — it is a multi-camera rig, not a single erratic camera. The earlier
note that "some frames look pre-cropped" was wrong: they are free-pose phone
shots.

**The weigh slip is printed ground truth.** Slip 228 / 19-03-2026 08:40:07 /
`TN 76 P 8336` / gross 5830 / tare 3410 / net 2420 / material `KARUVAI`.
Declared material and declared net weight — the two quantities the fraud
question turns on — are both machine-readable, once per serial. An OCR pass
over the slips would beat the LLM prose as a label source. Added to TODO.

Linkage independently confirmed: the SQL row says "Evidence from 15 photos"
and S3 holds exactly 15 objects for that serial.

**Role split at scale (file-size proxy, PROVISIONAL — validated on one entry
only):** 3,612 CCTV-sized (<0.8MB, median 0.23MB) vs 6,473 phone-sized
(median 2.94MB); modal serial 6 CCTV + 9 phone. So the pool of images that
actually show the load close-up is well under 10,085 — per-class budgets must
be computed after role separation.

**SQL re-read (765 de-duped serials).** The positive class is effectively
absent: `plate_match` 748/9, `weight_plausible` 755/2, `consistency_score`
median 0.95 with 12 rows below 0.7, `tampering_signs` empty in 632. The most
frequent tampering string occurs *twice* — it is free text, not a taxonomy,
and cannot be a label column without manual re-categorisation.

Reading the 12 worst rows: nearly every real anomaly is a **document/metadata**
discrepancy (declared vs slip weights, plate mismatch across gross/tare, slips
dated 2024, gross and tare 10-28 seconds apart, material printed as `FULL` /
`FUEL`, missing slip). Only a minority are visually detectable — the best
example being `2026-03-17-002`, a yellow open-bed truck in gross vs a green
caged truck in tare. **Scope implication:** the existing system's value is
mostly cross-checking documents, so slip/plate OCR deserves first-class status
alongside load classification.

**Code stack review.** Sound overall: I/O and pure logic properly separated
per rule 1, config-driven per rule 2, botocore errors mapped to the
`docs/AWS_ACCESS.md` table, 19 tests green, deps pinned with reasons. Four
defects logged in `TODO.md` — two red: `objects_by_year_month` is built from
S3 upload time rather than capture time (misleading for Gate 1), and
`pair_gross_tare` emits permanent zeros because gross/tare is not in the keys.
Two amber: `download_object` re-downloads unconditionally against `GLACIER_IR`
storage (costs retrieval fees every run), and `is_image_key` reports one
undifferentiated image count that overstates the usable pool.

Still no model or pipeline code written. Gate 1 remains open.

## 2026-10-03 — Entry viewer + labelling GUI (Flask)
- Owner asked for a GUI to browse the S3 archive by date → entry number, with
  the entry's SQL report alongside, then labelling. Plan agreed in-session:
  Flask, local only, view first then labels; AWS key rotation deferred (still
  open in TODO).
- Built `development/entry_viewer/`: `index.py` (pure: serial normalisation,
  date/entry index, visit split, role guess, label validation), `sources.py`
  (download-once image cache + thumbnails, read-only reports, SQLite label
  store with append-only `label_events`), `app.py` (Flask + CLI), one HTML
  page. All tunables + the label vocabulary in `config.yaml` → `viewer:`.
- Decisions: index from the existing crawl JSONL (no S3 calls to browse);
  dates from the serial folder (capture date), not `last_modified`; images
  fetched on first view only (GLACIER_IR fees); only indexed keys fetchable;
  bound to 127.0.0.1; reports DB opened `mode=ro`; labels stored as JSON per
  (kind, target) so the vocabulary can grow without migrations.
- Found: SQL serials also use **both** conventions (`2026-03-31-002` dashed
  alongside `20260306-001`) and some serials have several reports — both
  normalised / shown as tabs.
- Fixed the TODO 🟡: `download_object(..., expected_size=)` skips when the
  cached file matches the listed size, writes via `.part` + rename;
  `inventory_s3.py` passes sizes.
- Smoke test on real data: 138 dates, 770 entries (696 with images + 74
  report-only), 10,085 photos. `2026-03-19-001` splits 7 + 8, matching
  `docs/ENTRY_ANATOMY.md`; first thumbnail 2.3 s from S3, repeat 5 ms from
  cache; role guess becomes `cctv_indoor` once resolution is known.
- Gotcha: Jinja's `tojson` sorts keys by default regardless of
  `app.json.sort_keys` — set `jinja_env.policies["json.dumps_kwargs"]` too.
- Tests: 56 pass (`tests/test_entry_viewer.py` new, `test_aws_s3.py`
  extended). No model or pipeline code; Gate 1 still open.
- Added root `main.py` (starts the viewer, opens the browser; `--no-browser`)
  and filed the agreed plan + as-built status as `docs/ENTRY_VIEWER_PLAN.md`.
  Owner then asked for a Sonnet model to build the same plan independently,
  for comparison — run in an isolated git worktree.

## 2026-10-03 (2) — Viewer readability + AWS/SQL reconciliation
- Owner: text too small; why do some entries show no photos; explain SQL vs
  photos; are there entries in AWS but not SQL, and vice versa.
- GUI: root font 14 -> 18px with all sizes in rem, A-/A+ control, bigger
  thumbnails/chips, tooltips on SQL fields, explanatory banners for
  no-photo / no-report entries, flagged dropdowns, **Coverage** panel
  (`/api/coverage`, pure `reconcile()` in index.py). 58 tests pass. Not yet
  eyeballed in a browser by me.
- Finding: 687 in both, 9 AWS-only, 74 SQL-only (all 2026-08-06+). AWS-only
  serials sit exactly at gaps in the SQL transaction_id sequence. Details in
  `docs/DATA_AUDIT.md`. Dual-spelling serials have two txn ids each.

