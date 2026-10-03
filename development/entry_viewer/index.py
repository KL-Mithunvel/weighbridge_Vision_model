"""Pure logic for the entry viewer — no I/O, covered by tests/test_entry_viewer.py.

Turns the flat S3 listing (``data/s3_inventory/s3_objects.jsonl``) plus the SQL
report rows into a date -> entry -> photos index, splits each entry's photos
into visits, guesses each photo's role, and validates labels.

Everything inferred here (visit split, role guess) is PROVISIONAL — see
docs/DATA_AUDIT.md and docs/ENTRY_ANATOMY.md. The GUI labels it as such.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

# S3 folders and SQL rows use both 'YYYY-MM-DD-NNN' and 'YYYYMMDD-NNN'.
_SERIAL_RE = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})-(\d{3})$")
# Filenames are 'YYYYMMDD_HHMMSS_<hash>.jpg' — capture time, unlike S3
# last_modified which is the 2026-07..09 backfill upload time.
_CAPTURE_RE = re.compile(r"(\d{8})_(\d{6})_")

NOTES_MAX_CHARS = 2000


def normalize_serial(raw: str | None) -> str | None:
    """Canonical serial 'YYYYMMDD-NNN' (the SQL form), or None if unparseable."""
    if not raw:
        return None
    match = _SERIAL_RE.match(raw.strip())
    if not match:
        return None
    y, m, d, n = match.groups()
    return f"{y}{m}{d}-{n}"


def serial_date(serial: str) -> str:
    """'20260319-001' -> '2026-03-19'."""
    return f"{serial[0:4]}-{serial[4:6]}-{serial[6:8]}"


def capture_time(key: str) -> datetime | None:
    """Capture timestamp parsed from the object filename, or None."""
    match = _CAPTURE_RE.search(PurePosixPath(key).name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _new_entry(serial: str) -> dict[str, Any]:
    return {"serial": serial, "date": serial_date(serial), "folders": set(), "photos": []}


def build_index(
    objects: Iterable[Mapping[str, Any]],
    key_pattern: str,
    image_extensions: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Group listed objects into entries keyed by normalised serial.

    Each entry: ``serial``, ``date``, ``folders`` (set of raw S3 folder serials —
    more than one means the dual-convention duplicate case), ``photos`` (sorted
    by capture time, then key). Keys not matching ``key_pattern`` are skipped.
    """
    pattern = re.compile(key_pattern)
    exts = {e.lower() for e in image_extensions}
    index: dict[str, dict[str, Any]] = {}
    for obj in objects:
        key = obj["key"]
        if PurePosixPath(key).suffix.lower() not in exts:
            continue
        match = pattern.search(key)
        raw = match.group("serial") if match else None
        serial = normalize_serial(raw)
        if serial is None:
            continue
        entry = index.setdefault(serial, _new_entry(serial))
        entry["folders"].add(raw)
        taken = capture_time(key)
        entry["photos"].append(
            {
                "key": key,
                "size": int(obj.get("size") or 0),
                "etag": obj.get("etag") or "",
                "captured_at": taken.isoformat() if taken else None,
            }
        )
    for entry in index.values():
        entry["photos"].sort(key=lambda p: (p["captured_at"] or "9999", p["key"]))
    return index


