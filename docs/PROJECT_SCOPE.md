# Project Scope, Direction and Status

Last updated: 2026-10-08. Written after the owner gave the wider context for
the project; supersedes the narrower "four vision models" framing in earlier
docs (those four models are still wanted — they are now *components* of the
design below).

> **Source system.** The production app that creates all of this data is
> <https://github.com/smtwkla/WeighBridge> (private; read 2026-10-08 at v0.5.6,
> commit `36022b2`). What we learned from it is in
> `docs/REFERENCE_IMPLEMENTATION.md`; it is read-only for us.

---

## 1. Direction (owner's brief, 2026-10-03)

There is already an **AI agent in production** that audits weighbridge
transactions from their evidence (photos, weigh slip, weighbridge-software
screenshots) and writes a verdict per transaction. Its output is the 769-row
SQL snapshot in `data/wb_ai_reports.sqlite3`.

The goal is **not to replace that agent wholesale.** The agent stays because
it can notice things nobody anticipated — manual tampering, odd paperwork,
situations no rule or classifier was built for. The goal is to **build more
systems that work alongside it** — vision models and ordinary deterministic
programs — and let them take over the checks that are predictable, so that:

- the predictable checks become cheaper, faster, repeatable and auditable;
- the agent's attention is spent on the residual, unanticipated cases;
- every check we move out of the agent has been *measured* to be as good or
  better, not assumed to be.

The data collected so far (S3 photos + SQL reports) is what these systems are
developed and judged on.

> **Design principle: per-check replacement, never wholesale.** A component
> takes over one named check from the agent only after it has beaten or matched
> the agent *on that check* against human labels (section 5). Until then it runs
> in shadow next to the agent. False negatives are the costly failure mode
> (root `CLAUDE.md`), so the agent remains the safety net for anything a
> component does not cover or is unsure about.

---

## 2. What the existing agent does (as observed from its output)

**Known since 2026-10-08 (from the app's source,
`docs/REFERENCE_IMPLEMENTATION.md` section 3):** the agent is xAI **Grok**
(`grok-4-0709` from 2026-03-05, `grok-4.7` from 2026-09-23, temperature 0.2),
called by a Redis-queue worker when a transaction reaches `invoice_draft`. It
sees at most **16 photos** (first 8 gross + first 8 tare, not ranked), the
declared weighment/invoice data and pre-extracted EXIF, and its prompt is
checked into the repo. Cost and latency per report are still unknown. The
prompt and model changed during the 769 reports' date range, so they are not
one homogeneous agent (DI-35). What its reports show:

| SQL field | What it carries |
|---|---|
| `plate_ocr`, `plate_match` | Plate it read; whether it matched the declared vehicle |
| `load_assessment` | Free-text description of the load (always says firewood) |
| `weight_plausible` | Whether declared weight is plausible for the visible load |
| `consistency_score` | Its own 0-1 confidence everything agrees (median 0.95) |
| `tampering_signs`, `flags`, `summary`, `feedback` | Free-text findings |

**Where the agent's value actually is** (from reading the lowest-scoring
reports, `docs/DATA_AUDIT.md`): almost every real anomaly is a
**document/metadata discrepancy** found by cross-checking slip, software
screenshot and photos — declared vs slip weight, plate mismatch between
visits, slip dated 2024 on a 2026 transaction, gross and tare 10-28 s apart,
material printed `FULL`/`FUEL`, missing slip. Only a minority are visually
detectable (the clearest: `2026-03-17-002`, a yellow open-bed truck in gross
vs a green caged truck in tare). That shapes the priorities below.

---

## 3. Target design — a hybrid pipeline

