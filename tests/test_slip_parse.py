import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "development" / "ocr"))
from slip_parse import normalise_plate, parse_slip  # noqa: E402


class T:  # minimal Token stand-in
    def __init__(self, text, x, y, w=120, h=30):
        self.text, self.x0, self.y0, self.x1, self.y1 = text, x, y, x + w, y + h
        self.cx, self.cy = x + w / 2, y + h / 2


def copy(x, vals, y0=0):
    return [T(v, x, y0 + i * 110) for i, v in enumerate(vals)]


VALS = ["455", "23-05-2026", "09:11:41", "TN 82 Z 7402", "5520", "3270", "2250", "KARUVAI"]


def test_three_copies_parse_and_vote():
    toks = copy(100, VALS) + copy(1100, VALS) + copy(2100, VALS)
    r = parse_slip(toks)
    assert r["n_copies"] == 3
    assert r["fields"] == {"slip_no": 455, "date": "23-05-2026", "time": "09:11:41", "plate": "TN82Z7402",
                           "gross": 5520, "tare": 3270, "net": 2250, "material": "KARUVAI"}
    assert r["checks"]["net_ok"] and r["checks"]["complete"]


def test_vote_corrects_one_bad_copy():
    bad = [v if v != "5520" else "5S20" for v in VALS]
    r = parse_slip(copy(100, bad) + copy(1100, VALS) + copy(2100, VALS))
    assert r["fields"]["gross"] == 5520 and r["votes"]["gross"] == 3 - 0 or r["votes"]["gross"] >= 2


def test_split_words_are_merged_into_plate():
    words = [T(w, 100 + i * 150, 330, 100) for i, w in enumerate(["TN", "82", "Z", "7402"])]
    toks = copy(100, VALS[:3]) + words + copy(100, VALS[4:], y0=440)
    r = parse_slip(toks)
    assert r["fields"]["plate"] == "TN82Z7402"


def test_plate_confusions():
    assert normalise_plate("TH82Z7402") == "TN82Z7402"
    assert normalise_plate("TN 76 AD 9O87") == "TN76AD9087"
    assert normalise_plate("TN79A9806") == "TN79A9806"
    assert normalise_plate("HELLO") is None


def test_net_check_flags_mismatch():
    vals = VALS[:6] + ["2260", "KARUVAI"]
    r = parse_slip(copy(100, vals))
    assert r["checks"]["net_ok"] is False
