"""I/O for the entry viewer — S3 image cache, SQL reports, label store.

Thin wrappers only (CLAUDE.md Development Rule 1); decisions live in
``index.py``. Network calls go through ``aws_s3`` so errors map to the
docs/AWS_ACCESS.md troubleshooting table.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from aws_s3 import download_object
from entry_viewer.index import safe_cache_relpath


def load_objects_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read the crawl listing written by inventory_s3.py (one JSON per line)."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python development/inventory_s3.py --skip-samples` "
            "or use the viewer's 'Refresh from S3' button."
        )
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class ImageCache:
    """Download-once cache of originals + thumbnails under ``cache_dir``.

    Objects are GLACIER_IR (retrieval fee per GET), so an original is fetched
    from S3 at most once; ``download_object`` skips when the cached size
    matches the listing. Image resolution is recorded in a sidecar JSON so the
    role guess can use it without re-opening the file.
    """

    def __init__(
        self,
        client_factory: Callable[[], Any],
        bucket: str,
        cache_dir: Path,
        thumb_max_px: int,
        thumb_quality: int,
    ) -> None:
        self._client_factory = client_factory
        self._client: Any = None
        self._bucket = bucket
        self._root = cache_dir
        self._thumb_px = thumb_max_px
        self._thumb_quality = thumb_quality
        self._guard = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _client_or_create(self) -> Any:
        with self._guard:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    def _paths(self, key: str) -> tuple[Path, Path, Path]:
        rel = Path(*safe_cache_relpath(key).parts)
        return (
            self._root / "objects" / rel,
            self._root / "thumbs" / rel,
            self._root / "meta" / rel.with_name(rel.name + ".json"),
        )

    def is_cached(self, key: str, size: int) -> bool:
        original, _, _ = self._paths(key)
        return original.exists() and original.stat().st_size == size

    def resolution(self, key: str) -> str | None:
        """'WxH' if the original has been cached and probed, else None."""
        _, _, meta = self._paths(key)
        if not meta.exists():
            return None
        data = json.loads(meta.read_text(encoding="utf-8"))
        return f"{data['width']}x{data['height']}"

    def original(self, key: str, size: int) -> Path:
        """Local path of the original, downloading it if needed."""
        original, _, meta = self._paths(key)
        with self._lock_for(key):
            download_object(self._client_or_create(), self._bucket, key, original, expected_size=size)
            if not meta.exists():
                with Image.open(original) as im:
                    meta.parent.mkdir(parents=True, exist_ok=True)
                    meta.write_text(
                        json.dumps({"width": im.width, "height": im.height, "size": size}),
                        encoding="utf-8",
                    )
        return original

    def thumbnail(self, key: str, size: int) -> Path:
        """Local path of the thumbnail, building it (and the original) if needed."""
        _, thumb, _ = self._paths(key)
        if thumb.exists():
            return thumb
        original = self.original(key, size)
        with self._lock_for(key):
            if not thumb.exists():
                thumb.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(original) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((self._thumb_px, self._thumb_px))
                    tmp = thumb.with_name(thumb.name + ".part")
                    im.save(tmp, format="JPEG", quality=self._thumb_quality)
                    tmp.replace(thumb)
        return thumb


def load_reports(db_path: Path, table: str) -> list[dict[str, Any]]:
    """All rows of the SQL report table, opened read-only."""
    if not db_path.exists():
        raise FileNotFoundError(f"reports database not found: {db_path}")
    if not table.isidentifier():
        raise ValueError(f"invalid table name: {table!r}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]  # noqa: S608 — validated identifier


class LabelStore:
    """Human labels in a local SQLite file (gitignored).

    ``labels`` holds the current value per (kind, target); ``label_events`` is
    an append-only history so label provenance (who changed what, when) is
    never lost. Fields are stored as JSON so the vocabulary can grow in
    config.yaml without a schema migration.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS labels (
        kind TEXT NOT NULL CHECK (kind IN ('photo', 'entry')),
        target TEXT NOT NULL,
        serial TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        labeller TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (kind, target)
    );
    CREATE INDEX IF NOT EXISTS labels_serial ON labels (serial);
    CREATE TABLE IF NOT EXISTS label_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        target TEXT NOT NULL,
        serial TEXT NOT NULL,
        fields_json TEXT,
        labeller TEXT,
        at TEXT NOT NULL
    );
    """

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(
        self,
        kind: str,
        target: str,
        serial: str,
        fields: dict[str, Any] | None,
        labeller: str | None,
    ) -> str:
        """Upsert (or delete, when ``fields`` is None) and log the event. Returns timestamp."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(fields) if fields is not None else None
        with closing(self._connect()) as conn, conn:
            if fields is None:
                conn.execute("DELETE FROM labels WHERE kind = ? AND target = ?", (kind, target))
            else:
                conn.execute(
                    """INSERT INTO labels (kind, target, serial, fields_json, labeller, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (kind, target) DO UPDATE SET
                         fields_json = excluded.fields_json,
                         labeller = excluded.labeller,
                         updated_at = excluded.updated_at""",
                    (kind, target, serial, payload, labeller, now),
                )
            conn.execute(
                "INSERT INTO label_events (kind, target, serial, fields_json, labeller, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (kind, target, serial, payload, labeller, now),
            )
        return now

    def for_serial(self, serial: str) -> dict[str, dict[str, Any]]:
        """{'entry': {...} | None, 'photos': {key: {...}}} for one entry."""
        with closing(self._connect()) as conn, conn:
            rows = conn.execute("SELECT * FROM labels WHERE serial = ?", (serial,)).fetchall()
        result: dict[str, Any] = {"entry": None, "photos": {}}
        for row in rows:
            record = {**json.loads(row["fields_json"]), "labeller": row["labeller"], "updated_at": row["updated_at"]}
            if row["kind"] == "entry":
                result["entry"] = record
            else:
                result["photos"][row["target"]] = record
        return result

    def labelled_serials(self) -> set[str]:
        with closing(self._connect()) as conn, conn:
            return {r[0] for r in conn.execute("SELECT DISTINCT serial FROM labels")}

    def export(self) -> list[dict[str, Any]]:
        """Every current label, for a committed JSON snapshot."""
        with closing(self._connect()) as conn, conn:
            rows = conn.execute("SELECT * FROM labels ORDER BY serial, kind, target").fetchall()
        return [
            {
                "kind": r["kind"],
                "target": r["target"],
                "serial": r["serial"],
                **json.loads(r["fields_json"]),
                "labeller": r["labeller"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


def write_json(records: Iterable[dict[str, Any]] | dict[str, Any], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