```
 evidence per entry (serial)                     checks                      outcome
┌────────────────────────────┐   ┌──────────────────────────────────┐
│ S3 photos (CCTV x2, phone  │──▶│ A. deterministic programs        │──┐
│ x ~9, slip photo)          │   │    (rules, arithmetic, OCR+parse)│  │
│ weighbridge-software data  │   ├──────────────────────────────────┤  ├─▶ agreement /
│ (declared values) [see Q1] │──▶│ B. vision models                 │──┤   arbitration
│ weigh slip                 │   │    (role, load state, material,  │  │   layer
└────────────────────────────┘   │     residue, same-vehicle)       │  │      │
              │                  ├──────────────────────────────────┤  │      ▼
              └─────────────────▶│ C. existing AI agent (generalist)│──┘  flag / pass /
                                 │    unanticipated cases           │     human review
                                 └──────────────────────────────────┘
```

Disagreement between A/B and C is itself a signal: where they differ, route to
human review and use the case as a labelled example.

---

## 4. Candidate components

Everything here is a **proposal for the owner to confirm**, not a decision.
"Replaces" names the agent behaviour the component would take over *if it
proves out*.

| # | Component | Kind | Replaces / adds | Data it can be built on today | Blocker / risk |
|---|---|---|---|---|---|
| 1 | **Image-role classifier** (CCTV indoor / CCTV platform / handheld load / slip) | small vision model, or rule on resolution + overlay text | Gates everything else; replaces "which photo is which" reasoning | 10,085 photos; size proxy gives a provisional split (36% CCTV / 64% phone) | Needs a human-labelled sample to validate the proxy |
| 2 | **Evidence-completeness check** (photo count, roles present, slip present, timestamps present) | rules | Agent flags like "missing weigh-slip printout", "missing EXIF" | S3 listing + role classifier | Depends on #1; EXIF presence not yet checked |
| 3 | **Weigh-slip reader** (slip no, date, time, plate, gross, tare, net, material) | OCR + parser | Reading the slip is the agent's core cross-check | ~1 slip photo per serial (~700) | OCR quality on dot-matrix phone photos untested |
| 4 | **Slip arithmetic and sanity rules** (net = gross - tare; slip date = capture date; gross/tare time gap plausible; material is a known wood species) | rules on #3 output | Catches the 2024-date, 10-28 s, `FULL`/`FUEL` cases without an LLM | Needs #3 | Needs a list of valid material codes from the owner |
| 5 | **Declared-vs-slip cross-check** (declared weights/plate/material vs slip) | rules | Declared-vs-slip weight mismatches | Slip via #3 | **Declared values are not in our data at all** (Q1) |
| 6 | **Plate read and consistency** across gross, tare, CCTV, slip | plate OCR + string match | `plate_ocr` / `plate_match` | Platform CCTV has legible plates | Plate-repeat leakage when splitting (see DI-23) |
| 7 | **Weight-indicator reader** (Essae display in `WB INDOOR` CCTV) | OCR | Independent live reading to compare with the slip | ~one `WB INDOOR` frame per visit | Untested; 84 serials have no CCTV at all |
| 8 | **Visit / gross-tare assignment** | rules (timestamp clusters, then slip weights) | Provisional split becomes a verified one | Timestamps; 690/700 serials give 2 clean clusters. **The app records it per photo (`weighment_media.type` l/e) — join that in once the DB arrives; clustering then becomes a cross-check, not the source.** | 10 irregular serials; needs hand-check; the DB must actually be supplied (Q1) |
| 9 | **Same-vehicle-across-visits** | vision embedding / colour+type match | The `2026-03-17-002` case (vehicle substitution) | Few positives exist | Only one known positive; needs staged or future examples |
| 10 | **Load state** (loaded / empty) | vision classifier | Basic gross/tare sanity | Plentiful and fairly clean | Cheap, likely first vision win |
| 11 | **Residue in the empty bed** (rope, wood debris) | vision classifier | "Is it truly empty?" — the fraud case from the brief | Tare photos plentiful, but no labels | SQL text mixes tie-down rope with leftover rope; needs human labels |
| 12 | **Material: firewood vs other** | vision classifier | "Is the load really firewood?" | Many firewood examples | **Zero non-firewood examples exist** (DI-17); can only establish a false-positive floor |
| 13 | **Arbitration layer** | rules + logging | Combines 1-12 with the agent's verdict, routes disagreements | Needs components | Needs the human-review process defined |

