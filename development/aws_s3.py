"""AWS S3 access for the weighbridge camera archive (bucket smtw-weighbridge-archive).

Two layers, deliberately separated (CLAUDE.md Development Rule 1 — I/O apart from
pure logic):

* Network I/O — ``load_dotenv_file``, ``make_client``, ``list_objects``,
  ``download_object``, ``head_object``. These touch AWS and cannot be unit
  tested without credentials.
* Pure logic — ``credentials_status``, ``key_extension``, ``is_image_key``,
  ``top_level_prefix``, ``extract_key_facets``, ``summarize_objects``,
  ``pair_gross_tare``. These take plain dicts / strings and are covered by
  ``tests/test_aws_s3.py``.

Credential handling: keys are read from the environment (``AWS_ACCESS_KEY_ID``,
``AWS_SECRET_ACCESS_KEY``, ``AWS_DEFAULT_REGION``), which ``load_dotenv_file``
populates from a gitignored ``.env`` at the repo root. Keys are never passed as
arguments, logged, or written to disk. See docs/AWS_ACCESS.md.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Credentials we expect to find in the environment / .env.
_REQUIRED_CRED_VARS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
_REGION_VARS = ("AWS_DEFAULT_REGION", "AWS_REGION")


class S3AccessError(RuntimeError):
    """Raised for a credential / permission / region failure, with a hint.

    The message maps the underlying botocore error to the troubleshooting table
    in docs/AWS_ACCESS.md so the caller sees what to fix rather than a raw trace.
    """


# --------------------------------------------------------------------------- #
# Network I/O                                                                  #
# --------------------------------------------------------------------------- #
def load_dotenv_file(path: Path | None = None) -> bool:
    """Load ``.env`` (repo root by default) into ``os.environ``.

    boto3 does not read ``.env`` itself. Returns True if a file was found and
    loaded. Existing environment variables are not overridden.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 — optional at import time

    env_path = path or (REPO_ROOT / ".env")
    return load_dotenv(dotenv_path=env_path, override=False)


def make_client(region: str | None = None) -> Any:
    """Build an S3 client, raising :class:`S3AccessError` if credentials are absent.

    ``region`` falls back to ``AWS_DEFAULT_REGION`` / ``AWS_REGION`` in the
    environment. boto3 picks the access keys up from the environment.
    """
    import boto3  # noqa: PLC0415
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

    status = credentials_status(os.environ)
    if not status["has_keys"]:
        raise S3AccessError(
            "AWS credentials not found. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in the environment or in a .env file at the "
            "repo root (copy .env.example). See docs/AWS_ACCESS.md."
        )

    resolved_region = region or _first_env(os.environ, _REGION_VARS)
    try:
        return boto3.client("s3", region_name=resolved_region)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - construction rarely fails
        raise S3AccessError(f"Could not create S3 client: {exc}") from exc


def _wrap_botocore_error(exc: Exception) -> S3AccessError:
    """Translate a botocore exception into an :class:`S3AccessError` with a hint."""
    from botocore.exceptions import (  # noqa: PLC0415
        ClientError,
        EndpointConnectionError,
        NoCredentialsError,
    )

    if isinstance(exc, NoCredentialsError):
        return S3AccessError(
            "No credentials available to boto3. Check AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY. See docs/AWS_ACCESS.md."
        )
    if isinstance(exc, EndpointConnectionError):
        return S3AccessError(
            "Could not reach the S3 endpoint — likely a wrong region_name, or no "
            "network. Confirm the bucket region (S3 -> bucket -> Properties)."
        )
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        hint = {
            "InvalidAccessKeyId": "the access key id is wrong or mistyped.",
            "SignatureDoesNotMatch": "the secret access key is wrong or mistyped.",
            "AccessDenied": "keys work but the IAM policy or a KMS key blocks this "
            "call — contact the bucket admin.",
            "AllAccessDisabled": "the access key has been disabled or deleted.",
            "PermanentRedirect": "wrong region_name for this bucket.",
            "IllegalLocationConstraintException": "wrong region_name for this bucket.",
            "NoSuchBucket": "bucket name is wrong or not visible to this IAM user.",
        }.get(code, "see docs/AWS_ACCESS.md troubleshooting table.")
        return S3AccessError(f"S3 error {code}: {hint}")
    return S3AccessError(str(exc))


