# TODO

## In Progress
- [ ] Gate 1 (data understanding) for the weighbridge fraud-detection
  models — SQL audit done and **AWS image inventory done 2026-09-20**
  (`docs/DATA_AUDIT.md`). Remaining before Gate 1 can be declared clear:
  - [x] AWS S3 access + inventory tooling built (`development/aws_s3.py`,
    `development/inventory_s3.py`, `development/config.yaml`,
    `docs/AWS_ACCESS.md`, `tests/test_aws_s3.py` — 19 tests pass).
  - [x] Owner created the IAM access key; `.env` filled; region confirmed
    `ap-south-1`.
  - [x] Ran `python development/inventory_s3.py` — 10,085 images / 17.64 GB
    / 700 serials. `docs/data_inventory/s3_summary.json` committed,
    findings folded into `docs/DATA_AUDIT.md`, logged in `Claude_log.md`.
  - [x] Set `inventory.key_pattern` — layout is
    `weighments-YYYYMM/<serial>/<YYYYMMDD_HHMMSS_hash>.jpg`; both dashed and
    flat serial-folder conventions matched, 0 keys unmatched.
  - [x] **Entry viewer + labelling GUI built 2026-10-03**
    (`development/entry_viewer/`, `python development/entry_viewer/app.py`).
    Date -> entry -> photos (split into visits) beside the SQL report(s);
    photo + entry labels into `data/labels/labels.sqlite3` with history.
    This is the tool for the hand-checks below.
  - [ ] **Do a first labelling pass with the viewer** — a seeded sample of
    entries across months, labelling photo role + visit + entry
    `visit_split_correct`. Export a snapshot to `docs/labels/` and commit it.
  - [ ] **Verify the provisional gross/tare split.** Timestamp clustering
    puts 690/700 serials into exactly 2 visits (median ~22 min apart), but
    this is inferred, never eyeballed. Hand-check a sample before it is used
    as a weak label; handle the 10 serials that split into 1 or 3.
  - [ ] **Assess capture conditions** — lighting, angle, distance, day/night
    mix. The crawl measured resolution only. Needs actually viewing images.
  - [ ] Decide the input-geometry policy: resolutions span 1080x1920 to
    4160x1920 (aspect 0.46–2.17) and some frames look pre-cropped. A naive
    square resize distorts the ultra-wide majority.
  - [ ] Byte-compare the 4 serials stored under both folder conventions
    (`20260307-001`…`-004`) and de-duplicate before any split.
  - [ ] Decide what to do with the **9 AWS-only serials** (98 photos, no SQL
    report; txn ids skip those numbers) — see `docs/DATA_AUDIT.md`
    reconciliation section.
  - [ ] Ask the bucket admin about the 74 August serials that have SQL
    reports but no images (archive stops 2026-08-05, reports run to 08-26).
  - [ ] **Classify images by role before any dataset prep** — CCTV indoor /
    CCTV platform / handheld load photo / weigh-slip document. Only the
    handheld photos are subjects for the load-state and material models
    (`docs/ENTRY_ANATOMY.md`). Validate the file-size proxy on a larger
    sample, or classify by the burned-in overlay text.
  - [ ] **OCR the weigh-slip photos** — they print slip no, date, time, plate,
    gross/tare/net kg and declared material. That is per-transaction numeric
    ground truth, far stronger than the LLM prose. ~1 slip per serial.

  - [ ] **Rotate the AWS access key** — it was pasted into a chat session on
    2026-09-20, against `docs/AWS_ACCESS.md` §6. Create a new key, delete
    the old one, update `.env`.

## Added 2026-10-03 (project scope + data issues; see `docs/PROJECT_SCOPE.md`, `docs/DATA_ISSUES.md`)

- [ ] **Owner answers needed — owner is gathering data (asked 2026-10-03; Claude
  re-asks each session until answered, per `CLAUDE.md`)** (they gate the design): Q1 where declared
  values live (weighbridge-software data keyed by transaction), Q2 how the
  agent runs today, Q3 deployment target (Gate 3), Q4 real fraud examples,
  Q5 acceptable error rates, Q6 valid material list, Q7 the 74 + 9 missing
  pairs, Q8 which viewer build to keep. Record answers in
  `docs/PROJECT_SCOPE.md` and `docs/DEPLOYMENT_TARGETS.md`.
