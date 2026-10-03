"""Weighment entry viewer + labelling GUI (Flask, local only).

Pick a capture date -> pick an entry number -> see that entry's S3 photos,
split into visits, beside its SQL report(s) from the existing LLM audit system,
and label photos / the entry. Settings: ``viewer:`` in development/config.yaml.

Usage (venv active, from the repo root):
    python development/entry_viewer/app.py                 # http://127.0.0.1:5050
    python development/entry_viewer/app.py --export-labels docs/labels/labels_snapshot.json
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from typing import Any

_DEV_DIR = Path(__file__).resolve().parents[1]
if str(_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(_DEV_DIR))

import yaml  # noqa: E402
from flask import Flask, abort, jsonify, render_template, request, send_file  # noqa: E402

from aws_s3 import REPO_ROOT, S3AccessError, load_dotenv_file, make_client  # noqa: E402
from entry_viewer import index as ix  # noqa: E402
from entry_viewer.sources import (  # noqa: E402
    ImageCache,
    LabelStore,
    load_objects_jsonl,
    load_reports,
    write_json,
)


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ViewerState:
    """The in-memory index; rebuilt on start-up and on 'Refresh from S3'."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.viewer = config["viewer"]
        self._lock = threading.Lock()
        self.reports = ix.group_reports(
            load_reports(_resolve(self.viewer["reports_db"]), self.viewer["reports_table"])
        )
        self.rebuild(load_objects_jsonl(_resolve(config["paths"]["objects_jsonl"])))

    def rebuild(self, objects: list[dict[str, Any]]) -> None:
        index = ix.build_index(
            objects,
            self.config["inventory"]["key_pattern"],
            self.config["inventory"]["image_extensions"],
        )
        ix.add_report_only_entries(index, self.reports)
        sizes = {p["key"]: p["size"] for e in index.values() for p in e["photos"]}
        serial_of = {p["key"]: s for s, e in index.items() for p in e["photos"]}
        with self._lock:
            self.index, self.sizes, self.serial_of = index, sizes, serial_of


