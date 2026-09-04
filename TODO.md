# TODO

## In Progress
- [ ] Gate 1 (data understanding) for the weighbridge fraud-detection
  models — SQL audit report data done (`docs/DATA_AUDIT.md`); AWS image
  data still needs inventory (counts, resolution, gross/tare pairing to
  transaction_id/serial, capture conditions) before Gate 1 is clear.

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
- [ ] Get AWS image data access sorted and inventoried (owner: "I have the
  camera data in AWS, will go to that later").
- [ ] Confirm how a `transaction_id`/`serial` in `data/wb_ai_reports.sqlite3`
  maps to the corresponding gross/tare photos in AWS — needed to join the
  existing AI report text to actual images (see `docs/DATA_AUDIT.md`).
- [ ] Plan how genuine non-firewood negative examples get sourced — none
  exist in the current SQL report data (`docs/DATA_AUDIT.md` gap).
