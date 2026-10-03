# Data Audit — Weighbridge AI Reports (Gate 1)

Last updated: 2026-09-20. Covers **both** the SQL report data and the AWS
image archive — see "What's missing" below for what Gate 1 still needs.

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
- ~~**No confirmed linkage yet between `transaction_id`/`serial` and the
  actual image files in AWS**~~ — **resolved 2026-09-20**: the S3 folder
  name is the `serial`; 687 serials / 9,987 photos join once both sides are
  dash-normalised. See the AWS inventory section above.

## AWS image archive inventory (crawled 2026-09-20)

Source: `python development/inventory_s3.py` against
`s3://smtw-weighbridge-archive` (`ap-south-1`). Committed record:
`docs/data_inventory/s3_summary.json`. Raw per-object listing:
`data/s3_inventory/s3_objects.jsonl` (gitignored).

| | |
|---|---|
| Objects | **10,085**, all images, **17.64 GB** |
| Formats | `.jpg` 10,058, `.jpeg` 27 — all JPEG/RGB in the sample |
| Storage class | **`GLACIER_IR` for all 10,085 objects** |
| Distinct serials | **700** (696 after de-duping the dual-format ones) |
| Photos per serial | min 2, max 18, **median 15** |
| Capture date range | 2026-03-06 → **2026-08-05** |
| S3 upload range | 2026-07-04 → 2026-09-19 (bulk backfill, not capture time) |

### Key layout

```
weighments-YYYYMM/<serial>/<YYYYMMDD_HHMMSS_hash8>.jpg
```

**Two serial-folder conventions exist**, which any consumer must handle:

- dashed `YYYY-MM-DD-NNN` — 688 serials, 9,955 photos (the norm)
- flat `YYYYMMDD-NNN` — 12 serials, 130 photos, only on 2026-03-06/07
- 4 serials (`20260307-001`…`-004`) appear under **both** — likely duplicate
  copies of the same weighment. Not yet byte-compared.

The same split exists in SQL (`weighment_ai_reports.serial`: 753 dashed, 12
flat). Normalising both sides to `YYYYMMDD-NNN` is what makes them join.

### SQL ↔ image linkage — **resolved**

The folder name *is* the report `serial`. After normalising dashes on both
sides:

| | |
|---|---|
| S3 distinct serials | 696 |
| SQL distinct serials | 761 (from 765 raw — 4 differ only by dash form) |
| **Both photos and a report** | **687** |
| Photos under a linked report | **9,987 / 10,085 (99.0%)** |
| Report but no photos | 74 — **all August 2026** |
| Photos but no report | 9 (4× Mar, 4× Jun, 1× Jul) |

The 74 report-only serials are explained by the archive stopping at
2026-08-05 while SQL reports run to 2026-08-26 — the last ~3 weeks of images
were never uploaded. Worth asking the bucket admin whether they exist.

### Gross/tare separation — **not encoded in the filenames**

Nothing in the key marks a photo as gross or tare; each serial is one flat
folder. Capture timestamps do split cleanly, though: splitting each serial's
photos at any gap > 5 minutes yields

| clusters | serials |
|---|---|
| 2 | **690 (98.6%)** |
| 3 | 4 |
| 1 | 6 |

with a median largest intra-serial gap of ~22 min (p10 14 min, p90 37 min) —
consistent with weigh-in (loaded) → dump → weigh-out (empty). So the first
cluster is *probably* gross and the second *probably* tare.

> **PROVISIONAL — do not treat as ground truth.** This is inferred from
> timing alone, never visually verified. Before it is used as a weak label,
> confirm it against a hand-checked sample (and the 10 serials that do not
> split into exactly 2 clusters need individual handling). Per root
> `CLAUDE.md` rule 6 this stays labelled provisional until verified.

### Capture conditions — heterogeneous resolution

From a seeded random sample of 40 images (all 40 downloaded and probed OK):

| resolution | n | note |
|---|---|---|
| 4160x1920 | 26 | dominant, ultra-wide 2.17:1 — likely stitched/multi-sensor |
| 1920x1080 | 5 | standard 16:9 |
| 2688x1520 | 2 | |
| 3490x1811, 3431x2049, 3140x1812, 3287x1788, 3314x1824 | 1 each | irregular — suggests cropped |
| 1080x1920, 1920x4160 | 1 each | **portrait** — rotated or a different camera |

This is not a single fixed camera geometry. Consequences for Gate 1:

- **Absolute-pixel measurements will not transfer across these images.** Per
  root `CLAUDE.md`, prefer scale-independent ratios.
- Aspect ratios span 0.46 → 2.17. A naive square resize will distort the
  ultra-wide majority badly; letterboxing or aspect-aware cropping needs to
  be an explicit, tested decision.
- The irregular sizes suggest some images are already crops of a larger
  frame — provenance per resolution class is not yet established.

### Cost / retrieval caveat

Every object is **`GLACIER_IR`** (Glacier Instant Retrieval). Reads succeed
immediately, but each GET bills a per-GB retrieval fee on top of storage. A
full 17.64 GB pull is therefore a **paid** operation, and re-pulling it
repeatedly is wasteful. Download once to local disk, keep it, and prefer the
committed JSON summary for anything that does not need pixels.

## AWS <-> SQL reconciliation (2026-10-03)

Both sides normalised to `YYYYMMDD-NNN` (S3 folders and SQL rows each use both
the dashed and flat spellings). Reproduce with the viewer's **Coverage** button
or `GET /api/coverage`.

| | serials |
|---|---|
| In S3 (photos) | 696 |
| In SQL (reports) | 761 |
| **In both** | **687** |
| **AWS only** (photos, no report) | **9** |
| **SQL only** (report, no photos) | **74** |

**SQL only — all 74 are 2026-08-06 -> 2026-08-26.** The archive stops at
2026-08-05 (last photo serial `20260805-004`); reports run on to 08-26. These
reports describe photos we cannot see. Open question for the bucket admin.

**AWS only — 9 serials, 98 photos:** `20260307-006`, `20260310-006`,
`20260310-009`, `20260318-002`, `20260611-002`..`-005`, `20260722-005`.
The SQL `transaction_id` runs 1-775 with 10 unused ids (18, 37, 40, 90, 91,
383-386, 640). **Nine of those ten line up exactly with these nine serials**
(e.g. `20260307-005` = txn 17, `-007` = txn 19, nothing for `-006`; the four
`20260611` serials fill 383-386). So the audit system never produced (or lost)
a report for these weighments. The tenth gap (90 or 91) probably belongs to
`20260318-001`, which exists in neither source (inferred). The photos are
normal: usable for the image models, but with no LLM verdict to compare
against.

**Transaction ids.** `transaction_id` runs 1-775 with 765 distinct values over
761 serials: the 4 serials stored under both folder spellings
(`20260307-001`..`-004`) each have **two** transaction ids (e.g. 9 and 13) and
six serials have re-run reports (`20260306-001` has 4). Whether the dual-spelling
pairs are one weighment ingested twice or two weighments is still unconfirmed
(TODO: byte-compare).

## Further measurements (2026-10-03)

Full list of quirks with IDs: `docs/DATA_ISSUES.md`.

- **Photos per entry** (after merging the 4 dual-spelling pairs): median 15
  (439 entries), range 2-22. Short entries: `20260309-001` (2 photos),
  `20260318-002` (2), `20260722-005` (7).
- **Capture hours** (filename clock, assumed local): 05:00-19:59 only, no
  night; 66.6% of photos fall 14:00-17:59; 12 photos before 06:00, 18 after
  19:00. Lighting itself has still not been viewed.
- **Vehicles recur heavily.** Agent-read plates give 162 distinct values; 86
  occur in more than one serial, 50 in five or more, the top one in 40
  serials; repeat plates cover 680 of ~761 serials. Plate strings are
  LLM-read (may contain OCR errors), but the conclusion stands: **splitting by
  serial does not stop the same truck appearing in train and test.** Report a
  by-vehicle split too (DI-23).

## SQL verdict distribution — the positive class barely exists (2026-09-20)

Re-read of `ai_report_fields`, de-duplicated to 765 serials:

| field | distribution |
|---|---|
| `plate_match` | **748 match**, 9 mismatch, 8 null |
| `weight_plausible` | **755 plausible**, 2 implausible, 8 null |
| `consistency_score` | median **0.95**, p10 0.90, min 0.10 — only 19 below 0.8, 12 below 0.7 |
| `tampering_signs` | **632 empty**, 133 non-empty (64 with one sign, 46 with two) |
| `flags` | 482 empty, 283 with at least one |
| `parse_ok` | 765/765 — every row parsed |