**Suggested order (owner to confirm):** #1 role classifier and #3 slip reader
first, because they unlock most of #2, #4-#8 and because the observed fraud
signal lives in documents. #8 and #10 are cheap wins. #11, #12 and #9 need
labelled or staged data before they can be trusted, so start collecting that
now (the labelling GUI exists for this).

---

## 5. How a component earns the right to replace an agent check

1. **Human-labelled reference set.** The agent's verdicts are not ground truth
   (they are another AI's output), so the arbiter is a person. The entry viewer
   (`development/entry_viewer/`) is how those labels are made.
2. **Same entries, same split, per check** (root `CLAUDE.md` Gate 4: state the
   eval set; apples-to-apples). Compare component vs agent on the checks the
   component claims.
3. **Judge on missed anomalies first.** Recall on real anomalies matters more
   than overall accuracy; with ~1-2% positives, accuracy is meaningless. The
   honest report for most checks is "false-positive floor only" until positives
   exist (DI-16, DI-17).
4. **Shadow period.** Run beside the agent on live transactions for an agreed
   period, log disagreements, review them. Length of that period is an owner
   decision.
5. **Agent stays for the residual.** Anything outside a component's declared
   coverage, or below its confidence threshold, still goes to the agent.

Labels needed beyond what exists are listed in `TODO.md`; the labelling
vocabulary is `viewer.labels` in `development/config.yaml`.

---

## 6. Status of work to date

Gate status (root `CLAUDE.md`): **Gate 1 in progress; Gates 2, 3, 4 not yet
started.** No model or pipeline code has been written; the tooling below is
all Gate 1 data understanding.

| Done | Where | Notes |
|---|---|---|
| AWS S3 access + docs | `docs/AWS_ACCESS.md`, `development/aws_s3.py` | Read-only IAM key, region `ap-south-1`. **Key was pasted into a chat on 2026-09-20 and is still not rotated.** |
| S3 inventory | `development/inventory_s3.py`, `docs/data_inventory/s3_summary.json` | 10,085 images, 17.64 GB, all `GLACIER_IR` |
| SQL audit | `docs/DATA_AUDIT.md` | 769 rows / 765 distinct transactions / 761 normalised serials |
| SQL <-> S3 linkage | `docs/DATA_AUDIT.md` | Folder name = serial; 687 in both, 9 AWS-only, 74 SQL-only |
| Entry anatomy | `docs/ENTRY_ANATOMY.md` | Four image roles; slip is machine-readable ground truth for *what was declared* |
| Entry viewer + labelling GUI | `development/entry_viewer/`, run `python main.py` | Commits `94037d1`, `5a6237a`; 58 tests pass |
| Viewer plan | `docs/ENTRY_VIEWER_PLAN.md` | Agreed design and as-built status |
| Download fix | `development/aws_s3.py` | Re-downloads no longer repeat on `GLACIER_IR` |
| Edge-case catalogue | `docs/DATA_ISSUES.md` | Every known data/tooling issue, with status |
| Reference implementation read | `docs/REFERENCE_IMPLEMENTATION.md` | Source app <https://github.com/smtwkla/WeighBridge> v0.5.6 read 2026-10-08: agent, schema, CCTV capture, archive, deployment. Answers most of Q2, part of Q1/Q3/Q6/Q7; raises Q9-Q11. |
| Independent Sonnet build for comparison | branch `sonnet-entry-viewer` (`bc39724`) in `../weighbridge_Vision_model_sonnet` | Same plan, built blind. **Not merged; owner has not chosen yet.** |

Known open tooling defects (details in `TODO.md`): `objects_by_year_month`
uses upload time not capture time; `pair_gross_tare` emits permanent zeros;
`is_image_key` counts all four roles as "image".

---

## 7. Open questions for the owner

These block or shape the work; none can be answered from the repo. **Status
column: Open until the owner answers — then record the answer under the
question, mark it Answered, and fold it into the relevant doc.** Claude asks
every Open question at the start of each session (root `CLAUDE.md`, Project-
Specific Overrides). Asked and handed to the owner on 2026-10-03.

| Q | Topic | Status |
|---|---|---|
| Q1 | Where the declared values live | Partly answered (2026-10-08) — awaiting the file |
| Q2 | How the AI agent runs today | Mostly answered from source (2026-10-08) — cost/latency still open |
| Q3 | Deployment target (Gate 3) | Open — environment facts now known, decision not made |
| Q4 | Real fraud examples | Answered (2026-10-08) — one incident; more welcome |
| Q5 | Acceptable error rates | Open |
| Q6 | Valid material list | Partly answered from source (2026-10-08) — full list is in the DB |
| Q7 | The 74 August + 9 AWS-only serials | Explained from source (2026-10-08) — needs owner/IT confirmation |
| Q8 | Which viewer build to keep | Open |
| Q9 | How gross/tare weights enter the app | Partly answered (2026-10-08) — fraud was the old manual system; entry step in the current app still to confirm |
| Q10 | Non-firewood materials and other weighbridges | Answered (2026-10-08) — one weighbridge; firewood only for now |
| Q11 | Which camera is which | Open (new 2026-10-08) |

**Q1 — Where do the declared values live?** The SQL snapshot has no
structured declared plate, gross/tare/net or material — only the agent's prose
about them. To replace declared-vs-slip checks (#5) we need the weighbridge
software's transaction table. *Bring:* a CSV/Excel/database export with one
row per weighment (`transaction_id`, declared plate, gross, tare, net,
material, weighing times), or the table name and where that database sits.

> **Owner answer (2026-10-08):** the database contains all the values; it is a
> **SQLite3 file**. Owner will supply it. Until it arrives, Q1 stays open: no
> table/column names are known, and the file's path, schema and its
> relationship to the 769-report SQL snapshot must be inspected on receipt
> (Gate 1) before any declared-vs-slip check is designed.
>
> **From the app's source (2026-10-08, `docs/REFERENCE_IMPLEMENTATION.md`
> sections 5-6):** the declared values live in table
> **`weighment_transactions`** (`vehicle_registration`, `material`,
> `gross_weight`, `tare_weight`, `weighment_weight`, `invoice_weight`,
> `gross_datetime`, `tare_datetime`, `status`, supervisors, remarks), and
> `weighment_media` carries per-photo gross/tare (`type` l/e) and `source`.
> `weighment_transactions.id` is our snapshot's `transaction_id`. **But the
> production DB is MariaDB, not SQLite** — ask which the supplied file is
> (export / conversion / extract). Treat these names as *expected*, not
> verified, until the file arrives.

**Q2 — How does the agent run today?** *Bring:* which model and prompt (even
rough); what evidence it receives (all photos? slip? software screenshots?);
when it triggers (per weighment, batch, on demand); report latency and cost;
where its output goes.

> **Answered from source (2026-10-08)** — model Grok (`grok-4-0709`, then
> `grok-4.7`), prompt in full, evidence sent (<=16 photos + declared data +
> EXIF), trigger (`invoice_draft`, or manual button), output location
> (`weighment_ai_reports`, shown to the approver). Details:
> `docs/REFERENCE_IMPLEMENTATION.md` section 3. **Still open:** per-report
> cost and latency, and whether approvers actually act on the report.

**Q3 — Deployment target (Gate 3, root `CLAUDE.md`).** Where must the new
components run — weighbridge PC, cloud service, edge board? Online or offline?
Decides model size and whether hosted training (Roboflow) is a dead end.
`docs/DEPLOYMENT_TARGETS.md` questionnaire is unanswered. *Bring:* the target
machine (PC / cloud / Raspberry-Pi class), whether internet is always on, GPU
and RAM, and how long a check may take before it slows the weighbridge.

> **Known environment (2026-10-08, from source — not a decision):** the app
> runs as Docker Compose on one on-prem Proxmox VM with Redis job queues and
> separate worker containers; media on a Kerberos NFS share; the only cloud
> dependencies are the Grok API and the S3 archive; cameras are on the LAN.
> A new check can plausibly run as another worker on that host (CPU/GPU of the
> VM not known). See `docs/DEPLOYMENT_TARGETS.md` "Known facts". Still to
> ask: is the check meant to run per transaction on that VM, or offline on
> the archive; does the VM have a GPU; how long may a check take.

**Q4 — Real fraud examples.** Without positives every fraud model is a
false-positive floor only. *Bring:* any past incidents (material substituted,
truck not fully unloaded, vehicle swapped) with serial/date and how each was
found; and whether staging a few examples at the weighbridge is possible.

> **Owner answer (2026-10-08) — last known fraud:** a tractor carrying about
> **1.5 T** of load was recorded as **8 T**. The weighbridge itself was
> compromised, **staged photos** were used, and the **supervisor was also
> compromised**. Serial/date not yet given; how it was detected not stated.
>
> **Implications (design, not yet decided):**
> - The fraud was *weight-side* (declared/recorded weight vs real load), not a
>   material-type swap. A load-classification model alone would not have caught
>   it; a vehicle-class vs net-weight plausibility rule (tractor cannot carry
>   8 T) would have.
> - Photos and weighbridge readings can be forged by the same insider, so
>   camera-only evidence is not independent. Images that are staged are an
>   adversarial case: check image metadata/timestamps, camera-to-record time
>   consistency, and reused/duplicate scenes across serials.
> - A compromised supervisor means human sign-off is not a trusted control;
>   flags should route to someone outside the weighing chain.
> - One positive is still not a test set — Q4 stays useful for more examples.

**Q5 — What counts as acceptable?** Sets the "good enough to replace" bar in
section 5. *Bring:* tolerable missed-fraud rate per kind of check; how many
false alarms per day a person can review; who reviews a flagged weighment today
and how fast.

**Q6 — Valid material list.** *Bring:* the legitimate wood-species codes and
spellings printed on slips (`KARUVAI`, `PULI`, ...) so that `FULL` / `FUEL`
can be told apart as typo vs red flag.

> **Partly answered (2026-10-08):** `material` is free text in the app; it
> offers defaults `Karuvai` and `Tamarind` plus every distinct value already
> in the DB, and each transaction also carries an ERP item code (group
> `Raw Material [R-]`, e.g. `R-FW-KW`, sub-groups like "Firewood [R-FW]").
> So the authoritative list is `SELECT DISTINCT material` / the ERP item
> master, available once Q1's file arrives. Purchase ledgers also exist for
> **scrap paper**, and the prompt mentions clay (see Q10).

**Q7 — The 74 August serials and the 9 AWS-only serials.** *Bring:* do the
2026-08-06 -> 08-26 photos exist anywhere (other bucket, local disk, still on
the cameras)? Why would the agent have no report for the 9 Mar/Jun/Jul serials?
Does `20260318-001` exist anywhere (it appears to be in neither source)?

> **Explained from source (2026-10-08), pending confirmation.** *74 August
> serials:* the app archives originals to S3 only after **45 days**, and only
> for finished transactions. Our crawl was 2026-09-20; minus 45 days is
> 2026-08-06 — exactly where photos stop. So those photos almost certainly
> still sit on the NFS media share and will appear in S3 as they age (a crawl
> on 2026-10-08 should reach about 08-24). *9 AWS-only serials:* a report is
> only created when a transaction reaches `invoice_draft`, so aborted or
> rejected ones, or ones whose AI job failed all 3 retries, have photos but no
> report; the `transaction_id` gaps are those transactions. The `status` column
> in the supplied DB will settle it. *Ask owner/IT:* can the August photos be
> copied from the NFS share (`/app-fs/Weighbridge-Media`) now, and is it OK to
> re-crawl S3.

**Q8 — Which viewer build to keep?** Opus on `main` (`python main.py`, port
5050) or Sonnet on `sonnet-entry-viewer` (`main_sonnet.py` in
`../weighbridge_Vision_model_sonnet`, port 5051). Needs a choice, no data.

**Q9 — How do gross and tare weights get into the app?** (new 2026-10-08)
Typed by the supervisor, or read automatically from the scale / Essae
indicator / weighbridge software? Is the weigh slip printed from the same
number that is then stored? This decides whether a weight-side fraud (the
1.5 T recorded as 8 T incident) can be seen by comparing photos at all.
*Bring:* a description of the data-entry step, or a screen recording.

> **Owner answer (2026-10-08):** the 1.5 T / 8 T fraud happened under an
> **older manual system**; weights are now **read from the scale**. (The owner
> typed "qn 8"; the content matches Q9, recorded here.)
>
> **Check against the source (same day):** the web app has **no scale
> integration** — `TabGrossWeighment.vue` / `TabTareWeighment.vue` take gross
> and tare as ordinary number inputs and send them to the API
> (`gross_weight`, `tare_weight`); no serial/RS-232/indicator code exists. So
> "read from the scale" most likely means the Essae weighbridge software and
> printed slip read the scale, and the supervisor then **types** the figure
> into this app. That would keep a typing gap between slip and record
> (the app does not compare them; only the AI report cross-checks, from
> photos). *To confirm with the owner:* is the figure typed by the supervisor
> from the software/slip, or pasted/imported from it? If typed, the check
> "slip vs declared weight" (component #5) targets exactly this gap, and the
> old fraud is not ruled out for the current system.

**Q10 — Other materials and other weighbridges.** (new 2026-10-08) The
agent's prompt says goods "like firewood, clay, paper" are weighed, and it
applies special rules "for weighments done on the platform weigh bridge owned
by Sree Murugan Tile Works", implying some weighments use someone else's
bridge. *Bring:* are clay/paper weighments in the S3 archive and SQL (our
data shows only firewood), and which entries are on an outside bridge.

> **Owner answer (2026-10-08):** there is **only one weighbridge**. (Typed as
> "9"; the content matches Q10's second half, recorded here.) So the prompt's
> "weighbridge owned by Sree Murugan Tile Works" wording is generic, there is no
> outside-bridge subset, and every entry shares one scale, one slip format and
> one camera layout. 
>
> **Owner answer (2026-10-08), materials:** for this project it is **just
> firewood** for now. Clay and scrap paper are out of scope; the project
> should not try to classify them. The app does handle them, so this may
> change later (note it as a scope boundary, not a property of the app).

**Q11 — Which camera is which?** (new 2026-10-08) Three capture sources are
configured: Hikvision NVR channels 7 and 8 (1920x1080) and a CP Plus camera
(2688x1520). We have seen `WB INDOOR` (2688x1520) and `WB PLATFORM IN_2`
(1920x1080). *Bring:* names/views of NVR ch 7 and ch 8, and whether a third
camera view exists in the archive.

## 8. Immediate next steps (proposed)

1. Answer Q1-Q3; fill in `docs/DEPLOYMENT_TARGETS.md`.
2. Run `python tools/compute_survey.py` and log it (Gate 2).
3. First labelling pass in the viewer on a seeded sample of entries
   (role, visit, load state, residue, `visit_split_correct`); commit a labels
   snapshot to `docs/labels/`.
4. Finish Gate 1: byte-compare the 4 dual-spelling serials, assess lighting and
   capture conditions by looking at images, decide input-geometry policy.
5. Prototype components #1 and #3 against the labelled sample.
6. Rotate the AWS key.
7. When the DB file arrives: inspect it against `docs/REFERENCE_IMPLEMENTATION.md`
   section 5 (expected tables), join `weighment_media.type`/`source` to the S3
   keys, and re-derive DI-08/DI-12 from real labels.
8. Ask IT whether the 2026-08-06+ photos can be copied from the NFS share, and
   re-crawl S3 (it should now reach about 2026-08-24).
9. Remember S3 retention is 24 months — keep a local copy of whatever the
   models need.
