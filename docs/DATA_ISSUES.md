# Data Issues and Edge Cases (catalogue)

Last updated: 2026-10-08. Every known quirk of the data and tooling in one
place, so nobody re-discovers them. Each row has an ID (`DI-nn`) that other
docs, TODO items and commit messages can cite.

Companions: `docs/DATA_AUDIT.md` (the statistics), `docs/ENTRY_ANATOMY.md` (what
one entry looks like), `docs/PROJECT_SCOPE.md` (why this matters), `docs/REFERENCE_IMPLEMENTATION.md`
(the source app that produces the data; items marked *(2026-10-08)* come from it).

**Status key:** HANDLED = code already copes with it · OPEN = needs a decision
or work · UNVERIFIED = suspected, never checked · INFO = just be aware.

Numbers come from the 2026-09-20 S3 crawl (10,085 objects) and the SQL
snapshot (769 rows) unless stated; items marked *(2026-10-03)* were measured
that day.

---

## A. Identity and linkage (S3 <-> SQL)

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-01 | **Two serial spellings** on both sides: dashed `YYYY-MM-DD-NNN` and flat `YYYYMMDD-NNN`. | S3: 688 dashed / 12 flat (flat only on 2026-03-06/07). SQL: 753 dashed / 12 flat. | A naive join silently drops ~12 serials per side. | HANDLED. Normalise both sides to `YYYYMMDD-NNN` (`normalize_serial` in `entry_viewer/index.py`, tested). |
| DI-02 | **4 serials exist in S3 under both spellings** (`20260307-001`..`-004`), and in SQL each has **two transaction ids** (001: 9 and 13, and so on). | 700 raw folders -> 696 serials. | Double-counts photos and reports; if both copies land on opposite sides of a split, that is leakage. Unknown whether it is one weighment ingested twice or two weighments. | OPEN. Viewer merges them into one entry and shows a warning. Byte-compare the photos (TODO), then de-duplicate **before** any split. *(2026-10-08)* Flat names are all from 2026-03-06/07, the app's first week; probably an early naming convention, so likely two uploads of one weighment — unconfirmed. |
| DI-03 | **Repeated reports for one transaction.** | `transaction_id` 1 has 4 rows (serial `20260306-001`, seconds apart); `transaction_id` 154 (`2026-03-31-002`) has 2. | 769 rows but 765 transactions; counting rows over-weights these. | HANDLED in viewer (one tab per report, newest first). OPEN for training: **de-dupe by serial, keep latest `created_at`** — but not for DI-02 pairs, which are different transactions. |
| DI-04 | **Gaps in `transaction_id`.** Range is 1-775, 765 distinct, so 10 ids are unused. *(2026-10-03)* | Missing: 18, 37, 40, 90, 91, 383-386, 640. | Each gap is a weighment the audit system has no report for. | INFO. 9 of the 10 line up exactly with the AWS-only serials (DI-06). The 10th (90 or 91) is probably `20260318-001`, which exists in **neither** source (inferred, not confirmed). *(2026-10-08)* A report row exists only if the AI job succeeded after `invoice_draft`, so the gaps are transactions aborted/rejected early or whose job failed 3 times; the DB `status` column will confirm. |
| DI-05 | **74 SQL-only serials** (report, no photos). | All are 2026-08-06 -> 2026-08-26. Archive's last photo serial is `20260805-004`. | The agent's verdicts for these cannot be tied to images; they are unusable as image labels. | HANDLED in viewer (listed, marked "NO PHOTOS", banner explains). *(2026-10-08)* **Explained:** originals are archived to S3 only after 45 days and only for finished transactions; crawl date 2026-09-20 minus 45 days = 2026-08-06, the exact cut. The photos almost certainly still sit on the app's NFS share. OPEN: confirm with IT and re-crawl (should now reach ~2026-08-24). |
| DI-06 | **9 AWS-only serials** (98 photos, no report). *(2026-10-03)* | `20260307-006`, `20260310-006`, `20260310-009`, `20260318-002`, `20260611-002`..`-005`, `20260722-005`. | Photos are normal but there is no agent verdict to compare a component against. | OPEN. Usable for image models; excluded from agent-vs-component comparisons. Ask why the agent skipped them (Q7 in `PROJECT_SCOPE.md`). *(2026-10-08)* Probably aborted/rejected or AI-failed transactions (see DI-04). |

