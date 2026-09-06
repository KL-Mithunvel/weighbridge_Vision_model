"""Gate 1 inventory of the weighbridge camera archive in S3.

Crawls bucket ``smtw-weighbridge-archive`` (settings in ``development/config.yaml``),
writes the full per-object listing to ``data/s3_inventory/s3_objects.jsonl``
(gitignored), downloads a small sample of images to probe real resolution and
format, and writes an aggregated, committed audit record to
``docs/data_inventory/s3_summary.json``. Prints a human-readable report.

This does NOT establish ground-truth labels or pull the whole dataset - it is
the "what data actually exists" step required by CLAUDE.md Gate 1 before any
data-handling code is written. Record the outcome in ``Claude_log.md`` and fold
the findings into ``docs/DATA_AUDIT.md``.

Usage (venv active):
    python development/inventory_s3.py
    python development/inventory_s3.py --config development/config.yaml
    python development/inventory_s3.py --skip-samples      # listing only, no downloads
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aws_s3 import (
    REPO_ROOT,
    S3AccessError,
    credentials_status,
    download_object,
    is_image_key,
    list_objects,
    load_dotenv_file,
    make_client,
    pair_gross_tare,
    summarize_objects,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover - pillow is a pinned dep
    Image = None


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def crawl(client: Any, bucket: str, prefixes: list[str], max_objects: int | None) -> list[dict[str, Any]]:
    """List every object under each configured prefix, de-duplicated by key."""
    seen: dict[str, dict[str, Any]] = {}
    for prefix in prefixes:
        budget = None if max_objects is None else max_objects - len(seen)
        if budget is not None and budget <= 0:
            break
        for obj in list_objects(client, bucket, prefix=prefix, max_objects=budget):
            seen.setdefault(obj["key"], obj)
    return list(seen.values())


def write_jsonl(objects: list[dict[str, Any]], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for obj in objects:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def probe_resolution_sample(
    client: Any,
    bucket: str,
    objects: list[dict[str, Any]],
    image_extensions: list[str],
    sample_size: int,
    seed: int,
    sample_dir: Path,
) -> dict[str, Any]:
    """Download a seeded random image sample and report size / format / mode."""
    if Image is None:
        return {"error": "pillow not installed — cannot probe resolution"}

    image_keys = [o["key"] for o in objects if is_image_key(o["key"], image_extensions)]
    if not image_keys:
        return {"sampled": 0, "note": "no image-extension keys found in the listing"}

    rng = random.Random(seed)
    chosen = rng.sample(image_keys, min(sample_size, len(image_keys)))

    resolutions: dict[str, int] = {}
    formats: dict[str, int] = {}
    modes: dict[str, int] = {}
    failures: list[dict[str, str]] = []

    for key in chosen:
        dest = sample_dir / key.replace("/", "__")
        try:
            download_object(client, bucket, key, dest)
            with Image.open(dest) as im:
                resolutions[f"{im.width}x{im.height}"] = resolutions.get(f"{im.width}x{im.height}", 0) + 1
                formats[im.format or "?"] = formats.get(im.format or "?", 0) + 1
                modes[im.mode] = modes.get(im.mode, 0) + 1
        except (S3AccessError, OSError) as exc:
            failures.append({"key": key, "error": str(exc)})

    return {
        "sampled": len(chosen),
        "succeeded": len(chosen) - len(failures),
        "resolutions": dict(sorted(resolutions.items(), key=lambda kv: -kv[1])),
        "formats": formats,
        "modes": modes,
        "failures": failures,
        "sample_dir": str(sample_dir.relative_to(REPO_ROOT)),
    }


def build_summary(
    config: dict[str, Any],
    objects: list[dict[str, Any]],
    resolution: dict[str, Any] | None,
) -> dict[str, Any]:
    inv = config["inventory"]
    agg = summarize_objects(objects, inv["image_extensions"])
    pairing = pair_gross_tare(objects, inv.get("key_pattern"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bucket": config["s3"]["bucket"],
        "prefixes_crawled": config["s3"]["prefixes"],
        "max_objects_cap": config["s3"]["max_objects"],
        "aggregate": agg,
        "gross_tare_pairing": pairing,
        "resolution_sample": resolution,
        "notes": [
            "Object counts/sizes are exact for the crawled prefixes.",
            "last_modified is the S3 upload time, not necessarily capture time.",
            "Resolution figures are from a random sample only — see sampled/succeeded.",
            "gross_tare_pairing is populated only once inventory.key_pattern is set "
            "in development/config.yaml.",
        ],
    }


def print_report(summary: dict[str, Any]) -> None:
    agg = summary["aggregate"]
    line = "=" * 66
    print(line)
    print(f"S3 INVENTORY  {summary['bucket']}  ({summary['generated_at']})")
    print(line)
    print(f"Objects        : {agg['total_objects']:,}  ({_mb(agg['total_bytes'])})")
    print(f"  images       : {agg['image_objects']:,}  ({_mb(agg['image_bytes'])})")
    print(f"  non-images   : {agg['non_image_objects']:,}")
    if agg["last_modified_range"]:
        lo, hi = agg["last_modified_range"]
        print(f"Upload range   : {lo}  ->  {hi}")
    print("\nBy top-level prefix:")
    for prefix, count in agg["objects_by_top_level_prefix"].items():
        print(f"  {prefix:<28} {count:,}")
    print("\nBy extension:")
    for ext, count in agg["objects_by_extension"].items():
        print(f"  {ext:<28} {count:,}")
    if agg["objects_by_year_month"]:
        print("\nBy month (upload):")
        for ym, count in agg["objects_by_year_month"].items():
            print(f"  {ym:<28} {count:,}")
    res = summary["resolution_sample"]
    if res and res.get("resolutions"):
        print(f"\nResolution sample ({res['succeeded']}/{res['sampled']} probed):")
        for wh, count in res["resolutions"].items():
            print(f"  {wh:<28} {count}")
        print(f"  formats: {res['formats']}   modes: {res['modes']}")
    pairing = summary["gross_tare_pairing"]
    if pairing["pattern_matched"]:
        print("\nGross/tare pairing:")
        print(f"  distinct serials              {pairing['distinct_serials']:,}")
        print(f"  with both gross and tare      {pairing['serials_with_gross_and_tare']:,}")
        print(f"  gross only / tare only        {pairing['serials_gross_only']:,} / {pairing['serials_tare_only']:,}")
    else:
        print("\nGross/tare pairing: skipped (set inventory.key_pattern in config.yaml)")
    print(line)


def _mb(n: int) -> str:
    return f"{n / 1024 ** 2:.1f} MB" if n < 1024**3 else f"{n / 1024 ** 3:.2f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--skip-samples", action="store_true", help="list only; do not download images")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    load_dotenv_file()

    status = credentials_status_from_env()
    if not status["has_keys"]:
        _print_missing_credentials(status)
        return 1

    s3_cfg = config["s3"]
    region = s3_cfg.get("region")
    try:
        client = make_client(region=region)
        print(f"Crawling s3://{s3_cfg['bucket']} (prefixes={s3_cfg['prefixes']}) ...")
        objects = crawl(client, s3_cfg["bucket"], s3_cfg["prefixes"], s3_cfg["max_objects"])
    except S3AccessError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    if not objects:
        print("No objects found for the configured prefixes. Nothing to inventory.")
        return 0

    objects_path = _resolve(config["paths"]["objects_jsonl"])
    write_jsonl(objects, objects_path)
    print(f"Wrote {len(objects):,} object records -> {objects_path.relative_to(REPO_ROOT)}")

    resolution: dict[str, Any] | None = None
    if args.skip_samples:
        print("Skipping resolution sample (--skip-samples).")
    else:
        inv = config["inventory"]
        try:
            resolution = probe_resolution_sample(
                client,
                s3_cfg["bucket"],
                objects,
                inv["image_extensions"],
                inv["resolution_sample_size"],
                inv["sample_seed"],
                _resolve(config["paths"]["sample_dir"]),
            )
        except S3AccessError as exc:
            resolution = {"error": str(exc)}

    summary = build_summary(config, objects, resolution)
    summary_path = _resolve(config["paths"]["summary_json"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote summary -> {summary_path.relative_to(REPO_ROOT)}\n")

    print_report(summary)
    return 0


def credentials_status_from_env() -> dict[str, Any]:
    return credentials_status(os.environ)


def _print_missing_credentials(status: dict[str, Any]) -> None:
    print("AWS credentials are not set - cannot crawl the bucket yet.\n")
    for name, present in status["present"].items():
        print(f"  {name:<24} {'set' if present else 'MISSING'}")
    print(f"  region                   {status['region'] or 'MISSING (default ap-south-1 will be used)'}")
    print(
        "\nFix: copy .env.example to .env at the repo root and fill in the IAM "
        "access key for this laptop. Full steps in docs/AWS_ACCESS.md."
    )


if __name__ == "__main__":
    raise SystemExit(main())
