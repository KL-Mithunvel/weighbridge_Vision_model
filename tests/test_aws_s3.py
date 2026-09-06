"""Unit tests for the pure-logic layer of development/aws_s3.py (no network)."""

import pytest

from aws_s3 import (
    credentials_status,
    extract_key_facets,
    is_image_key,
    key_extension,
    pair_gross_tare,
    summarize_objects,
    top_level_prefix,
)

IMAGE_EXTS = [".jpg", ".jpeg", ".png"]


def _obj(key, size=1000, last_modified="2026-03-06T10:00:00+05:30"):
    return {"key": key, "size": size, "last_modified": last_modified, "storage_class": "STANDARD"}


# --------------------------------------------------------------------------- #
# credentials_status                                                           #
# --------------------------------------------------------------------------- #
def test_credentials_status_all_present():
    env = {
        "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "AWS_DEFAULT_REGION": "ap-south-1",
    }
    status = credentials_status(env)
    assert status["has_keys"] is True
    assert status["has_region"] is True
    assert status["region"] == "ap-south-1"


def test_credentials_status_missing_secret():
    status = credentials_status({"AWS_ACCESS_KEY_ID": "AKIA"})
    assert status["has_keys"] is False
    assert status["present"] == {"AWS_ACCESS_KEY_ID": True, "AWS_SECRET_ACCESS_KEY": False}
    assert status["has_region"] is False


def test_credentials_status_falls_back_to_aws_region():
    status = credentials_status(
        {"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b", "AWS_REGION": "us-east-1"}
    )
    assert status["region"] == "us-east-1"


def test_credentials_status_empty_string_is_not_present():
    status = credentials_status({"AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": ""})
    assert status["has_keys"] is False


# --------------------------------------------------------------------------- #
# key helpers                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key, expected",
    [
        ("a/b/photo.JPG", ".jpg"),
        ("photo.jpeg", ".jpeg"),
        ("noext", ""),
        ("archive.tar.gz", ".gz"),
    ],
)
def test_key_extension(key, expected):
    assert key_extension(key) == expected


def test_is_image_key():
    assert is_image_key("x/y/a.PNG", IMAGE_EXTS) is True
    assert is_image_key("x/y/a.txt", IMAGE_EXTS) is False


@pytest.mark.parametrize(
    "key, expected",
    [
        ("gross/2026/a.jpg", "gross"),
        ("top.jpg", "<root>"),
        ("2026/03/06/a.jpg", "2026"),
    ],
)
def test_top_level_prefix(key, expected):
    assert top_level_prefix(key) == expected


# --------------------------------------------------------------------------- #
# extract_key_facets                                                           #
# --------------------------------------------------------------------------- #
def test_extract_key_facets_none_pattern_returns_none():
    assert extract_key_facets("anything", None) is None


def test_extract_key_facets_matches_named_groups():
    pattern = r"(?P<serial>\d{8}-\d{3}).*(?P<state>gross|tare)"
    facets = extract_key_facets("2026/20260306-001/gross_1.jpg", pattern)
    assert facets == {"serial": "20260306-001", "state": "gross"}


def test_extract_key_facets_no_match_returns_none():
    assert extract_key_facets("random/key.jpg", r"(?P<serial>\d{8}-\d{3})") is None


# --------------------------------------------------------------------------- #
# summarize_objects                                                            #
# --------------------------------------------------------------------------- #
def test_summarize_objects_counts_and_sizes():
    objects = [
        _obj("gross/a.jpg", size=100, last_modified="2026-03-06T10:00:00+05:30"),
        _obj("gross/b.jpg", size=200, last_modified="2026-04-06T10:00:00+05:30"),
        _obj("tare/c.png", size=300, last_modified="2026-04-07T10:00:00+05:30"),
        _obj("manifest.csv", size=50, last_modified="2026-04-07T10:00:00+05:30"),
    ]
    summary = summarize_objects(objects, IMAGE_EXTS)
    assert summary["total_objects"] == 4
    assert summary["total_bytes"] == 650
    assert summary["image_objects"] == 3
    assert summary["image_bytes"] == 600
    assert summary["non_image_objects"] == 1
    assert summary["objects_by_top_level_prefix"] == {"gross": 2, "tare": 1, "<root>": 1}
    assert summary["objects_by_extension"][".jpg"] == 2
    assert summary["objects_by_year_month"] == {"2026-03": 1, "2026-04": 3}
    assert summary["largest_object"] == {"key": "tare/c.png", "size": 300}
    assert summary["last_modified_range"][0].startswith("2026-03-06")


def test_summarize_objects_empty():
    summary = summarize_objects([], IMAGE_EXTS)
    assert summary["total_objects"] == 0
    assert summary["largest_object"] is None
    assert summary["last_modified_range"] is None


# --------------------------------------------------------------------------- #
# pair_gross_tare                                                              #
# --------------------------------------------------------------------------- #
PAIR_PATTERN = r"(?P<serial>\d{8}-\d{3}).*(?P<state>gross|tare)"


def test_pair_gross_tare_without_pattern():
    result = pair_gross_tare([_obj("a.jpg"), _obj("b.jpg")], None)
    assert result["pattern_matched"] is False
    assert result["keys_unmatched"] == 2
    assert result["distinct_serials"] == 0


def test_pair_gross_tare_counts_pairs():
    objects = [
        _obj("2026/20260306-001/gross_1.jpg"),
        _obj("2026/20260306-001/tare_1.jpg"),
        _obj("2026/20260306-002/gross_1.jpg"),
        _obj("2026/20260306-003/tare_1.jpg"),
        _obj("misc/readme.txt"),
    ]
    result = pair_gross_tare(objects, PAIR_PATTERN)
    assert result["pattern_matched"] is True
    assert result["distinct_serials"] == 3
    assert result["serials_with_gross_and_tare"] == 1
    assert result["serials_gross_only"] == 1
    assert result["serials_tare_only"] == 1
    assert result["keys_unmatched"] == 1
