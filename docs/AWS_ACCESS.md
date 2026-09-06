# AWS S3 Access — Weighbridge Camera Archive

How to reach the raw camera images from a local laptop. This is the verbatim
content of the access instructions provided to the owner, plus how it wires into
this repo's tooling. Needed to complete **Gate 1** (data inventory) —
`docs/DATA_AUDIT.md` covers only the SQL side so far.

| | |
|---|---|
| Bucket | `smtw-weighbridge-archive` |
| Region | Look it up (see step 1). Example given: `ap-south-1` |
| Access | The owner's IAM user can **list and read** this bucket. Read-only. |
| Credentials | A personal IAM access key, **for this one laptop**. Not yet created. |
| KMS | Bucket objects may be SSE-KMS encrypted — an `AccessDenied` on `get`/`download` while `list` works points at a KMS key policy, not the access key. |

---

## 1. Create access keys

1. Sign in to the AWS Console with your IAM user.
2. **IAM → Users →** your username.
3. **Security credentials** tab.
4. **Create access key**.
5. Choose **Command Line Interface (CLI)** / *Application running outside AWS*.
6. Create the key and **download the `.csv`**.

You get two values:

- `AWS_ACCESS_KEY_ID` — starts with `AKIA`
- `AWS_SECRET_ACCESS_KEY` — long secret, **shown only once**

Keep the secret private. If it leaks: create a new key, then delete the old one
(**IAM → Security credentials**).

Also note the **bucket region**: S3 → the bucket → **Properties → AWS Region**
(e.g. `ap-south-1`). It is required below — a wrong region gives a redirect
error.

---

## 2. Install `boto3`

Already pinned in `requirements.txt` (`boto3`, `python-dotenv`, `pillow`).
With the project venv active:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

Standalone equivalent: `pip install boto3`.

---

## 3. Pass credentials — this repo uses a gitignored `.env`

`boto3` looks for credentials in this order: constructor args → environment
variables → `~/.aws/credentials` → instance role. This repo standardises on
**environment variables loaded from a `.env` file** (same pattern as
`ROBOFLOW_API_KEY`), because:

- the values survive across terminals (a raw `export` / `$env:` does not);
- `.env` is already in `.gitignore`, so keys cannot be committed;
- `development/aws_s3.py` calls `load_dotenv_file()` before creating a client.

**Setup:**

```powershell
copy .env.example .env
notepad .env
```

Fill in:

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your-secret
AWS_DEFAULT_REGION=ap-south-1        # set to the real bucket region
```

`python-dotenv` loads these into the environment; `boto3.client("s3")` then
finds them with no further wiring. **Do not put keys in any `.py` file.**

### Alternative credential methods (not used here, for reference)

**Option A — environment variables directly.** Last only for that terminal
session.

```powershell
# Windows PowerShell
$env:AWS_ACCESS_KEY_ID="AKIA..."
$env:AWS_SECRET_ACCESS_KEY="your-secret"
$env:AWS_DEFAULT_REGION="ap-south-1"
```

```bash
# macOS / Linux
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="ap-south-1"
```

**Option B — credentials in code.** Local machine only, never committed or
shared:

```python
import boto3

s3 = boto3.client(
    "s3",
    aws_access_key_id="AKIA...",
    aws_secret_access_key="your-secret",
    region_name="ap-south-1",
)
```

This repo does not use Option B — `development/aws_s3.py` never accepts keys as
arguments.

---

## 4. Example: list and download (raw boto3)

```python
import boto3

s3 = boto3.client("s3")            # reads env / .env-loaded vars
bucket = "smtw-weighbridge-archive"

# list first 10 objects
resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=10)
for obj in resp.get("Contents", []):
    print(obj["Key"], obj["Size"])

# list one prefix only
resp = s3.list_objects_v2(Bucket=bucket, Prefix="some/folder/")

# download one file
s3.download_file(bucket, "folder/file.jpg", "file.jpg")

# read an object into memory
body = s3.get_object(Bucket=bucket, Key="folder/file.jpg")["Body"].read()
```

`list_objects_v2` returns at most 1000 keys per call — use a paginator for the
whole bucket (this repo's `aws_s3.list_objects` does that).

---

## 5. Quick check

```powershell
python development\inventory_s3.py --skip-samples
```

or, if the AWS CLI is installed:

```bash
aws s3 ls s3://smtw-weighbridge-archive
```

| Result | Meaning |
|---|---|
| Listing works | Keys + region + permissions are fine |
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | Wrong or mistyped key |
| `AccessDenied` | Keys work; IAM policy or KMS key issue — contact the bucket admin |
| `PermanentRedirect` / `IllegalLocationConstraintException` | Wrong `region_name` |
| `EndpointConnectionError` | Wrong region or no network |

`development/aws_s3.py` maps each of these to a one-line hint via `S3AccessError`.

---

## 6. Security rules (from the access instructions)

- Do **not** email or chat the secret access key.
- Do **not** put keys in GitHub, shared notebooks, or screenshots.
- One key pair, for this laptop only.
- If a key leaks: create a new one, delete the old one.
- **When the project ends, delete the access key** in IAM → Security credentials.

`.env` is gitignored. Before any commit, confirm `git status` does not show
`.env` and that no key string appears in a staged diff.

---

## 7. How this maps to the repo

| Path | Role |
|---|---|
| `.env` (gitignored) | Holds `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`. |
| `.env.example` | Template with blank placeholders. |
| `development/config.yaml` | Bucket, region, prefixes to crawl, sample size, output paths — no hardcoding. |
| `development/aws_s3.py` | Thin boto3 wrapper (`make_client`, `list_objects`, `download_object`, `head_object`) + pure helpers (`summarize_objects`, `pair_gross_tare`, …) covered by `tests/test_aws_s3.py`. |
| `development/inventory_s3.py` | Gate 1 crawler → writes `data/s3_inventory/s3_objects.jsonl` (gitignored) + `docs/data_inventory/s3_summary.json` (committed) + a console report. |
| `data/s3_inventory/` | Raw listing + downloaded image samples. Gitignored (`data/`). |
| `docs/data_inventory/s3_summary.json` | Committed aggregate audit record (counts, histograms — no image content). |

Run order once `.env` is filled:

```powershell
.venv\Scripts\activate
python development\inventory_s3.py            # full crawl + resolution sample
```

Then fold the findings into `docs/DATA_AUDIT.md` and log the run in
`Claude_log.md` (Gate 1 requirement).

---

## 8. Alternative path — mirror the bucket into Roboflow

Instead of (or in addition to) pulling images to the laptop, the Roboflow
`cloud-storage` skill can mirror `smtw-weighbridge-archive` straight into a
Roboflow workspace: create a storage credential from the same IAM key, define a
datasource with glob rules, validate, and run a mirror job. Relevant if
labelling/versioning happens in Roboflow.

**Caveat (Gate 3):** Roboflow-hosted training exports no weights for some
architectures. If the weighbridge models must run locally/offline/on-edge, keep
the production model on an exportable path — see `docs/DEPLOYMENT_TARGETS.md` and
`docs/ROBOFLOW_INTEGRATION.md`. Using Roboflow only for dataset management is
fine.
