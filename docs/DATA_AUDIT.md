# Data Audit — Weighbridge AI Reports (Gate 1)

Last updated: 2026-09-04. Covers the SQL side of the data only — see
"What's missing" below for what Gate 1 still needs.

## Project context

A company weighbridge, monitored by camera, handles vehicles bringing in
firewood: the truck is weighed loaded ("gross"), dumps its load, and is
weighed again empty ("tare"). Payment is based on the declared firewood
weight, which creates a fraud incentive — the concern is people gaming the
system (e.g. a truck not fully unloading, or the load not actually being
firewood).

The vision models to build (owner's stated goals):

1. **Identify the truck** in frame.
2. **Classify load state**: loaded vs. empty.
3. **If loaded**: is the visible material firewood, or something else?
   Flag if not firewood.
4. **If empty**: is it *actually* empty, or does it still have leftover
   material (rope, wood debris, etc.)? Flag if not truly empty.

This is a fraud/integrity check, not a quality-grading task — false
negatives (missing an actual substitution or non-empty truck) are the
costly failure mode, not false positives.

## Inventory — what exists right now

- `data/wb_ai_reports.sqlite3` (gitignored, never committed — see
  `.gitignore`'s `data/` rule) — two tables, 769 rows each:
  - `weighment_ai_reports` — raw fidelity copy; verdict sits as a JSON
    string in `report_json`. Ignore `report_json_path` (internal storage
    path, doesn't resolve here).
  - `ai_report_fields` — the same reports, unpacked into columns. **Use
    this one.**
- **This is not raw image data.** It's text output from an existing
  LLM-based auditing system that already looked at each transaction's
  weighbridge photos and wrote a verdict. Confirmed by inspecting
  `report_json` directly: it contains exactly the same 8 fields as
  `ai_report_fields` — no image references, no bounding boxes, no
  per-photo breakdown, nothing beyond what's already unpacked.
- The actual photos are in AWS (owner will provide access later) — **not
  yet inventoried**. Gate 1 is not complete until that happens; this
  document covers only what the SQL side can tell us today.

## Schema reference

### `ai_report_fields` (primary — use this)

| column | type | notes |
|---|---|---|
| `id` | INTEGER | row id |
| `transaction_id` | INTEGER | which weighment transaction |
| `serial` | TEXT | report serial, ~1:1 with `transaction_id` (see dedup note below) |
| `created_at` | TEXT | IST, `YYYY-MM-DD HH:MM:SS` |
| `plate_ocr` | TEXT | vehicle plate as read from photos |
| `plate_match` | INTEGER (0/1/NULL) | does OCR plate match declared vehicle |
| `load_assessment` | TEXT | free-text description of the visible load |
| `weight_plausible` | INTEGER (0/1/NULL) | is declared weight plausible for the visible load |
| `tampering_signs` | TEXT (JSON array) | `[]` = nothing found; `json.loads()` or `json_each()` |
| `consistency_score` | REAL | 0.0–1.0 overall confidence |
| `summary` | TEXT | one-paragraph verdict |
| `flags` | TEXT (JSON array) | `[]` = nothing found |
| `feedback` | TEXT, nullable | see finding below — far more often populated than expected |
| `parse_ok` | INTEGER (0/1) | 0 = malformed LLM response, fields above are empty; filter `WHERE parse_ok = 1` |

### `weighment_ai_reports` (raw fallback only)

`id`, `transaction_id`, `serial`, `report_type` (always `"full"` in this
snapshot), `report_json_path` (**unusable, ignore**), `report_json` (JSON
string, same 8 verdict fields as above), `summary_text`, `flags_json`,
`created_at`.

## Findings from this audit run (769 rows)

- **`parse_ok`**: all 769 rows = 1 in this snapshot. No malformed rows to
  filter out right now (the column/filter still matters going forward).
- **Coverage**: 2026-03-06 to 2026-08-26 (6 months), reasonably spread —
  43 to 182 rows/month, no month dominates.
- **Row identity**: 765 distinct `transaction_id`, 765 distinct `serial`
  (~1:1). 769 total rows because `transaction_id` 1 has 4 rows (same
  `serial` `20260306-001`, `created_at` seconds apart — repeated report
  generation, not 4 real transactions) and `transaction_id` 154 has 2. **If
  this table is ever used for labels, de-dupe by `serial` and keep the
  latest `created_at`.**
- **`plate_match`**: 752 match / 9 mismatch / 8 null.
- **`weight_plausible`**: 759 plausible / 2 implausible / 8 null.
- **`consistency_score`**: range 0.10–1.00, mean ≈0.95 — heavily skewed
  toward "consistent," as expected from a working, mostly-compliant
  process.
- **`feedback`**: **635/769 (82%) non-null** — this is the opposite of
  "usually NULL." Sampled values are generic process-improvement notes
  ("include visible timestamps in weighment software screenshots"), not
  incident-specific — read as boilerplate commentary from the existing
  system, not a per-transaction signal.
- **`tampering_signs`** non-empty: 133/769 (17%).
- **`flags`** non-empty: 287/769 (37%) — dominated by *procedural/paperwork*
  issues (missing weigh-slip printout, missing EXIF metadata, date/serial
  mismatches on the slip), not load-content fraud.

## What the data does NOT contain (the load-bearing gap)

- **Zero rows describe a non-firewood load.** Every one of the 765
  transactions' `load_assessment` mentions "firewood"; none match "not
  firewood" / "different material" / "non-firewood" phrasing. This dataset,
  as it stands, has **no known negative examples** for a "is this actually
  firewood" classifier. Same shape as the Tile_Sorting lesson in root
  `CLAUDE.md`: this can define what firewood normally looks like, but
  cannot establish true-positive sensitivity for detecting a substitution,
  because none is recorded here. **Any accuracy claim from this data alone
  is a false-positive floor, not a sensitivity measurement.**
- **Material variety is narrow**: "Karuvai" (a wet-firewood variety)
  accounts for 552/765 mentions; no other named species (casuarina,
  eucalyptus, subabul, etc.) appear in this snapshot's free text, though a
  material *code* `PULI` (tamarind) shows up once inside a flag about a
  paperwork mismatch. Don't assume the model generalizes to firewood
  varieties not represented here.
- **"Not truly empty" signal is present but tangled**: rope/debris/residual
  mentions appear in a meaningful minority of rows (rope: 155, debris: 53,
  residual/remnant: ~70 combined) — but most explicitly say "no visible
  remnants" (the clean/normal case), and the free text conflates two
  different things: rope used to *tie down the load* (visible in gross
  photos, normal) vs. *leftover material found in the empty/tare photos*
  (the actual signal of interest). A dedicated re-read would be needed to
  separate these before using this text as any kind of label.
- **No vehicle-type field or bounding boxes** — vehicle type is only
  inferable from free text, and mentions overlap (one description can use
  several terms): `trailer` 294, `tractor` 224, `tractor-trailer` 137,
  `three-wheeler` 86, `small truck` 40, `pickup` 16, `auto-rickshaw` 4,
  `lorry` 3.
- **No confirmed linkage yet between `transaction_id`/`serial` and the
  actual image files in AWS** — that mapping has to be established before
  any of this text can be used to weakly-label images.

## Label provenance and trustworthiness

Every field in `ai_report_fields` is **another AI system's own generated
verdict** about photos it was shown for that transaction — not
human-reviewed ground truth. Treat `load_assessment`, `flags`,
`tampering_signs`, `summary` as a *prior* — useful for defining the
taxonomy the business already cares about, and as a possible weak-label
source — but not validated ground truth for training the new vision model.
Same caveat class as Tile_Sorting's 3A/3B/4/5 grades: inherited trust, not
verified trust. `plate_match` and `weight_plausible` are the same LLM
comparing its own read against declared data — internally consistent, not
independently verified.

## Splits / scale-dependence

Not yet applicable — no images in hand. Once AWS image data is pulled,
apply the standard rule from root `CLAUDE.md`: split by source-image group
/ by transaction, fixed seed, and confirm a transaction's gross and tare
photos never straddle train/val/test (they're the same session, so
scoring one and training on the other leaks obvious context).

## What's missing before Gate 1 is fully clear

1. **Access and inventory the AWS image data**: counts, resolution, how
   gross/tare photos pair to a `serial`/`transaction_id`, capture
   conditions (lighting, angle, distance, day/night), file naming/storage
   layout. Nothing in this document substitutes for that.
   - Bucket: `smtw-weighbridge-archive` (read-only IAM access). Full access
     instructions in `docs/AWS_ACCESS.md`.
   - Tooling is ready: `development/inventory_s3.py` crawls the bucket and
     writes `docs/data_inventory/s3_summary.json`. **Blocked on the owner
     creating an IAM access key and filling `.env`.** Run it, then update
     this section with the actual figures.
2. Decide whether `ai_report_fields` text can be joined to images by
   `serial`/`transaction_id` to bootstrap weak labels (e.g., transactions
   whose `load_assessment` says "no visible remnants" as clean-empty
   examples) — useful, but doesn't fix the non-firewood-example gap above.
3. Given the total absence of non-firewood examples in this dataset, plan
   how genuine negative/fraud examples get sourced (staged synthetic
   examples? historical incidents outside this DB? manual flagging going
   forward?) before a "is it firewood or something else" classifier can be
   trained with real sensitivity, not just a false-positive floor.