def list_objects(
    client: Any,
    bucket: str,
    prefix: str = "",
    max_objects: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one dict per object under ``prefix``.

    Keys: ``key``, ``size`` (bytes), ``last_modified`` (ISO-8601 str),
    ``etag``, ``storage_class``. Pagination is handled internally.
    """
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

    paginator = client.get_paginator("list_objects_v2")
    yielded = 0
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                last_modified = obj.get("LastModified")
                yield {
                    "key": obj["Key"],
                    "size": obj.get("Size", 0),
                    "last_modified": last_modified.isoformat()
                    if isinstance(last_modified, datetime)
                    else last_modified,
                    "etag": (obj.get("ETag") or "").strip('"'),
                    "storage_class": obj.get("StorageClass", "STANDARD"),
                }
                yielded += 1
                if max_objects is not None and yielded >= max_objects:
                    return
    except (BotoCoreError, ClientError) as exc:
        raise _wrap_botocore_error(exc) from exc


def download_object(client: Any, bucket: str, key: str, dest: Path) -> Path:
    """Download one object to ``dest`` (parent dirs created). Returns ``dest``."""
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.download_file(bucket, key, str(dest))
    except (BotoCoreError, ClientError) as exc:
        raise _wrap_botocore_error(exc) from exc
    return dest


def head_object(client: Any, bucket: str, key: str) -> dict[str, Any]:
    """Return object metadata (content type, size, last-modified) without the body."""
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

    try:
        resp = client.head_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise _wrap_botocore_error(exc) from exc
    last_modified = resp.get("LastModified")
    return {
        "key": key,
        "size": resp.get("ContentLength", 0),
        "content_type": resp.get("ContentType"),
        "last_modified": last_modified.isoformat()
        if isinstance(last_modified, datetime)
        else last_modified,
        "metadata": resp.get("Metadata", {}),
    }


# --------------------------------------------------------------------------- #
# Pure logic                                                                   #
# --------------------------------------------------------------------------- #
def _first_env(env: Mapping[str, str], names: Iterable[str]) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


def credentials_status(env: Mapping[str, str]) -> dict[str, Any]:
    """Report which AWS settings are present in ``env`` (no values, no I/O)."""
    present = {name: bool(env.get(name)) for name in _REQUIRED_CRED_VARS}
    region = _first_env(env, _REGION_VARS)
    return {
        "has_keys": all(present.values()),
        "present": present,
        "region": region,
        "has_region": region is not None,
    }


def key_extension(key: str) -> str:
    """Lower-cased file extension of an S3 key, including the dot ('' if none)."""
    return Path(key).suffix.lower()


def is_image_key(key: str, image_extensions: Iterable[str]) -> bool:
    exts = {e.lower() for e in image_extensions}
    return key_extension(key) in exts


def top_level_prefix(key: str) -> str:
    """First path segment of a key, or '<root>' for a key with no '/'."""
    head, sep, _ = key.partition("/")
    return head if sep else "<root>"


def _year_month(last_modified: str | None) -> str | None:
    if not last_modified:
        return None
    try:
        return datetime.fromisoformat(last_modified.replace("Z", "+00:00")).strftime("%Y-%m")
    except ValueError:
        return None


def extract_key_facets(key: str, pattern: str | re.Pattern[str] | None) -> dict[str, str] | None:
    """Apply ``pattern`` to ``key`` and return its named groups, or None.

    Used to pull a transaction/serial id and a gross/tare tag out of the object
    key so photos can be paired to the SQL reports (docs/DATA_AUDIT.md).
    """
    if not pattern:
        return None
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    match = compiled.search(key)
    if not match:
        return None
    return {k: v for k, v in match.groupdict().items() if v is not None}


def summarize_objects(
    objects: Iterable[Mapping[str, Any]],
    image_extensions: Iterable[str],
) -> dict[str, Any]:
    """Aggregate a listing into counts / sizes / histograms (no image content)."""
    exts = {e.lower() for e in image_extensions}
    total_count = 0
    total_bytes = 0
    image_count = 0
    image_bytes = 0
    by_prefix: Counter[str] = Counter()
    bytes_by_prefix: Counter[str] = Counter()
    by_extension: Counter[str] = Counter()
    by_year_month: Counter[str] = Counter()
    by_storage_class: Counter[str] = Counter()
    largest = {"key": None, "size": -1}
    timestamps: list[str] = []

    for obj in objects:
        key = obj["key"]
        size = int(obj.get("size", 0) or 0)
        total_count += 1
        total_bytes += size
        ext = key_extension(key)
        by_extension[ext or "<none>"] += 1
        prefix = top_level_prefix(key)
        by_prefix[prefix] += 1
        bytes_by_prefix[prefix] += size
        by_storage_class[obj.get("storage_class") or "STANDARD"] += 1
        ym = _year_month(obj.get("last_modified"))
        if ym:
            by_year_month[ym] += 1
        if obj.get("last_modified"):
            timestamps.append(obj["last_modified"])
        if ext in exts:
            image_count += 1
            image_bytes += size
        if size > largest["size"]:
            largest = {"key": key, "size": size}

    return {
        "total_objects": total_count,
        "total_bytes": total_bytes,
        "image_objects": image_count,
        "image_bytes": image_bytes,
        "non_image_objects": total_count - image_count,
        "objects_by_top_level_prefix": dict(by_prefix.most_common()),
        "bytes_by_top_level_prefix": dict(bytes_by_prefix.most_common()),
        "objects_by_extension": dict(by_extension.most_common()),
        "objects_by_year_month": dict(sorted(by_year_month.items())),
        "objects_by_storage_class": dict(by_storage_class.most_common()),
        "largest_object": largest if largest["key"] else None,
        "last_modified_range": [min(timestamps), max(timestamps)] if timestamps else None,
    }


def pair_gross_tare(
    objects: Iterable[Mapping[str, Any]],
    pattern: str | re.Pattern[str] | None,
    serial_group: str = "serial",
    state_group: str = "state",
) -> dict[str, Any]:
    """Report how photo keys pair into gross/tare sets per serial.

    Returns zeroed counters and ``matched: False`` when ``pattern`` is None or
    matches nothing — the inventory still runs, it just can't show pairing yet.
    """
    states_by_serial: dict[str, set[str]] = defaultdict(set)
    photos_by_serial: Counter[str] = Counter()
    unmatched = 0
    total = 0

    for obj in objects:
        total += 1
        facets = extract_key_facets(obj["key"], pattern)
        if not facets or serial_group not in facets:
            unmatched += 1
            continue
        serial = facets[serial_group]
        photos_by_serial[serial] += 1
        state = facets.get(state_group)
        if state:
            states_by_serial[serial].add(state.lower())

    both = sum(1 for s in states_by_serial.values() if {"gross", "tare"} <= s)
    gross_only = sum(1 for s in states_by_serial.values() if s == {"gross"})
    tare_only = sum(1 for s in states_by_serial.values() if s == {"tare"})

    return {
        "pattern_matched": bool(photos_by_serial),
        "keys_seen": total,
        "keys_unmatched": unmatched,
        "distinct_serials": len(photos_by_serial),
        "serials_with_gross_and_tare": both,
        "serials_gross_only": gross_only,
        "serials_tare_only": tare_only,
        "photos_per_serial_min": min(photos_by_serial.values()) if photos_by_serial else 0,
        "photos_per_serial_max": max(photos_by_serial.values()) if photos_by_serial else 0,
    }
