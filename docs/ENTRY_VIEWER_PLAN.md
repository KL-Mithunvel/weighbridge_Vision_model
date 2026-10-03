# Entry Viewer + Labelling GUI — Plan and Status

Agreed with the owner 2026-10-03. **Status: phases 1–4 done** (built by
Claude Opus 5.5, same day). Run with `python main.py`. Usage details:
`development/README.md` → "Entry viewer + labelling GUI".

## Goal

A GUI that connects to the S3 archive (`smtw-weighbridge-archive`) so the data
can be understood one weighment at a time:

1. Choose a **date**.
2. Choose the **entry number** for that date (`-001`, `-002`, …).
3. Display that entry's photos **alongside its SQL report** from
   `data/wb_ai_reports.sqlite3` → `ai_report_fields`.
4. Then (phase 2, owner's request): **label** photos and entries.

It serves the open Gate 1 items: hand-checking the provisional gross/tare
split, assessing capture conditions, and separating image roles.

## Owner decisions

| Question | Decision |
|---|---|
| GUI technology | **Flask** + one HTML page (matches the Flask/FastAPI stack preference) |
| Labelling | **Yes**, after the viewer |
| AWS key rotation | Later — still open in `TODO.md` |

## Design decisions (from existing repo knowledge)

| Decision | Reason |
|---|---|
| Index built from the crawl `data/s3_inventory/s3_objects.jsonl`; a *Refresh from S3* button re-lists | Browsing costs zero S3 calls; the crawl already has every key |
| Date taken from the serial folder, not S3 `last_modified` | `last_modified` is the Jul–Sep backfill upload time (TODO 🔴) |
| Serials normalised to `YYYYMMDD-NNN` on **both** sides | S3 folders *and* SQL rows use both dashed and flat conventions |
| Images downloaded on first view only, cached in `data/viewer_cache/` + thumbnails | All objects are `GLACIER_IR` — every GET costs a retrieval fee |
| Only keys present in the index can be fetched; cache paths validated | No arbitrary object / path access |
| SQLite reports opened read-only (`mode=ro`) | The viewer must never change audit data |
| Bound to `127.0.0.1` | The app uses the owner's AWS keys |
| Visit split (gap > N min) and role guess shown as **provisional** | Both are unverified inferences (`DATA_AUDIT.md`, `ENTRY_ANATOMY.md`) |
| Labels in `data/labels/labels.sqlite3`, fields stored as JSON, append-only `label_events` history | Vocabulary can grow in config without migrations; label provenance is preserved |
| Everything tunable in `development/config.yaml` → `viewer:` | Development Rule 2 — no hardcoded parameters |

## Layout

```
┌ Date ▾ ┐ ┌ Entry ▾ (photos · report · labelled) ┐ ◀ ▶   Labeller [__] Export  Refresh S3
├──────────── PHOTOS ────────────────────┬──── SIDE PANEL ──────────┤
│ Visit 1 — provisional gross            │ Entry labels (chips)     │
│ [thumb][thumb][thumb]…                 │ SQL report (tabs if >1): │
│ Visit 2 — provisional tare             │  plate / match, weight   │
│ [thumb][thumb]…[slip]                  │  plausible, consistency, │
│ click → full image + photo label panel │  load, tampering, flags, │
│                                        │  summary, feedback       │
└────────────────────────────────────────┴──────────────────────────┘
```

Label vocabulary (config `viewer.labels`):

- **photo** — `role` (cctv_indoor / cctv_platform / phone_load / weigh_slip /
  other), `visit` (gross / tare / unsure), `load_state` (loaded / empty /
  partial / not_visible), `material` (firewood / not_firewood / mixed / unsure
  / n/a), `residue` (clean / residue / unsure / n/a), notes.
- **entry** — `visit_split_correct`, `vehicle_same_both_visits`, `suspect`
  (yes / no / unsure), notes.

## Code structure (Development Rule 1: I/O separate from pure logic)

| File | Role |
|---|---|
| `main.py` | Root launcher — starts the app and opens the browser |
| `development/entry_viewer/index.py` | Pure logic — serial normalisation, index, visit split, role guess, label validation |
| `development/entry_viewer/sources.py` | Thin I/O — image cache, read-only reports, label store |
| `development/entry_viewer/app.py` | Flask routes + CLI (`--export-labels`) |
| `development/entry_viewer/templates/`, `static/` | The single page |
| `tests/test_entry_viewer.py` | Synthetic keys, temp SQLite, fake S3 client |

## Phases

| # | Phase | Status |
|---|---|---|
| 1 | Pure index logic + tests | ✅ done |
| 2 | Cached S3 fetch + thumbnails, fix `download_object` re-download | ✅ done |
| 3 | Flask server + UI, then labelling | ✅ done |
| 4 | Docs, TODO, Claude_log | ✅ done |

## Verification (real data, 2026-10-03)

138 dates · 770 entries (696 with images + 74 report-only) · 10,085 photos.
`2026-03-19-001` splits 7 + 8, matching `ENTRY_ANATOMY.md`. First thumbnail
2.3 s from S3, repeat 5 ms from cache. 56 tests pass.

## Next

- First labelling pass over a seeded sample of entries; commit an exported
  snapshot under `docs/labels/`.
- A Sonnet-built implementation of this same plan is being produced
  separately for comparison (see `Claude_log.md`).
