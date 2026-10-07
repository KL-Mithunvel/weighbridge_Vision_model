# Reference Implementation — the Production WeighBridge App

Written 2026-10-08 from a read-only read of the source repo. **Nothing was
changed in that repo**; this file records what we need from it so we do not have
to keep going back.

| | |
|---|---|
| **Source repo** | <https://github.com/smtwkla/WeighBridge> (private — a plain web fetch returns 404; `git clone` works with the owner's stored credentials) |
| **Read at** | `main` = `36022b2` "release v0.5.6" (`VERSION` = 0.5.6). 144 commits, first 2026-03-03. Branches `claude/add-tonnes-chart-K9JLq` and `cursor/admin-purchase-analytics-00f9` exist (not read). |
| **Its own docs** | `docs/Software-Specification.md` (v2.1, 2026-07-10), `docs/Backend-Readme.md`, `docs/Frontend-Readme.md`, `docs/Backup.md`; deploy runbooks are in a different repo, `smtw_erp_devops` (`docs/lob-apps/weighbridge.MD`, not seen) |
| **Key files for us** | `backend/ai_prompt_template.py` (the agent's prompt), `backend/ai_reports.py` + `backend/worker.py` (how the agent is called), `backend/media.py`, `backend/storage.py`, `backend/nvr_client.py`, `backend/company_settings.py` (CCTV sources), `backend/local_db.py` (schema migrations) |

> **How to refresh.** Re-clone or `git fetch` and diff against `36022b2`. The
> app is still moving (v0.5.6 shipped 2026-09-23). Anything below that is
> marked *[code]* was read from source; *[doc]* was only stated in their docs;
> *[inferred]* is our deduction and must be checked against the real database.

**Why this matters to us.** This app *is* the source system. Our 769-row SQL
snapshot, the S3 archive and the weigh-slip photos all come out of it. Reading
it answers most of what we had to infer (`docs/ENTRY_ANATOMY.md`,
`docs/DATA_ISSUES.md`) and several of the owner questions
(`docs/PROJECT_SCOPE.md` section 7).

---

## 1. What the app is *[doc]*

A mobile-first web app (Vue 3 frontend, Flask backend) that replaced a WhatsApp
group for weighment evidence at **Sree Murugan Tile Works**. Firewood (and per
its prompt also clay and paper) is bought by weight from suppliers. The
supervisor does the gross and tare weighments, attaches photos, a purchase
incharge turns it into a draft ERPNext purchase invoice, an AI report is
generated, and the MD approves; approval submits the invoice and syncs a
purchase voucher to Tally. Cash and bank payments to suppliers are also tracked
there (out of scope for us).

Roles (Keycloak SSO over Active Directory): `supervisor`, `purchase_incharge`,
`authorized_approver`, `cashier`, `it_incharge`.

**Status lifecycle** (`weighment_transactions.status`):

```
draft -> evidence_complete -> invoice_draft -> approved -> submitted
 (supervisor)  (supervisor)     (incharge)     (approver)  (ERPNext confirmed)
                                              \-> rejected (terminal)
draft -> aborted (terminal, reason required)
```

The AI report is auto-queued when status becomes **`invoice_draft`** — i.e.
only *after* the supervisor and incharge have finished. It is advisory; a human
approver still decides.

## 2. Deployment environment *[doc]* (feeds Gate 3)

Production = Docker Compose on one Proxmox VM ("Customer-7", `10.24.0.112`),
all on the company LAN:

| Piece | Detail |
|---|---|
| Containers | `wb-backend` (Flask/Gunicorn, Python 3.14), `wb-frontend` (nginx), `wb-ai-worker`, `wb-tally-worker`, `wb-mariadb` (MariaDB 11.8), `wb-redis`, `wb-adminer` |
| Media | Kerberos **NFS** share from the "App-FS" VM (`10.24.0.117`), ZFS dataset `Weighbridge-Media`, mounted at `/data/media` |
| Archive | AWS S3 `smtw-weighbridge-archive`, `ap-south-1`, Glacier Instant Retrieval — **the same bucket we read** |
| Cameras | Hikvision NVR + a CP Plus camera on `192.168.16.x`; the backend container must reach that LAN |
| ERP / accounting | ERPNext "OneERP" (`oneerp.mspv.app`), Tally Prime via a Go proxy on a Windows VM |
| Identity | Keycloak `sso.mspv.app`, realm `Office.smtw.in` |
| AI | xAI Grok via the OpenAI SDK — an **external cloud API**, internet required |

Implications for us: the company already has an on-prem Linux/Docker host,
a Redis job queue and a worker pattern (`worker.py`: BRPOP loop, retries,
heartbeat). A new check could be another worker container reading the same
queue/DB. The only GPU-less, cloud-reliant piece today is the Grok call. This
does not by itself answer Q3 (see `docs/DEPLOYMENT_TARGETS.md`, "Known
facts").

## 3. The existing AI agent, exactly *[code]*

This replaces the "model, prompt, cost unknown" gap in
`docs/PROJECT_SCOPE.md` section 2.

| | |
|---|---|
| Provider / model | xAI **Grok**, called through the OpenAI Python SDK (`base_url` = `GROK_API_URL`). `grok-2-vision-latest` on 2026-03-03/04; **`grok-4-0709` from 2026-03-05 to 2026-09-23**; `grok-4.7` from 2026-09-23 (`e849258`). |
| Temperature | 0.2. `response_format = json_object` added 2026-06-10. |
| Trigger | Auto-enqueued on `invoice_draft`; also a manual "full report" button (`POST .../ai/full-report`). Redis list `ai:jobs`; up to **3 attempts, 10 min apart**; startup recovery re-enqueues lost jobs. |
| Photos sent | **Max 16** (`AI_MAX_PHOTOS`; it was 8 for the first hours of 2026-03-05). Split half gross / half tare; if one side has fewer than 8 the surplus goes to the other. **Selection is "first N in DB order", not random or ranked** — a 17th photo is simply never seen. Full-resolution, base64-embedded. **Videos are not sent.** |
| Text sent | Declared weighment data (serial, supplier, vehicle, material, gross/tare/net/invoice weights and datetimes, supervisors, remarks), ERP invoice data and print text, per-photo label ("Gross"/"Tare", "CCTV capture"/"manual upload") and **pre-extracted EXIF**. |
| Output (JSON) | `plate_ocr, plate_match, load_assessment, weight_plausible, tampering_signs[], consistency_score (0-1), summary, flags[], feedback (string or null)` — these are exactly the columns of our `ai_report_fields`. |
| Stored | `weighment_ai_reports` (`report_json`, `summary_text`, `flags_json`) plus a JSON file under `ai-reports/`. |

**What the prompt asks it to check** (this is the agent's *actual* spec — the
list our components would be measured against):

- timeline, and plausibility of the weight for the vehicle type
- the declared material is consistent with the photos
- both phases: plate, vehicle fully on the platform, vehicle type, scale
  reading, a screenshot of the weighment software (may share a photo with the
  scale)
- gross: payload visible. Tare: platform expected empty; "returned/rejected
  material is sometimes included in empty weight — bring to notice"
- weigh slip: one per weighment, either phase, 3 columns (`Sl, Date, Time,
  Vehicle, Gross, Tare, Net, Material`), footer has operator signature and
  print datetime; dot-matrix on plain paper
- own-weighbridge tolerance: **10 kg allowed for wind fluctuation, provided it
  is <= 1% of the reading**
- EXIF: CCTV frames never carry EXIF (do not flag); for manual uploads compare
  EXIF time to declared gross/tare time, note GPS, and flag missing EXIF as a
  possible edit or forward

**Version drift in the 769 reports** *(verified against the local snapshot,
DI-35)*. The prompt and model changed during the period the reports cover
(2026-03-06 to 2026-08-26): prompt revisions 03-05, 03-13 (feedback field),
03-14 and 03-18 (EXIF), 06-10 (JSON-fence fix), 08-08 (feedback must be null
when nothing to report). So the reports are not one homogeneous "agent".

## 4. How an entry is produced *[code]* — and what that explains

This is the most useful part for the data work.

**Serial.** `YYYY-MM-DD-NNN`, date in **IST**, next number for that day
(`_generate_serial`). Plate regex enforced at entry:
`^[A-Z]{2}\d{2}[A-Z]{0,2}\d{4}$` (no spaces; the slip's `TN 76 P 8336`
normalises to `TN76P8336`).

**Media row.** Each photo is a `weighment_media` row with:

- `type`: **`l` = gross/loaded, `e` = tare/empty** — chosen by the supervisor in
  the Gross or Tare tab, so *gross/tare is recorded in the DB* (it is only
  absent from the S3 key).
- `source`: `upload` (phone) or `capture` (CCTV). Their spec says `nvr`; the
  code writes **`capture`** and the AI module tests for `capture` — doc drift,
  check the real data.
- `file_path` = `weighments-YYYYMM/<serial>/<YYYYMMDD_HHMMSS>_<8-hex>.<ext>`
  — the S3 key we see.

**File names are server-receive time, IST** (`datetime.now(IST)` at upload).
They are not capture time. For a phone photo the filename time is when the
upload arrived; for CCTV it is the moment the button was pressed.

**CCTV capture** (`POST .../media/nvr-snapshot`): one click captures every
configured source at once and stores each as a photo of the chosen phase. Three
sources are configured *(as of v0.5.6)*:

| Source | Device | Native size | Matches our role |
|---|---|---|---|
| NVR ch **7** | Hikvision `192.168.16.230` | 1920x1080 | `WB PLATFORM IN_2` *(or ch 8 — which is which is not stated)* |
| NVR ch **8** | Hikvision `192.168.16.230` | 1920x1080 | the other platform view |
| Camera | CP Plus `192.168.16.234` | 2688x1520 | `WB INDOOR` (matches the 2688x1520 we measured) |

`cctv_enabled` is an app setting, **default off**; one capture per phase.
That explains the modal "6 CCTV + 9 phone" per entry: 3 sources x 2 phases = 6
*[inferred, strongly]*, and why 84 entries have no CCTV (captured before it was
switched on — the feature landed 2026-03-13, high-res 2026-03-18).

**Upload rules.** Photo `jpg/jpeg/png/webp/heic`; video `mp4/webm/mov`; 50 MB
hard cap per file (an admin setting `max_upload_size_mb` defaults to 5); a
thumbnail is made on upload (JPEG q80). Uploads are allowed only while the
transaction is `draft` or `evidence_complete`; media can be deleted only
before its phase is marked complete.

**Archive and retention** *(explains the 74 "SQL-only" serials)*:

- Nightly `media-lifecycle` job: originals of **terminal-status** transactions
  older than **45 days** are uploaded to S3 and deleted from NFS. Media older
  than **24 months** is deleted *everywhere*, but the DB row stays.
- The S3 archive feature was introduced 2026-07-04; our S3 `LastModified`
  (2026-07 -> 09) is the backfill time (DI-26).
- Our inventory was 2026-09-20. 2026-09-20 minus 45 days = **2026-08-06** —
  exactly the first date with no photos. So the 74 serials (08-06 -> 08-26)
  almost certainly **still sit on the NFS share, not yet archived** — they are
  not lost. *[inferred; confirm with the owner/IT]*
- A fresh crawl today (2026-10-08) should reach about 2026-08-24.
- **Retention risk:** the earliest photos (2026-03) will be deleted from S3
  around 2028-03. Our local copy is the only durable one — keep what we need.

**AI report rows.** Written only if the job succeeds. A transaction that was
aborted, rejected before `invoice_draft`, or whose job exhausted its 3 retries
has **no report row** though it may have photos — a likely cause of the 9
"AWS-only" serials and the `transaction_id` gaps (DI-04/06) *[inferred]*. The
manual button and retries mean several reports per transaction are normal by
design (DI-03).

## 5. Data model — the parts we need *[doc + code]*

MariaDB 11.8, `utf8mb4`, all `DATETIME` stored as **IST (naive)**; schema
version 24. Full DDL is in their `Software-Specification.md` section 5.

### `weighment_transactions` — this is the "declared values" table (Q1)

| Column | Notes |
|---|---|
| `id`, `serial` (unique) | `id` = our SQL snapshot's `transaction_id` |
| `supplier_name` / `erp_supplier`, `erp_supplier_name` | free text and ERP id (`SUP-2025-00001`) |
| `vehicle_registration` | validated plate |
| `material`; `erp_item_code`, `erp_item_name` | free text (defaults offered: `Karuvai`, `Tamarind`, plus distinct DB values) and ERP item (e.g. `R-FW-KW`) |
| `gross_weight`, `tare_weight` | kg, `DECIMAL(10,2)` |
| `weighment_weight` | gross - tare (auto) |
| `invoice_weight` | defaults to `weighment_weight`; **editable by the incharge**, remarks mandatory if different |
| `gross_datetime`, `tare_datetime` | when each phase was recorded |
| `gross_weigh_supervisor`, `tare_weigh_supervisor`, `gross_checked_by`, `tare_checked_by` | who |
| `gross_complete`, `tare_complete`, `status` | workflow |
| `weighment_remarks`, `invoice_remarks`, `rejection_reason`, `abort_reason`, `approved_by`, `rejected_by`, `aborted_by`, `invoice_submitted_by` | human trail |
| `erp_invoice_docname`, `tally_*`, `amount_paid` | accounting (not needed) |

> Two weights matter: `weighment_weight` (what the scale gave) versus
> `invoice_weight` (what is paid on). A fraud can sit in the *gap*, or in the
> typed-in `gross_weight`/`tare_weight` themselves. The frontend has **no scale
> integration** — the weights are plain number inputs the supervisor fills in,
> so the figure is probably keyed in from the weighbridge software/slip
> *[inferred from the form code]*. The owner says the 1.5 T / 8 T fraud was
> under an older manual system and weights are now read from the scale
> (2026-10-08); whether the app's entry is typed or imported is still to be
> confirmed (Q9).

### `weighment_media`
`transaction_id`, `file_path`, `file_type` (`photo`/`video`), `type` (`l`/`e`),
`source`, `file_size`/`archived_at`/`archive_key` (archive), `purged_at`,
`uploaded_at`.

### `weighment_ai_reports`
`transaction_id`, `report_type` (`quick`/`full`), `report_json`,
`summary_text`, `flags_json`, `created_at`. Our `wb_ai_reports.sqlite3` is a
flattened export of this table (with a derived `parse_ok` column).

### Not in our snapshot
Everything in `weighment_transactions` except `id` and `serial`, and all of
`weighment_media`. That is the declared plate/weights/material (Q1), the
gross/tare labelling, the photo source, and the status of each transaction.

## 6. What the real database is (and a contradiction to resolve)

The owner said on 2026-10-08 the database is a **SQLite3 file**. The app's own
database is **MariaDB**, not SQLite, and has no SQLite code path (`pymysql`
only; dev compose also uses MariaDB). So the file the owner will supply is
either (a) an export or a converted copy, or (b) our existing derived
`wb_ai_reports.sqlite3`-style extract of a larger set of tables. Do **not**
assume table or column names; use section 5 as the *expected* shape and verify
on receipt (Gate 1). Ask the owner which it is.

## 7. Discrepancies and cautions in the reference repo itself

| # | Observation | Why it matters |
|---|---|---|
| R1 | Spec says `weighment_media.source = 'nvr'`; code writes `'capture'`. | Filter on the real data, not the doc. |
| R2 | `AI_MAX_PHOTOS` = 16 and selection is first-N. | Entries with >16 photos: the agent never judged the rest. Our components could cover them. |
| R3 | Photo timestamp in the key is upload time (IST). | DI-13 is partly answered: filename clock is server IST, so DI-11's hours are local time. Still not equal to capture time for phone photos. |
| R4 | The prompt says an own-platform weighbridge rule applies, which suggested other weighbridges. **Owner (2026-10-08): there is only one weighbridge.** | No outside-bridge subset; the wording is generic. |
| R5 | Prompt and ERP config show **clay and scrap paper** are also bought. | "Firewood only" (DI-17/18) may just reflect what this archive holds. **Owner (2026-10-08): firewood only for this project for now** — clay/paper are out of scope. |
| R6 | Plain-text secrets are templated into `secrets_app.py`; an example file is in the repo. | We have not seen any real secret and must not copy any. CCTV IPs above are LAN addresses only. |
| R7 | The repo has its own `.claude/` guidance and a `smtw-review` skill. | Useful house conventions if we later add a worker there; we are not editing it. |

## 8. Questions this reading raises (for the owner)

Folded into `docs/PROJECT_SCOPE.md` section 7 as Q9-Q11, and into Q1/Q2/Q3/Q6/Q7.

- Q9 (partly answered): the old fraud was a manual system; weights are now read
  from the scale. The app itself has typed inputs — confirm whether the figure
  is keyed in from the weighbridge software or imported.
- Q10 (answered): only one weighbridge; this project is firewood only for now.
- Q11: which camera is `WB INDOOR` / `WB PLATFORM IN_2` / the third source
  (NVR ch 7, ch 8, the CP Plus at `.234`)?

## 9. What was not read

`frontend/` beyond file names, `erpnext.py`, `tally_*`, `payments*`, the two
extra branches, the PR, and the devops repo. None are needed for the vision
work; read them only if a question needs them.
