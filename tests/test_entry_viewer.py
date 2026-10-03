"""Tests for development/entry_viewer — pure logic, label store, and the Flask
app against a fake S3 client (no network, no real data)."""

import json
import sqlite3
from contextlib import closing

import pytest
from PIL import Image

from entry_viewer import index as ix
from entry_viewer.app import create_app
from entry_viewer.sources import LabelStore

KEY_PATTERN = r"(?P<serial>\d{4}-\d{2}-\d{2}-\d{3}|\d{8}-\d{3})"
EXTS = [".jpg", ".jpeg", ".png"]
ROLE_RULES = {
    "by_resolution": {"2688x1520": "cctv_indoor", "1920x1080": "cctv_platform", "4160x1920": "phone"},
    "cctv_max_bytes": 838861,
    "small_unknown": "cctv?",
    "large_unknown": "phone_irregular",
}
VOCAB = {
    "photo": {"role": ["phone_load", "weigh_slip"], "load_state": ["loaded", "empty"]},
    "entry": {"suspect": ["no", "yes"]},
}


def _obj(key, size=3_000_000):
    return {"key": key, "size": size, "etag": "e", "storage_class": "GLACIER_IR"}


# --------------------------------------------------------------------------- #
# Pure logic                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-19-001", "20260319-001"),
        ("20260319-001", "20260319-001"),
        (" 2026-03-31-002 ", "20260331-002"),
        ("2026-03-19", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_serial(raw, expected):
    assert ix.normalize_serial(raw) == expected


def test_capture_time_from_filename_not_upload_time():
    taken = ix.capture_time("weighments-202603/2026-03-19-001/20260319_082038_ab12cd34.jpg")
    assert taken.isoformat() == "2026-03-19T08:20:38"
    assert ix.capture_time("weighments-202603/2026-03-19-001/photo.jpg") is None


def test_build_index_merges_both_folder_conventions_and_sorts_by_time():
    objects = [
        _obj("w/2026-03-07-001/20260307_121500_b.jpg"),
        _obj("w/20260307-001/20260307_121000_a.jpg"),
        _obj("w/2026-03-07-002/20260307_130000_c.jpg"),
        _obj("w/2026-03-07-002/notes.txt"),          # not an image
        _obj("w/misc/20260307_130000_d.jpg"),        # no serial
    ]
    index = ix.build_index(objects, KEY_PATTERN, EXTS)
    assert set(index) == {"20260307-001", "20260307-002"}
    first = index["20260307-001"]
    assert first["date"] == "2026-03-07"
    assert first["folders"] == {"2026-03-07-001", "20260307-001"}
    assert [p["key"].rsplit("_", 1)[1] for p in first["photos"]] == ["a.jpg", "b.jpg"]


def test_report_only_entries_and_listing():
    index = ix.build_index([_obj("w/2026-03-07-001/20260307_121000_a.jpg")], KEY_PATTERN, EXTS)
    reports = ix.group_reports(
        [
            {"serial": "20260307-001", "created_at": "2026-03-07 10:00:00"},
            {"serial": "2026-03-07-001", "created_at": "2026-03-07 11:00:00"},
            {"serial": "20260807-004", "created_at": "2026-08-07 09:00:00"},
        ]
    )
    assert [r["created_at"] for r in reports["20260307-001"]] == ["2026-03-07 11:00:00", "2026-03-07 10:00:00"]
    ix.add_report_only_entries(index, reports)
    assert index["20260807-004"]["photos"] == []

    dates = ix.list_dates(index, reports)
    assert dates == [
        {"date": "2026-03-07", "entries": 1, "photos": 1, "with_report": 1},
        {"date": "2026-08-07", "entries": 1, "photos": 0, "with_report": 1},
    ]
    rows = ix.list_entries(index, reports, "2026-03-07")
    assert rows == [
        {"serial": "20260307-001", "number": "001", "photos": 1, "reports": 2, "duplicate_folders": False}
    ]


def test_split_visits_on_gap_and_untimed_last():
    photos = [
        {"key": "a", "captured_at": "2026-03-19T08:20:38"},
        {"key": "b", "captured_at": "2026-03-19T08:23:00"},
        {"key": "c", "captured_at": "2026-03-19T08:41:34"},
        {"key": "d", "captured_at": None},
    ]
    visits = ix.split_visits(photos, gap_minutes=5)
    assert [[p["key"] for p in v] for v in visits] == [["a", "b"], ["c"], ["d"]]


def test_visit_caption_only_guesses_for_two_visits():
    assert "provisional gross" in ix.visit_caption(0, 2)
    assert "provisional tare" in ix.visit_caption(1, 2)
    assert ix.visit_caption(2, 3) == "Visit 3 of 3"


@pytest.mark.parametrize(
    ("size", "resolution", "expected"),
    [
        (300_000, "2688x1520", "cctv_indoor"),
        (3_000_000, "4160x1920", "phone"),
        (300_000, None, "cctv?"),
        (1_700_000, "3338x1805", "phone_irregular"),
    ],
)
def test_guess_role(size, resolution, expected):
    assert ix.guess_role(size, resolution, ROLE_RULES) == expected


@pytest.mark.parametrize(
    "key", ["../etc/passwd", "/abs/key.jpg", "a//b.jpg", "a/./b.jpg", "a\\..\\b.jpg", "C:/x.jpg", ""]
)
def test_safe_cache_relpath_rejects_traversal(key):
    with pytest.raises(ValueError):
        ix.safe_cache_relpath(key)


def test_validate_label_accepts_vocab_and_clears_empty():
    cleaned = ix.validate_label({"role": "weigh_slip", "load_state": "", "notes": "  slip  "}, VOCAB["photo"])
    assert cleaned == {"role": "weigh_slip", "load_state": None, "notes": "slip"}
    assert ix.is_empty_label(ix.validate_label({}, VOCAB["photo"]))


@pytest.mark.parametrize(
    "payload",
    [{"role": "truck"}, {"colour": "red"}, {"notes": 5}, {"notes": "x" * (ix.NOTES_MAX_CHARS + 1)}],
)
def test_validate_label_rejects(payload):
    with pytest.raises(ValueError):
        ix.validate_label(payload, VOCAB["photo"])


# --------------------------------------------------------------------------- #
# Label store                                                                  #
# --------------------------------------------------------------------------- #
def test_label_store_upsert_delete_and_history(tmp_path):
    db = tmp_path / "labels.sqlite3"
    store = LabelStore(db)
    store.save("photo", "k1", "20260319-001", {"role": "phone_load"}, "KLM")
    store.save("photo", "k1", "20260319-001", {"role": "weigh_slip"}, "KLM")
    store.save("entry", "20260319-001", "20260319-001", {"suspect": "no"}, None)
    got = store.for_serial("20260319-001")
    assert got["photos"]["k1"]["role"] == "weigh_slip"
    assert got["entry"]["suspect"] == "no"

    store.save("photo", "k1", "20260319-001", None, "KLM")
    assert store.for_serial("20260319-001")["photos"] == {}
    assert len(store.export()) == 1
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM label_events").fetchone()[0] == 4


# --------------------------------------------------------------------------- #
# Flask app with a fake S3 client                                              #
# --------------------------------------------------------------------------- #
class FakeS3:
    """Writes a small JPEG for any key and counts downloads."""

    def __init__(self):
        self.downloads = []

    def download_file(self, bucket, key, dest):
        self.downloads.append(key)
        Image.new("RGB", (64, 32), "orange").save(dest, format="JPEG")


@pytest.fixture
def viewer(tmp_path):
    keys = [
        "w/2026-03-19-001/20260319_082038_a.jpg",
        "w/2026-03-19-001/20260319_084134_b.jpg",
        "w/2026-03-19-002/20260319_100000_c.jpg",
    ]
    fake = FakeS3()
    # Pre-compute the size the fake will produce so the cache-skip check matches.
    probe = tmp_path / "probe.jpg"
    fake.download_file(None, None, probe)
    fake.downloads.clear()
    size = probe.stat().st_size

    listing = tmp_path / "objects.jsonl"
    listing.write_text("".join(json.dumps(_obj(k, size)) + "\n" for k in keys), encoding="utf-8")

    reports_db = tmp_path / "reports.sqlite3"
    with closing(sqlite3.connect(reports_db)) as conn, conn:
        conn.execute("CREATE TABLE ai_report_fields (serial TEXT, created_at TEXT, summary TEXT)")
        conn.execute("INSERT INTO ai_report_fields VALUES ('20260319-001', '2026-03-19 08:56:47', 'ok')")

    config = {
        "s3": {"bucket": "b", "region": "ap-south-1", "prefixes": [""], "max_objects": None},
        "inventory": {"image_extensions": EXTS, "key_pattern": KEY_PATTERN},
        "paths": {"objects_jsonl": str(listing)},
        "viewer": {
            "cache_dir": str(tmp_path / "cache"),
            "thumb_max_px": 32,
            "thumb_jpeg_quality": 70,
            "reports_db": str(reports_db),
            "reports_table": "ai_report_fields",
            "labels_db": str(tmp_path / "labels.sqlite3"),
            "visit_gap_minutes": 5,
            "role_guess": ROLE_RULES,
            "labels": VOCAB,
        },
    }
    app = create_app(config, client_factory=lambda: fake)
    return app.test_client(), fake, keys


def test_dates_entries_and_entry_payload(viewer):
    client, _, keys = viewer
    assert client.get("/api/dates").get_json() == [
        {"date": "2026-03-19", "entries": 2, "photos": 3, "with_report": 1}
    ]
    entries = client.get("/api/dates/2026-03-19/entries").get_json()
    assert [e["number"] for e in entries] == ["001", "002"]

    entry = client.get("/api/entries/20260319-001").get_json()
    assert [v["caption"] for v in entry["visits"]] == ["Visit 1 — provisional gross", "Visit 2 — provisional tare"]
    assert entry["reports"][0]["summary"] == "ok"
    assert entry["prev"] is None and entry["next"] == "20260319-002"
    assert client.get("/api/entries/20260319-999").status_code == 404


def test_images_download_once_and_unknown_keys_refused(viewer):
    client, fake, keys = viewer
    assert client.get("/api/photo/thumb", query_string={"key": keys[0]}).status_code == 200
    assert client.get("/api/photo/full", query_string={"key": keys[0]}).status_code == 200
    assert client.get("/api/photo/thumb", query_string={"key": keys[0]}).status_code == 200
    assert fake.downloads == [keys[0]]  # GLACIER_IR: fetched exactly once

    photo = client.get("/api/entries/20260319-001").get_json()["visits"][0]["photos"][0]
    assert photo["cached"] is True and photo["resolution"] == "64x32"

    assert client.get("/api/photo/full", query_string={"key": "w/other.jpg"}).status_code == 404
    assert fake.downloads == [keys[0]]


def test_labels_round_trip_and_validation(viewer):
    client, _, keys = viewer
    res = client.post("/api/labels/photo", json={"key": keys[0], "labeller": "KLM",
                                                "fields": {"role": "phone_load", "notes": "rope"}})
    assert res.status_code == 200
    res = client.post("/api/labels/entry", json={"serial": "20260319-001", "fields": {"suspect": "yes"}})
    assert res.status_code == 200

    entry = client.get("/api/entries/20260319-001").get_json()
    assert entry["visits"][0]["photos"][0]["label"]["notes"] == "rope"
    assert entry["entry_label"]["suspect"] == "yes"
    assert [e["labelled"] for e in client.get("/api/dates/2026-03-19/entries").get_json()] == [True, False]
    assert len(client.get("/api/labels/export").get_json()) == 2

    bad = client.post("/api/labels/photo", json={"key": keys[0], "fields": {"role": "truck"}})
    assert bad.status_code == 400 and "not in" in bad.get_json()["error"]
    assert client.post("/api/labels/photo", json={"key": "nope", "fields": {}}).status_code == 404


def test_page_keeps_label_vocab_in_config_order(viewer):
    client, _, _ = viewer
    html = client.get("/").get_data(as_text=True)
    # config order is role -> load_state; Jinja's default would sort them.
    assert html.index('"role"') < html.index('"load_state"')
