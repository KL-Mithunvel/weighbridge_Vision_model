# TODO

## In Progress
- [ ] Gate 1 (data understanding) for the weighbridge fraud-detection
  models — SQL audit report data done (`docs/DATA_AUDIT.md`); AWS image
  data still needs inventory (counts, resolution, gross/tare pairing to
  transaction_id/serial, capture conditions) before Gate 1 is clear.
  - [x] AWS S3 access + inventory tooling built (`development/aws_s3.py`,
    `development/inventory_s3.py`, `development/config.yaml`,
    `docs/AWS_ACCESS.md`, `tests/test_aws_s3.py` — 19 tests pass). Access
    instructions from the owner documented in full in `docs/AWS_ACCESS.md`.
  - [ ] Owner: create the IAM access key, fill `.env` (see `docs/AWS_ACCESS.md`),
    confirm the bucket region.
  - [ ] Run `python development/inventory_s3.py`, commit
    `docs/data_inventory/s3_summary.json`, fold findings into
    `docs/DATA_AUDIT.md`, log in `Claude_log.md`.
  - [ ] Once the object-key layout is known, set `inventory.key_pattern` in
    `development/config.yaml` for the gross/tare ↔ serial pairing breakdown.

## Done
- [x] Turn claude_MV into the machine-vision baseline/template repo — CLAUDE.md
  with the four gates (data understanding, compute survey,
  deployment-target-first, standard results), docs (MV workflow, Tile_Sorting
  case study, deployment-target guide, results standard), tools
  (compute_survey.py, standard_results.py), model-folder template, `.CLAUDE/`
  rules library carried over from Tile_Sorting.

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
- [ ] Confirm how a `transaction_id`/`serial` in `data/wb_ai_reports.sqlite3`
  maps to the corresponding gross/tare photos in AWS — needed to join the
  existing AI report text to actual images (see `docs/DATA_AUDIT.md`).
- [ ] Plan how genuine non-firewood negative examples get sourced — none
  exist in the current SQL report data (`docs/DATA_AUDIT.md` gap).