def create_app(config: dict[str, Any], client_factory: Any = None) -> Flask:
    """Build the Flask app. ``client_factory`` is injectable for tests."""
    viewer = config["viewer"]
    state = ViewerState(config)
    cache = ImageCache(
        client_factory or (lambda: make_client(config["s3"].get("region"))),
        config["s3"]["bucket"],
        _resolve(viewer["cache_dir"]),
        int(viewer["thumb_max_px"]),
        int(viewer["thumb_jpeg_quality"]),
    )
    labels = LabelStore(_resolve(viewer["labels_db"]))
    vocab = viewer["labels"]

    app = Flask(__name__)
    # Keep label fields in config.yaml order — both in API JSON and in the
    # template's |tojson (Jinja's own policy defaults to sort_keys=True).
    app.json.sort_keys = False
    app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}

    @app.errorhandler(S3AccessError)
    def _s3_error(exc: S3AccessError):  # noqa: ANN202
        return jsonify(error=str(exc)), 502

    @app.errorhandler(ValueError)
    def _bad_request(exc: ValueError):  # noqa: ANN202
        return jsonify(error=str(exc)), 400

    def _known_key() -> tuple[str, int]:
        """The ?key= argument, accepted only if it is in the index (no arbitrary fetches)."""
        key = request.args.get("key", "")
        size = state.sizes.get(key)
        if size is None:
            abort(404)
        return key, size

    def _entry_or_404(serial: str) -> dict[str, Any]:
        entry = state.index.get(serial)
        if entry is None:
            abort(404)
        return entry

    @app.get("/")
    def home():  # noqa: ANN202
        return render_template("index.html", vocab=vocab)

    @app.get("/api/dates")
    def dates():  # noqa: ANN202
        return jsonify(ix.list_dates(state.index, state.reports))

    @app.get("/api/coverage")
    def coverage():  # noqa: ANN202
        return jsonify(ix.reconcile(state.index, state.reports))

    @app.get("/api/dates/<date>/entries")
    def entries(date: str):  # noqa: ANN202
        done = labels.labelled_serials()
        rows = ix.list_entries(state.index, state.reports, date)
        for row in rows:
            row["labelled"] = row["serial"] in done
        return jsonify(rows)

    @app.get("/api/entries/<serial>")
    def entry(serial: str):  # noqa: ANN202
        found = _entry_or_404(serial)
        saved = labels.for_serial(serial)
        groups = ix.split_visits(found["photos"], float(viewer["visit_gap_minutes"]))
        visits = []
        for pos, group in enumerate(groups):
            photos = []
            for photo in group:
                resolution = cache.resolution(photo["key"])
                photos.append(
                    {
                        **photo,
                        "resolution": resolution,
                        "role_guess": ix.guess_role(photo["size"], resolution, viewer["role_guess"]),
                        "cached": cache.is_cached(photo["key"], photo["size"]),
                        "label": saved["photos"].get(photo["key"]),
                    }
                )
            visits.append({"caption": ix.visit_caption(pos, len(groups)), "photos": photos})
        same_day = [r["serial"] for r in ix.list_entries(state.index, state.reports, found["date"])]
        pos = same_day.index(serial)
        return jsonify(
            serial=serial,
            date=found["date"],
            folders=sorted(found["folders"]),
            visits=visits,
            reports=state.reports.get(serial, []),
            entry_label=saved["entry"],
            prev=same_day[pos - 1] if pos > 0 else None,
            next=same_day[pos + 1] if pos + 1 < len(same_day) else None,
        )

    @app.get("/api/photo/thumb")
    def thumb():  # noqa: ANN202
        key, size = _known_key()
        return send_file(cache.thumbnail(key, size), mimetype="image/jpeg", max_age=86400)

    @app.get("/api/photo/full")
    def full():  # noqa: ANN202
        key, size = _known_key()
        return send_file(cache.original(key, size), max_age=86400)

    @app.post("/api/labels/photo")
    def label_photo():  # noqa: ANN202
        body = request.get_json(force=True)
        key = body.get("key", "")
        if key not in state.sizes:
            abort(404)
        serial = state.serial_of[key]
        cleaned = ix.validate_label(body.get("fields") or {}, vocab["photo"])
        stored = None if ix.is_empty_label(cleaned) else cleaned
        at = labels.save("photo", key, serial, stored, _labeller(body))
        return jsonify(ok=True, updated_at=at, cleared=stored is None)

    @app.post("/api/labels/entry")
    def label_entry():  # noqa: ANN202
        body = request.get_json(force=True)
        serial = body.get("serial", "")
        _entry_or_404(serial)
        cleaned = ix.validate_label(body.get("fields") or {}, vocab["entry"])
        stored = None if ix.is_empty_label(cleaned) else cleaned
        at = labels.save("entry", serial, serial, stored, _labeller(body))
        return jsonify(ok=True, updated_at=at, cleared=stored is None)

    @app.get("/api/labels/export")
    def export_labels():  # noqa: ANN202
        return jsonify(labels.export())

    @app.post("/api/refresh")
    def refresh():  # noqa: ANN202
        from inventory_s3 import crawl, write_jsonl  # noqa: PLC0415

        s3 = config["s3"]
        client = make_client(s3.get("region"))
        objects = crawl(client, s3["bucket"], s3.get("prefixes") or [""], s3.get("max_objects"))
        write_jsonl(objects, _resolve(config["paths"]["objects_jsonl"]))
        state.rebuild(objects)
        return jsonify(ok=True, objects=len(objects), entries=len(state.index))

    return app


def _labeller(body: dict[str, Any]) -> str | None:
    name = (body.get("labeller") or "").strip()
    return name[:80] or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=_DEV_DIR / "config.yaml")
    parser.add_argument("--export-labels", type=Path, help="write all current labels to this JSON file and exit")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.export_labels:
        records = LabelStore(_resolve(config["viewer"]["labels_db"])).export()
        write_json(records, _resolve(str(args.export_labels)))
        print(f"wrote {len(records)} labels -> {args.export_labels}")
        return 0

    load_dotenv_file()
    app = create_app(config)
    host, port = config["viewer"]["host"], int(config["viewer"]["port"])
    print(f"Entry viewer on http://{host}:{port}  (Ctrl+C to stop)")
    app.run(host=host, port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