def group_reports(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """SQL report rows keyed by normalised serial, newest ``created_at`` first.

    Some serials carry several reports (re-runs), so this is a list, not a row.
    Rows whose serial cannot be normalised are kept under their raw serial.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        raw = row.get("serial") or ""
        grouped[normalize_serial(raw) or raw].append(dict(row))
    for reports in grouped.values():
        reports.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return dict(grouped)


def add_report_only_entries(
    index: dict[str, dict[str, Any]],
    report_serials: Iterable[str],
) -> None:
    """Add photo-less entries for serials that have a report but no images.

    E.g. the 74 August serials whose images are missing from the archive — they
    should still be browsable, with an explicit "no images" state.
    """
    for serial in report_serials:
        if normalize_serial(serial) == serial and serial not in index:
            index[serial] = _new_entry(serial)


def list_dates(
    index: Mapping[str, Mapping[str, Any]],
    reports: Mapping[str, list[Any]],
) -> list[dict[str, Any]]:
    """One row per capture date: entry, photo and report counts."""
    by_date: dict[str, dict[str, int]] = {}
    for serial, entry in index.items():
        row = by_date.setdefault(entry["date"], {"entries": 0, "photos": 0, "with_report": 0})
        row["entries"] += 1
        row["photos"] += len(entry["photos"])
        row["with_report"] += 1 if reports.get(serial) else 0
    return [{"date": d, **counts} for d, counts in sorted(by_date.items())]


def list_entries(
    index: Mapping[str, Mapping[str, Any]],
    reports: Mapping[str, list[Any]],
    date: str,
) -> list[dict[str, Any]]:
    """Entries captured on ``date`` ('YYYY-MM-DD'), in serial order."""
    rows = []
    for serial in sorted(s for s, e in index.items() if e["date"] == date):
        entry = index[serial]
        rows.append(
            {
                "serial": serial,
                "number": serial.rsplit("-", 1)[1],
                "photos": len(entry["photos"]),
                "reports": len(reports.get(serial, [])),
                "duplicate_folders": len(entry["folders"]) > 1,
            }
        )
    return rows


def split_visits(
    photos: list[Mapping[str, Any]],
    gap_minutes: float,
) -> list[list[Mapping[str, Any]]]:
    """Split time-sorted photos into visits wherever the gap exceeds ``gap_minutes``.

    Photos without a parseable capture time go into a trailing group of their own.
    """
    timed = [p for p in photos if p.get("captured_at")]
    untimed = [p for p in photos if not p.get("captured_at")]
    visits: list[list[Mapping[str, Any]]] = []
    previous: datetime | None = None
    for photo in timed:
        taken = datetime.fromisoformat(photo["captured_at"])
        if previous is None or (taken - previous).total_seconds() > gap_minutes * 60:
            visits.append([])
        visits[-1].append(photo)
        previous = taken
    if untimed:
        visits.append(untimed)
    return visits


def visit_caption(position: int, total: int) -> str:
    """Human caption for visit ``position`` (0-based) of ``total``.

    Only the clean 2-visit case gets a gross/tare guess — order-inferred and
    PROVISIONAL (docs/DATA_AUDIT.md).
    """
    if total == 2:
        return ("Visit 1 — provisional gross", "Visit 2 — provisional tare")[position]
    return f"Visit {position + 1} of {total}"


def guess_role(size: int, resolution: str | None, rules: Mapping[str, Any]) -> str:
    """PROVISIONAL image-role guess from resolution (if known) else byte size."""
    by_res = rules.get("by_resolution") or {}
    if resolution and resolution in by_res:
        return by_res[resolution]
    if size < int(rules["cctv_max_bytes"]):
        return rules["small_unknown"]
    return rules["large_unknown"]


def safe_cache_relpath(key: str) -> PurePosixPath:
    """Relative cache path for an S3 key; rejects traversal / absolute keys."""
    # Check raw segments: PurePosixPath would silently collapse '//' and '/./'.
    # Backslashes and ':' are rejected too — the cache lives on a Windows path.
    segments = key.split("/")
    if any(s in ("", ".", "..") or "\\" in s or ":" in s for s in segments):
        raise ValueError(f"unsafe object key: {key!r}")
    return PurePosixPath(key)


def validate_label(
    payload: Mapping[str, Any],
    vocabulary: Mapping[str, Iterable[str]],
) -> dict[str, Any]:
    """Return the cleaned label fields from ``payload``.

    Each vocabulary field must be one of its allowed values, or empty/None to
    clear it. ``notes`` is free text (trimmed, length-capped). Unknown fields
    raise — a typo in the client must not silently drop a label.
    """
    allowed_fields = set(vocabulary) | {"notes"}
    unknown = set(payload) - allowed_fields
    if unknown:
        raise ValueError(f"unknown label field(s): {sorted(unknown)}")
    cleaned: dict[str, Any] = {}
    for field, choices in vocabulary.items():
        value = payload.get(field)
        if value in (None, ""):
            cleaned[field] = None
        elif value in set(choices):
            cleaned[field] = value
        else:
            raise ValueError(f"{field}={value!r} not in {list(choices)}")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be a string")
    notes = (notes or "").strip()
    if len(notes) > NOTES_MAX_CHARS:
        raise ValueError(f"notes longer than {NOTES_MAX_CHARS} characters")
    cleaned["notes"] = notes or None
    return cleaned


def is_empty_label(cleaned: Mapping[str, Any]) -> bool:
    """True when every field is cleared — the caller deletes instead of storing."""
    return all(v is None for v in cleaned.values())
