# development/ — dev-only analysis tooling

Not part of any runtime. Scripts here inspect and calibrate against the real
data before pipeline code is written (CLAUDE.md Gate 1 pattern).

## AWS S3 access + Gate 1 image inventory

| File | Role |
|---|---|
| `config.yaml` | All tunables — bucket, region, prefixes, sample size, output paths. Never hardcode these in the scripts. |
| `aws_s3.py` | S3 access. Network I/O (`make_client`, `list_objects`, `download_object`, `head_object`) is kept separate from pure logic (`credentials_status`, `summarize_objects`, `pair_gross_tare`, `extract_key_facets`, …), which `tests/test_aws_s3.py` covers with no network. |
| `inventory_s3.py` | Crawls the bucket, writes the full object listing + an aggregated summary, probes a sample of images for real resolution/format, prints a report. |

### Run

```powershell
# from repo root, venv active
.venv\Scripts\activate

# one-time: create .env with the IAM key — see docs/AWS_ACCESS.md
copy .env.example .env

python development\inventory_s3.py                  # full crawl + resolution sample
python development\inventory_s3.py --skip-samples   # listing only, no downloads
python development\inventory_s3.py --config development\config.yaml
```

### Outputs

- `data/s3_inventory/s3_objects.jsonl` — one JSON record per object (gitignored).
- `data/s3_inventory/samples/` — downloaded resolution-probe images (gitignored).
- `docs/data_inventory/s3_summary.json` — committed aggregate audit record.

### After a run

Fold the findings into `docs/DATA_AUDIT.md` ("What's missing before Gate 1 is
clear") and log the run in `Claude_log.md`. Set `inventory.key_pattern` in
`config.yaml` once the object-key layout is known, so the gross/tare ↔ serial
pairing breakdown populates.

## Entry viewer + labelling GUI

A local Flask app for looking at the archive one weighment at a time: pick a
**capture date** → pick an **entry number** → that entry's S3 photos (split
into visits) appear beside its SQL report(s) from `ai_report_fields`, and you
can label photos and the entry.

| File | Role |
|---|---|
| `entry_viewer/index.py` | Pure logic: serial normalisation (both `YYYY-MM-DD-NNN` and `YYYYMMDD-NNN`), date → entry index from the crawl listing, visit split, role guess, label validation. Covered by `tests/test_entry_viewer.py`. |
| `entry_viewer/sources.py` | Thin I/O: download-once image cache + thumbnails, read-only SQL report load, SQLite label store with append-only history. |
| `entry_viewer/app.py` | Flask routes + CLI. `templates/` and `static/` hold the single page. |
| `config.yaml` → `viewer:` | Host/port, cache dir, thumbnail size, visit-gap minutes, role-guess rules, label vocabulary. |

```powershell
.venv\Scripts\activate
python main.py                                    # from the repo root: starts it and opens the browser
python development\entry_viewer\app.py           # same app, no auto-open; then open http://127.0.0.1:5050
python development\entry_viewer\app.py --export-labels docs\labels\labels_snapshot.json
```

How it behaves:

- **Index source** is `data/s3_inventory/s3_objects.jsonl` (the inventory
  crawl), so browsing dates/entries makes no S3 calls. *Refresh from S3*
  re-lists the bucket (LIST calls only) and rewrites that file.
- **Dates come from the serial folder**, i.e. capture date — not S3
  `last_modified`, which is the backfill upload time.
- **Images download on first view only**, into `data/viewer_cache/`
  (gitignored). Every object is `GLACIER_IR`, so each first view of an entry
  costs a small retrieval fee (~45 MB per entry); later views are free. A ☁
  on a tile means "not cached yet". Only keys present in the index can be
  fetched.
- **Report-only entries** (the 74 August serials with no images) are listed
  with a `NO IMAGES` marker. Serials stored under both folder conventions get
  a duplicate warning. Serials with several SQL reports show one tab each.
- **Provisional inference is labelled as such**: the visit split (gap >
  `visit_gap_minutes`; only a clean 2-visit split is captioned gross/tare)
  and the dashed role badge (resolution once cached, else file size).
- **Labels** — click a thumbnail to open it full size with the photo label
  panel (←/→ moves between photos, Esc closes); entry labels sit in the side
  panel. Clicking a chip saves immediately; clicking it again clears it.
  Notes save on blur. Enter your initials in *Labeller* first — it is stored
  with every change. Labels go to `data/labels/labels.sqlite3` (gitignored);
  the vocabulary is `viewer.labels` in `config.yaml` (add values freely, never
  rename one — existing labels would be orphaned).
- **Text size**: fixed 18px root, smallest text ~14px (no resize control); all sizes are rem so
  one number (`html { font-size }` in `style.css`) rescales the page.
- **Coverage** button: lists serials in both / AWS-only / SQL-only; click one
  to jump to it. Dates and entries that lack photos or a report are flagged ⚠
  in the dropdowns and explained in a banner.
- Bound to `127.0.0.1` only — it uses your AWS keys.

### Tests

```powershell
.venv\Scripts\python.exe -m pytest tests\ -q
```