## B. Images

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-07 | **Four different image roles are mixed in one folder**: `WB INDOOR` CCTV, `WB PLATFORM IN_2` CCTV, handheld phone photos, weigh-slip photo. Only the phone photos are subjects for load-state / material / residue models. | Worked example `2026-03-19-001`; `docs/ENTRY_ANATOMY.md`. | "10,085 images" overstates the usable training pool by roughly a third (plus ~700 document photos). | OPEN. Role classifier is component #1 in `PROJECT_SCOPE.md`. `is_image_key` still counts all as "image" (DI-28). |
| DI-08 | **Role split rests on a file-size proxy** (<0.8 MB = CCTV). Validated on one entry only. | 3,612 small / 6,473 large; modal entry is 6 CCTV + 9 phone; 84 entries have **no** CCTV, 4 have **no** phone photos. | Mislabelled roles would poison every per-role count. | PROVISIONAL. Viewer shows the guess with a dashed badge, switching to resolution once an image is cached. Validate against human labels or the burned-in overlay text. *(2026-10-08)* Supported by the app: 3 CCTV sources x 2 phases = 6 CCTV frames, the modal count; CCTV sizes match the configured 1920x1080 / 2688x1520. The DB `source` column (`capture` vs `upload`) would give the role split exactly. |
| DI-09 | **Heterogeneous resolution and aspect ratio**, including portrait and apparent crops. | 40-image sample: 4160x1920 (26), 1920x1080 (5), 2688x1520 (2), five irregular crops, two portrait. Aspect 0.46-2.17. | Absolute-pixel measurements will not transfer; a square resize badly distorts the ultra-wide majority. | OPEN (input-geometry policy is a TODO). Prefer ratios; make letterbox/crop an explicit, tested choice. |
| DI-10 | **Irregular photo counts per entry.** *(2026-10-03)* | Median 15 (439 entries); range 2-22 after merging DI-02 pairs. Three short entries: `20260309-001` (2 photos), `20260318-002` (2), `20260722-005` (7). | Short entries cannot have both visits; they will break assumptions of "one gross + one tare set". | INFO. Check each by hand before using. Entries with 17-22 photos may hold retakes or the DI-02 duplicates. |
| DI-11 | **Capture hours are skewed to the afternoon; lighting never looked at.** *(2026-10-03)* | From filename times: 66.6% of photos are 14:00-17:59; 12 photos before 06:00; 18 after 19:00; none at night. | Models trained here see mostly afternoon light; dawn/dusk and shadow cases are rare. | OPEN. No one has yet viewed images for lighting/angle/distance. Hours assume the filename clock is local time (DI-13). |
| DI-12 | **Gross vs tare is not recorded anywhere** — inferred by splitting photos at gaps >5 min. | 690 of 700 raw folders -> 2 clusters; 4 -> 3; 6 -> 1. Median gap ~22 min. | Wrong visit assignment would mislabel loaded vs empty. | PROVISIONAL. Viewer captions only the clean 2-visit case as "provisional gross/tare". Verify by hand; cross-check with slip weights (gross > tare). Handle the 10 odd serials individually. *(2026-10-08)* The app stores gross/tare per photo (`weighment_media.type`); once the DB is supplied use that and treat clustering as a cross-check. |
| DI-13 | **Three clocks, never reconciled**: filename timestamp (used everywhere), burned-in CCTV overlay, and possibly EXIF. | Worked example agrees to the minute, but only one entry was checked. | If camera clocks drift or differ in timezone, visit splitting and cross-camera ordering are off. | UNVERIFIED. Compare filename vs overlay vs EXIF on a sample. *(2026-10-08)* Partly answered: the filename clock is the app server's receive time in **IST** (so DI-11's hours are local time), not capture time; CCTV frames have no EXIF; phone-photo EXIF, if kept, is the real capture time. |
| DI-14 | **All objects are `GLACIER_IR`.** | 10,085 / 10,085. | Every GET incurs a retrieval fee; re-pulling the 17.64 GB archive repeatedly is wasteful. | HANDLED. `download_object` skips when the local file matches the listed size; viewer fetches an image once, only when you open its entry (~45 MB per entry). |
| DI-15 | **Whether the JPEGs carry EXIF is unknown.** The agent flags "missing EXIF metadata" in some reports. | Not examined; the crawl probed size/format/mode only. | Possible evidence-completeness signal (component #2), or a trap if upload stripped EXIF. | UNVERIFIED. Check a sample with Pillow. *(2026-10-08)* CCTV frames never have EXIF (per the app; its prompt tells the agent not to flag it). Whether phone uploads keep EXIF is unknown; the agent is told to flag its absence, and many reports do. |

## C. Labels and what the SQL data can and cannot tell us

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-16 | **Every SQL field is another AI's opinion, not ground truth.** | `plate_match`, `weight_plausible` are the agent comparing its own read to declared data. | Training on these inherits the agent's blind spots; "beating the agent" cannot be measured against itself. | INFO / policy. Human labels from the viewer are the arbiter (`PROJECT_SCOPE.md` section 5). |
| DI-17 | **The positive class barely exists, and non-firewood examples are absent.** | `plate_match` 748/9/8 null; `weight_plausible` 755/2/8 null; consistency median 0.95 with 12 rows <0.7; **0 of 765** loads described as anything but firewood. | Any accuracy is a false-positive floor, never sensitivity (Tile_Sorting trap). A 1-2% positive rate on unverified labels is anecdotes, not a training signal. | OPEN. Source real negatives: historical incidents, staged examples, or flagged cases going forward (Q4). |
| DI-18 | **Narrow material variety.** | "Karuvai" in 552/765 descriptions; no other species named; `PULI` appears once in a paperwork flag. | A material model may not generalise to other woods. | INFO. State this limit on any material result. *(2026-10-08)* See DI-37: the business also buys clay and scrap paper, so this may reflect the archive, not the business. |
| DI-19 | **"Rope" is ambiguous in the text.** | rope 155, debris 53, residual/remnant ~70; most say "no visible remnants". | Rope tying the load (normal, in gross photos) vs rope left in the empty bed (the fraud case) are conflated, so text cannot label residue. | OPEN. Needs human re-labelling; the viewer's `residue` field is for this. |
| DI-20 | **`tampering_signs`, `flags`, `feedback` are free text, not a taxonomy.** | Most frequent sign string occurs twice; `feedback` is non-null in 635/769 (82%) and is mostly boilerplate advice; `flags` is non-empty in 287/769 (37%), mostly paperwork. | Cannot be a label column without manual categorisation; `feedback` is not a per-transaction signal. | OPEN. Design a flag taxonomy if weak labels are wanted. |
| DI-21 | **Real anomalies are mostly documentary, not visual.** | Lowest-scoring reports: declared vs slip weights, plate mismatch between visits, slip dated 2024, gross/tare 10-28 s apart, material `FULL`/`FUEL`, missing slip. Only `2026-03-17-002` (yellow open-bed vs green caged truck) is a clear visual positive. | Vision models alone cover a small part of what the agent catches. | INFO. Drives the component priorities (slip reader and rules first). |
| DI-22 | **The weigh slip is declared data, and declared values are not in our dataset.** | Slip prints plate, gross/tare/net, material; the SQL has none of these as columns. | Slip OCR gives ground truth for *what was claimed*, not whether the claim was honest. Declared-vs-slip checks cannot be rebuilt without the weighbridge software's data. | OPEN (Q1 in `PROJECT_SCOPE.md`). |

## D. Splits and leakage

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-23 | **The same trucks recur constantly, so a split by serial still leaks vehicle identity.** *(2026-10-03)* | Agent-read plates: 162 distinct values; 86 appear in more than one serial; 50 in five or more; the top plate appears in 40 serials; repeat plates cover 680 of ~761 serials. (Plate strings are LLM-read and may contain OCR errors, so the true fleet may be smaller.) | Within one serial, photos are near-duplicates (median 15), so split by serial at minimum. But across serials the same truck, trailer and background repeat, so scores for load-state, residue and especially vehicle-ID are optimistic if the same vehicle is in train and test. | OPEN. Report two numbers: split by serial (in-fleet) and split by vehicle group (new-vehicle). Decide which the deployment needs once Gate 3 is answered. |
| DI-24 | **Near-duplicate frames inside a serial.** | Several phone angles within seconds; DI-02 duplicates. | Photo-level splits inflate every metric. | HANDLED in policy (split by serial group, fixed seed, from `prepare_dataset.py`); script not yet written. |
| DI-25 | **Scale dependence.** | See DI-09. | Calibrated pixel values are resolution-specific. | INFO. Re-check any threshold under new lighting and camera. |

## E. Tooling and process edge cases (found while building)

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-26 | **`objects_by_year_month` is built from S3 `last_modified`**, which is the 2026-07 -> 09 bulk backfill upload time, not capture time. | `summarize_objects` in `aws_s3.py`. | The "when was this captured" histogram is wrong. | OPEN (TODO 🔴). Derive from the filename timestamp. The viewer already uses the serial/filename date. |
| DI-27 | **`pair_gross_tare` can never work** (gross/tare is not in the key) and emits hardcoded zeros. | `s3_summary.json`. | Zeros read as "no pairs found" rather than "not determinable". | OPEN (TODO 🔴). Replace with timestamp clustering or emit `method: "not_in_key"`. |
| DI-28 | **`is_image_key` is role-blind**; summary says 10,085 "images". | See DI-07. | Overstates the usable pool. | OPEN (TODO 🟡). |
| DI-29 | **"Refresh from S3" overwrites the crawl listing in place** (`write_jsonl` truncates, then writes). | `inventory_s3.write_jsonl`. | A crash mid-write would leave a truncated `s3_objects.jsonl`, and the viewer would then show a partial archive. | OPEN. Write to a temp file and rename. The old listing is not versioned. |
| DI-30 | **AWS key was pasted into a chat on 2026-09-20 and is still live.** | `docs/AWS_ACCESS.md` section 6 forbids this. | Credential exposure. | OPEN (TODO). Create a new key, delete the old, update `.env`. |
| DI-31 | **`.CLAUDE/` and `.claude/` are the same folder on Windows**, but git tracks both spellings. | Automatic agent worktree creation failed; left an empty locked worktree `.CLAUDE/worktrees/agent-aa990c72c55e05d65` and branch `worktree-agent-aa990c72c55e05d65`. | Isolated-worktree tooling fails on this repo; stray worktree remains. | OPEN. Remove the stale worktree/branch; consider renaming one folder. Work-around used: a manual sibling worktree. |
| DI-32 | **Bugs hit and fixed while building the viewer.** | (a) `PurePosixPath` silently collapses `//` and `/./`, defeating the path-traversal guard — now raw segments are checked and `\` / `:` rejected; (b) Jinja's `tojson` sorts keys regardless of Flask's setting, scrambling label-field order — fixed via the Jinja policy; (c) `sqlite3` context managers do not close connections — now wrapped in `closing()`; (d) `JSON_SORT_KEYS` was removed in Flask 2.3 — uses `app.json.sort_keys`. | Regression risks. | HANDLED, with tests for (a) and (b). |
| DI-33 | **A thumbnail needs the full original.** | Thumbs are derived from the downloaded JPEG (~3 MB each). | Opening one entry pulls ~45 MB (and a retrieval fee) before anything shows. | INFO. Accepted trade-off; cached after first view. |
| DI-34 | **Viewer limitations.** | The GUI has not been checked in a browser by the author (routes and JS syntax only); local-only, no authentication; the role guess is size-only until an image is cached; label history is append-only but not shown in the UI. | Layout bugs may remain. | INFO. Check visually; keep bound to `127.0.0.1`. |

## F. Findings from the source application (added 2026-10-08)

Source: <https://github.com/smtwkla/WeighBridge> v0.5.6 (`docs/REFERENCE_IMPLEMENTATION.md`).

| ID | Issue | Evidence | Impact | Handling / status |
|---|---|---|---|---|
| DI-35 | **The "agent" is not one fixed system across the 769 reports.** Model `grok-4-0709` throughout our date range (changed to `grok-4.7` on 2026-09-23, after our data); the prompt changed on 03-05, 03-13, 03-14, 03-18, 06-10 and 08-08; `AI_MAX_PHOTOS` was 8 for part of 2026-03-05. | Git history of `backend/ai_prompt_template.py`. Verified in our snapshot: `feedback` is non-null in 97/156 (Mar), 43/43 (Apr), 118/124 (May), 165/167 (Jun), 182/182 (Jul), but only 30/97 (Aug) — the 08-08 change makes `feedback` null when there is nothing to report. | Comparing a component to "the agent" mixes prompt versions; the `feedback` rate (DI-20) is a prompt artefact, not a property of the data. | OPEN. Record the report date with every comparison; consider scoring post-08-08 reports separately. Future `grok-4.7` reports will differ again. |
| DI-36 | **Some stored reports are unparsed raw model output.** 8 rows have null `plate_match`: 4 hold the whole answer as fenced `json` text in `summary` (2026-05-16, 05-30, 06-01, 06-09); 4 (all 2026-05-14) have an empty summary. | The app added fence-stripping and forced JSON mode on 2026-06-10 (`525309d`); before that a fenced reply was stored as `{"summary": <text>, "flags": null}`. | These rows have no usable structured fields; reading them as "no flags" would be wrong. | OPEN. **`parse_ok` is 1 for all 8, so it does not catch them** (checked 2026-10-08) — select on `plate_match IS NULL`. Exclude them, or re-parse the fenced four from `summary`; inspect the empty four. |
| DI-37 | **The business buys more than firewood.** The agent prompt says "firewood, clay, paper"; Tally has a `Scrap Paper Purchase URD` ledger; ERP items are a group `Raw Material [R-]` with sub-groups. Our data shows only firewood (DI-17). | `ai_prompt_template.py`, `company_settings.py`. | A material model trained here may meet clay/paper in production, or the archive was filtered. | HANDLED as scope (owner 2026-10-08): firewood only for now; clay/paper out of scope. Re-open if scope widens; the app can record them, so production may still see them. |
| DI-38 | **The prompt hints at other weighbridges (there are none).** The prompt applies a 10 kg / 1% tolerance only "for weighments done on the platform weigh bridge owned by Sree Murugan Tile Works". | `ai_prompt_template.py`. | Entries from another bridge may have a different slip format and no `WB INDOOR` view. | HANDLED (owner 2026-10-08): there is only one weighbridge, so no outside-bridge subset; the prompt wording is generic. Entries lacking `WB INDOOR` are explained by CCTV timing (DI-08), not a different bridge. |
| DI-39 | **The agent sees at most 16 photos, first-N in DB order, not ranked; videos never.** | `_build_verification_context` in `ai_reports.py`. | For entries with >16 photos the verdict ignores the rest, so an "all clear" says nothing about them. Median entry is 15, so most are fully seen; the 17-22-photo entries are not. | INFO. Our components can cover the unseen photos; record the photo count per entry. |
| DI-40 | **The agent is told the declared data, so it checks consistency, not truth.** It receives gross/tare/net, invoice weight, material, vehicle and datetimes with the photos. | Same file. | A number that is *consistently* forged in the record and the photos passes. The 1.5 T / 8 T incident (Q4) is of this kind. | INFO. Reinforces Q4: independent evidence is needed (vehicle-class plausibility, duplicate scenes, review outside the weighing chain). |
| DI-41 | **`invoice_weight` is separate from `weighment_weight` and editable by the purchase incharge**; `gross_weight` / `tare_weight` are stored columns. Owner (2026-10-08): the old fraud was under a manual system and weights are now read from the scale — but the app itself has no scale link; `TabGrossWeighment.vue` is a typed number field, so the supervisor appears to key in the figure. | Software spec section 5; frontend source. | Fraud can sit in the gap, or in the entry step; neither is visible in photos. | OPEN (Q9, partly answered; confirm typed vs imported). |
| DI-42 | **Media is deleted 24 months after upload** (S3 and local; the DB row is kept with `purged_at`). | `media_retention_months` = 24; `Backup.md`. | March 2026 photos vanish from S3 around March 2028. | OPEN. Keep a local copy of the training set; do not rely on S3 as our archive. |
| DI-43 | **Doc drift in the source app**: the spec says media `source = 'nvr'`, the code writes `'capture'`. And the real DB is MariaDB while the owner said "SQLite3". | `media.py` writes `"capture"`; `ai_reports.py` tests `== "capture"`; `local_db.py`. | A filter written from the doc matches nothing; schema assumptions may not fit the supplied file. | OPEN. Check actual values on receipt; ask what format the file is and what produced it. |
| DI-44 | **Time semantics**: file name = server receive time (IST); report `created_at` = when the AI job finished; DB datetimes = IST, naive. | `storage.upload_file`; spec "Timezone policy". | Directly comparable with each other, unlike the camera overlay clock (unverified, DI-13). | INFO. |

---

## Rules that follow from these issues

1. Always normalise serials before any join (DI-01).
2. De-duplicate DI-02 pairs and repeat reports (DI-03) before building any
   label table or split.
3. Split by serial at minimum; also report a by-vehicle split (DI-23, DI-24).
4. Treat visit assignment and image role as provisional until hand-checked
   (DI-08, DI-12).
5. Never present a score without its eval set, and for fraud checks say
   "false-positive floor only" while positives are missing (DI-17).
6. Keep every download one-off; never loop over the archive casually (DI-14).
7. Treat the agent's text as a prior, not a label (DI-16, DI-20).
8. Date-stamp every comparison with the agent: its prompt and model changed
   (DI-35); skip the 8 unparsed rows (DI-36).
9. Prefer the source app's own fields (gross/tare per photo, photo source,
   declared values) over inference once its DB is supplied (DI-08, DI-12).