- [ ] Gate 2: run `python tools/compute_survey.py`, log the result.
- [ ] DI-23: decide the split policy — serial-grouped (in-fleet) vs
  vehicle-grouped (new-vehicle) — once Gate 3 says which matters.
- [ ] DI-13 / DI-15: compare filename vs burned-in overlay vs EXIF timestamps
  on a sample; check whether the JPEGs carry EXIF at all.
- [ ] 🟡 DI-29: make `write_jsonl` / "Refresh from S3" write to a temp file and
  rename, so a crash cannot truncate `s3_objects.jsonl`.
- [ ] DI-31: remove the stale worktree `.CLAUDE/worktrees/agent-aa990c72c55e05d65`
  and branch `worktree-agent-aa990c72c55e05d65`; consider unifying
  `.CLAUDE/` vs `.claude/` (both tracked, same folder on Windows).
- [ ] Owner to compare the Opus viewer (`main`) with the Sonnet build
  (`sonnet-entry-viewer`, `bc39724`) and pick one; delete the other branch and
  `../weighbridge_Vision_model_sonnet`.
- [ ] Verify the viewer visually in a browser (DI-34).

## Code stack review (2026-09-20)

Stack is sound — clean I/O vs pure-logic split, no hardcoded params, errors
mapped to the docs troubleshooting table, 19 passing tests, deps pinned with
reasons. Four real defects found:

- [ ] 🔴 `summarize_objects` builds `objects_by_year_month` from
  `last_modified`, which is the **S3 upload time** (a 2026-07→09 bulk
  backfill), not capture time. As a Gate 1 "when was this data captured"
  histogram it is actively misleading. Capture time is in the filename
  (`YYYYMMDD_HHMMSS_`) — derive the month from the key instead.
- [ ] 🔴 `pair_gross_tare` cannot work as written: gross/tare is not in the
  keys, so `serials_with_gross_and_tare` / `_gross_only` / `_tare_only` are
  hardcoded-zero in every summary and read as "no pairs found" rather than
  "not determinable from keys". Replace with the timestamp-cluster method,
  or emit an explicit `method: "not_in_key"` field.
- [x] 🟡 **Fixed 2026-10-03.** `download_object` re-downloads unconditionally. Every
  `inventory_s3.py` run re-pulls the 40-image sample, and all objects are
  `GLACIER_IR` — **each re-run costs retrieval fees**. Skip when the local
  file exists with a matching size/etag.
- [ ] 🟡 `is_image_key` counts every object as one undifferentiated "image",
  producing `image_objects: 10085`. Now that four image roles are known,
  that number overstates the usable training pool. Add role classification
  to the summary.

## Done
- [x] Turn claude_MV into the machine-vision baseline/template repo — CLAUDE.md
  with the four gates (data understanding, compute survey,
  deployment-target-first, standard results), docs (MV workflow, Tile_Sorting
  case study, deployment-target guide, results standard), tools
  (compute_survey.py, standard_results.py), model-folder template, `.CLAUDE/`
  rules library carried over from Tile_Sorting.

- [x] Confirm how a `transaction_id`/`serial` in `data/wb_ai_reports.sqlite3`
  maps to the corresponding gross/tare photos in AWS — **done 2026-09-20**:
  the S3 folder name is the `serial`. 687 serials / 9,987 photos (99.0%)
  join once both sides are normalised to `YYYYMMDD-NNN`. Gross vs tare is
  *not* in the key and remains provisional (see In Progress).

## Not Started
- [ ] Exercise the template on the next new MV project and fold back anything
  that turned out awkward in practice.
- [ ] Add a `.tflite` export recipe alongside ONNX in the model-folder template
  once a project actually needs it (MCU-class target).
- [ ] Evaluate the planned pip→`uv` migration for this template's setup steps.
- [ ] Set `ROBOFLOW_API_KEY` in a project-local `.env` (see `.env.example`,
  `docs/ROBOFLOW_INTEGRATION.md`) to activate the Roboflow MCP server —
  plugin/skills are already installed (user scope) but MCP calls currently
  fail with `CONNECTION_CLOSED` for lack of a key.
- [ ] Evaluate mirroring `smtw-weighbridge-archive` into Roboflow via the
  `cloud-storage` skill as an alternative/addition to the local pull
  (`docs/AWS_ACCESS.md` §8) — decide after the local inventory is in.
- [ ] Plan how genuine non-firewood negative examples get sourced — none
  exist in the current SQL report data (`docs/DATA_AUDIT.md` gap).
