# TODO

## In Progress

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
