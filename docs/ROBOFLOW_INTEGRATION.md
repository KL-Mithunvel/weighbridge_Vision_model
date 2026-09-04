# Roboflow Integration

This project uses the official Roboflow skills/plugin
(`github.com/roboflow/computer-vision-skills`) for dataset management,
annotation, training, and deployment via the Roboflow platform. It supplies
two things:

- **Skills** — durable product guidance, loaded on demand: `api-reference`,
  `batch-processing`, `cloud-storage`, `custom-weights-upload`,
  `data-management`, `inference`, `plans-and-pricing`, `product-navigation`,
  `training-and-evaluation`, `universe` (10 total).
- **MCP server** (`mcp.roboflow.com`) — live, authenticated tools for
  projects, images, annotation jobs, versions, training, Workflows,
  inference, and Universe search.

## Install status

Two separate installs exist and are both active:

1. **User (global) scope**, from the `roboflow` Claude Code plugin
   (`~/.claude/plugins/marketplaces/roboflow`, `roboflow@roboflow` v0.1.1,
   installed 2026-08-16) — available in every project on this machine. This
   is what supplies the `mcp__plugin_roboflow_roboflow__*` MCP tools and the
   `roboflow:*`-prefixed skills.
2. **Project-local skills**, added 2026-09-04, as plain files under
   `.claude/skills/roboflow-*` — Claude Code's actual skill-discovery
   convention (plural `skills/`), alongside `grill-me`, `PDF`, `update-docs`
   (also moved here from `.claude/skill/`, singular, which Claude Code does
   not auto-load — see below). Not the `vercel-labs/skills` CLI's default
   `.agents/` + symlink layout either (tried first, then undone). Content
   pulled from `github.com/roboflow/computer-vision-skills`, `skills/` dir.
   Meant to be **committed** — it's what makes the skills available to any
   collaborator cloning this repo, without depending on this machine's
   global plugin install. Includes one skill (`batch-processing`) not yet
   in the cached global plugin (v0.1.1).

Only the MCP server (live Roboflow API access) depends on the global plugin
+ `ROBOFLOW_API_KEY` below — the skills themselves work project-locally
regardless of plugin/API-key state.

If a future project needs a **different Roboflow workspace/API key** than
this one, switch that project's *plugin* (not skills — skills carry no
auth) to a local-scoped install instead of sharing the global key:

```bash
claude plugin install roboflow --scope local
```

### Known issue hit during install (resolved)

First attempt used `npx skills add roboflow/computer-vision-skills` (the
[vercel-labs/skills](https://github.com/vercel-labs/skills) CLI). Two
problems surfaced and were undone before anything was committed:

1. It defaults to `.agents/skills/roboflow-*` (real content) with
   `.claude/skills/roboflow-*` (**plural**) as symlinks, plus a
   `skills-lock.json` manifest — a different convention from this repo's
   existing `.claude/skill/` (**singular**). Fixed by copying the real
   content into `.claude/skill/roboflow-*` and deleting `.agents/`,
   `.claude/skills/`, and `skills-lock.json`.
2. It also staged an unrelated, unrequested rename —
   `templates/model_dir/` → `docs/templates/model_dir/` — in the git index
   (files present, 0 content diff, so `git status` reported it as a clean
   rename). Cause not confirmed; suspected interaction with this repo's
   `.CLAUDE/` (uppercase) rules-library directory colliding with Claude
   Code's own `.claude/` (lowercase) on Windows' case-insensitive
   filesystem — the installer writes to `.claude/skills/`, the *same
   physical folder* as `.CLAUDE/` here. Reverted by hand (`git restore
   --staged` + moved the files back).

**If re-running any skills/plugin installer in this repo, diff `git status`
afterward before committing** — don't assume an installer only touched what
it was asked to touch.

### `.claude/skill/` vs `.claude/skills/`

This repo previously had a `.claude/skill/` (**singular**) folder
(`grill-me`, `PDF`, `update-docs`) that predates this session. Claude Code's
actual skill loader reads `.claude/skills/` (**plural**) — the singular
folder was never being auto-discovered as invokable skills. All of it (the
3 pre-existing ones plus the 10 Roboflow ones) has been moved to
`.claude/skills/` so they're real, loadable skills.

**Case-sensitivity note**: this repo's `.CLAUDE/` (rules library:
`CLAUDE-COMMON.md`, `PROJ_STARTER.md`, etc., referenced with that exact
case throughout `CLAUDE.md`) and Claude Code's own `.claude/` resolve to
the *same physical folder* on Windows/NTFS (case-insensitive, case
-preserving). `git add`/`git status` on this setup silently re-cases new
paths under an existing differently-cased directory back to the original
case (`.CLAUDE`) unless forced with `git -c core.ignorecase=false add`,
which is what was used here to keep `.claude/skills/roboflow-*` correctly
lowercase in the git index — so a checkout on a case-sensitive filesystem
(Linux CI, a Mac case-sensitive volume) resolves it correctly as
`.claude/skills/`, not a separate stray `.CLAUDE/skills/`. The 3
pre-existing skills (`grill-me`, `PDF`, `update-docs`) came along via
`git mv`, which also preserved the lowercase destination case.

## Required: `ROBOFLOW_API_KEY`

The MCP server authenticates via the `x-api-key` header, sourced from the
`ROBOFLOW_API_KEY` environment variable. Without it, MCP tool calls fail to
connect (`CONNECTION_CLOSED`) — skills still work, but nothing that touches
live Roboflow data (project/image/training calls) will.

1. Grab the key from `app.roboflow.com/settings/api`.
2. Copy `.env.example` → `.env` (already gitignored) and set
   `ROBOFLOW_API_KEY=<key>` there — never paste the key into chat.
3. Restart the Claude Code session so the MCP server picks up the new
   environment variable.

## How this fits the Four Gates (see root `CLAUDE.md`)

- **Gate 3 (deployment target first)** applies directly to any Roboflow
  training path: Roboflow's hosted training (e.g. hosted ViT) exports **no
  weights**, only a hosted inference API. If this project's target requires
  local/offline/edge inference, only Roboflow training paths with an
  exportable weights format (`.pt`/`.onnx`/`.tflite`) are viable — confirm
  this in `docs/DEPLOYMENT_TARGETS.md` before starting a Roboflow training
  run, not after.
- Roboflow is fine to use for **dataset management, labeling, and quick
  baselines** regardless of the final target (Gate 3's explicit carve-out).
