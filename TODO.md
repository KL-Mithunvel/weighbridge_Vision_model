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
  - [ ] Ask the bucket admin about the 74 August serials that have SQL
    reports but no images (archive stops 2026-08-05, reports run to 08-26).
  - [ ] **Rotate the AWS access key** — it was pasted into a chat session on
    2026-09-20, against `docs/AWS_ACCESS.md` §6. Create a new key, delete
    the old one, update `.env`.

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
