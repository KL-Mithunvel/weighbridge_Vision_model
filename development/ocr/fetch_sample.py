"""Download a seeded, month-stratified sample of entries for the OCR benchmark.

Per serial: every CCTV frame (small; plate visible on WB PLATFORM) and the last
N handheld photos (the weigh-slip photo is an ordinary upload, usually last).
Objects are GLACIER_IR -> skip files already present (download_object does).
"""
from __future__ import annotations

import collections
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "development"))
import aws_s3  # noqa: E402


def pick_keys(rows: list[dict], cfg: dict) -> list[dict]:
    """Pure: choose objects to fetch from inventory rows."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["key"].split("/")[1]].append(r)
    months = collections.defaultdict(list)
    for serial in sorted(by):
        months[serial[:7] if "-" in serial[:5] else serial[:6]].append(serial)
    rng = random.Random(cfg["seed"])
    chosen: list[dict] = []
    for _, serials in sorted(months.items()):
        for s in rng.sample(serials, min(cfg["serials_per_month"], len(serials))):
            objs = sorted(by[s], key=lambda r: r["key"].split("/")[2])
            hand = [o for o in objs if o["size"] >= cfg["handheld_min_bytes"]]
            cctv = [o for o in objs if o["size"] <= cfg["cctv_max_bytes"]]
            chosen += cctv + hand[-cfg["last_handheld_n"]:]
    return chosen


def main() -> None:
    cfg = yaml.safe_load((Path(__file__).with_name("config.yaml")).read_text())["sample"]
    rows = [json.loads(line) for line in (REPO / "data/s3_inventory/s3_objects.jsonl").open()]
    chosen = pick_keys(rows, cfg)
    print(f"{len(chosen)} objects, {sum(o['size'] for o in chosen)/1e6:.0f} MB")
    aws_s3.load_dotenv_file()
    client = aws_s3.make_client()
    bucket = yaml.safe_load((REPO / "development/config.yaml").read_text())["s3"]["bucket"]
    out = REPO / cfg["out_dir"]

    def get(o):
        parts = o["key"].split("/")
        dest = out / parts[1] / parts[2]
        try:
            aws_s3.download_object(client, bucket, o["key"], dest, o["size"])
            return None
        except Exception as e:  # noqa: BLE001 - report and continue
            return f"{o['key']}: {e}"

    with ThreadPoolExecutor(cfg["workers"]) as ex:
        errs = [e for e in ex.map(get, chosen) if e]
    print("errors:", len(errs), errs[:3])


if __name__ == "__main__":
    main()