**This is a ~1–2% positive rate on an already-unverified label.** Two
weight-implausible rows in six months is not a trainable signal; it is a
handful of anecdotes. Combined with the existing "no non-firewood examples"
gap, the honest position is that this dataset can establish a **false-positive
floor** for the fraud models and nothing about true-positive sensitivity —
precisely the Tile_Sorting trap recorded in `docs/TILE_SORTING_CASE_STUDY.md`.

### `tampering_signs` is free text, not a taxonomy

Across all rows the most frequent sign string occurs **twice**. There is no
repeated categorical vocabulary to learn from — every entry is a bespoke
sentence. It cannot be used as a label column without a manual
re-categorisation pass.

### What the flagged cases are actually about

Reading the 12 lowest-consistency reports: almost every anomaly is a
**document / metadata** discrepancy, not a visual one —

- declared vs slip weight mismatches (`declared tare 4520 kg` vs `1970 kg` on
  the slip and software screenshot);
- plate mismatch between gross and tare photos, or between CCTV and the slip
  (`TN76AH0241` vs `TN76AH0245`);
- date mismatches, including slips printed with a **2024** date on a 2026
  transaction;
- gross and tare recorded 10–28 seconds apart — physically impossible for
  unloading;
- material on the slip reading `FULL` or `FUEL` rather than a wood species;
- missing weigh-slip printout.

**Implication for scope.** The existing LLM system earns most of its value by
cross-checking numbers and text across slip, software and photos — not by
looking at firewood. Only a minority of cases are visually detectable, e.g.
`2026-03-17-002`: *"Vehicle in gross photos is yellow with open bed, while tare
photos show a green truck with caged sides — possible different vehicles"*.
That one is a genuine vision positive (vehicle substitution between weighings)
and is the kind of case the planned models could catch independently.

This argues for treating **OCR of the weigh slip + plate** as first-class
alongside load classification, since that is where the observed fraud signal
actually lives. See `docs/ENTRY_ANATOMY.md`.

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

**Human labels (new source, 2026-10-03).** `development/entry_viewer/` lets a
person label photos (role, gross/tare visit, load state, material, residue)
and whole entries (visit split correct, same vehicle both visits, suspect).
These live in `data/labels/labels.sqlite3` (gitignored) with an append-only
`label_events` history recording labeller and timestamp per change. They are
the first labels in this project that are *not* inherited from another
system. Commit a JSON snapshot (`app.py --export-labels`) once labelling is
under way, and record who labelled and against which vocabulary.

## Splits / scale-dependence

Images are now inventoried (not yet pulled in bulk). The standard rule from
root `CLAUDE.md` applies, and the inventory makes it concrete:

- **Split by `serial`, never by photo.** A serial holds a median of 15
  photos of the same truck in the same session; splitting by image would
  leak near-duplicates across train/val/test and inflate every score.
- Fixed seed, reproducible from `prepare_dataset.py`.
- The 4 dual-format serials must be de-duplicated *before* splitting, or the
  same session lands on both sides.
- **Scale-dependence is a live risk here**: resolutions range 1080x1920 to
  4160x1920 (aspect 0.46–2.17). Any calibrated absolute-pixel value is
  resolution-specific and will not transfer; prefer ratios.

## What's missing before Gate 1 is fully clear

1. ~~**Access and inventory the AWS image data**~~ — **done 2026-09-20**,
   see the AWS inventory section above. What that crawl left open:
   - **Gross/tare assignment is provisional** (timestamp clustering only)
     and needs verification against a hand-checked sample.
   - **Capture conditions were not assessed** — the crawl measured
     resolution/format, but lighting, angle, distance and day/night mix
     still require actually looking at images. Timestamps show captures
     across the day; no night/day breakdown has been made.
   - **The 4 dual-format serials** have not been byte-compared to confirm
     they are true duplicates.
   - **74 August serials have reports but no images**; ask the bucket admin
     whether the 2026-08-05 → 08-26 images exist anywhere.
2. Decide whether `ai_report_fields` text can be joined to images by
   `serial`/`transaction_id` to bootstrap weak labels (e.g., transactions
   whose `load_assessment` says "no visible remnants" as clean-empty
   examples) — useful, but doesn't fix the non-firewood-example gap above.
3. Given the total absence of non-firewood examples in this dataset, plan
   how genuine negative/fraud examples get sourced (staged synthetic
   examples? historical incidents outside this DB? manual flagging going
   forward?) before a "is it firewood or something else" classifier can be
   trained with real sensitivity, not just a false-positive floor.
