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

### Tests

```powershell
.venv\Scripts\python.exe -m pytest tests\ -q
```
