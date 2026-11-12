"""Pure parsing of weigh-slip OCR tokens into fields (no I/O, no OCR imports).

The slip is a 3-copy dot-matrix continuous form: each value is printed three
times side by side, in this vertical order per copy::

    slip no / date dd-mm-yyyy / time hh:mm:ss / plate / gross / tare / net / material

plus a footer ``Weighed on Essae Electronic Weigh Bri  dd-mm-yyyy hh:mm:ss``
and a handwritten signature. Three copies give a free majority vote, and
``net == gross - tare`` is a free correctness check.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from statistics import median

FIELDS = ("slip_no", "date", "time", "plate", "gross", "tare", "net", "material")

# Characters OCR commonly confuses, by the class of character expected.
_TO_DIGIT = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1", "i": "1",
                           "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "T": "7"})
_TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"})

DATE_RE = re.compile(r"(\d{2})\s*[-/.]\s*(\d{2})\s*[-/.]\s*(\d{4})")
TIME_RE = re.compile(r"(\d{2})\s*[:.]\s*(\d{2})\s*[:.]\s*(\d{2})")
PLATE_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")


@dataclass(frozen=True)
class Line:
    text: str
    cx: float
    cy: float
    h: float


def digits_only(s: str) -> str:
    """Map look-alike letters to digits and drop everything else."""
    return re.sub(r"\D", "", s.translate(_TO_DIGIT))


def normalise_plate(raw: str) -> str | None:
    """Return a compact plate ('TN82Z7402') or None if it cannot be a plate.

    Positional repair: 2 state letters, 1-2 district digits, 0-3 series
    letters, 4 digits. Series letters/digits are corrected by position.
    """
    s = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if len(s) < 6:
        return None
    last4 = s[-4:].translate(_TO_DIGIT)
    head = s[:-4]
    if not last4.isdigit() or len(head) < 3:
        return None
    state = head[:2].translate(_TO_LETTER)
    if state == "TH":  # the TN misread seen across engines
        state = "TN"
    rest = head[2:]
    # district: leading 1-2 digit-like chars; series: remaining letters
    m = re.match(r"^([0-9OIlSBZG]{1,2})(.*)$", rest)
    if not m:
        return None
    district = m.group(1).translate(_TO_DIGIT)
    series = m.group(2).translate(_TO_LETTER)
    cand = f"{state}{district}{series}{last4}"
    return cand if PLATE_RE.match(cand) else None


def merge_into_lines(tokens, gap_factor: float = 2.0) -> list[Line]:
    """Merge same-row word tokens that sit close together (docTR splits words).

    Tokens in different slip copies are ~hundreds of px apart so stay separate.
    """
    toks = sorted(tokens, key=lambda t: (t.cy, t.x0))
    if not toks:
        return []
    h_med = median(max(t.y1 - t.y0, 1.0) for t in toks)
    rows: list[list] = []
    for t in toks:
        for r in rows:
            if abs(r[-1].cy - t.cy) < 0.6 * h_med:
                r.append(t)
                break
        else:
            rows.append([t])
    lines: list[Line] = []
    for r in rows:
        r.sort(key=lambda t: t.x0)
        group = [r[0]]
        for t in r[1:]:
            if t.x0 - group[-1].x1 < gap_factor * h_med:
                group.append(t)
            else:
                lines.append(_mk(group))
                group = [t]
        lines.append(_mk(group))
    return lines


def _mk(group) -> Line:
    return Line(" ".join(t.text for t in group), sum(t.cx for t in group) / len(group),
                sum(t.cy for t in group) / len(group), max(t.y1 - t.y0 for t in group))


def _classify(text: str) -> str:
    t = text.strip()
    if DATE_RE.fullmatch(t.replace(" ", "")) or (DATE_RE.search(t) and len(digits_only(t)) == 8):
        return "date"
    if TIME_RE.search(t) and len(digits_only(t)) == 6 and ":" in t.replace(".", ":"):
        return "time"
    if normalise_plate(t) and re.search(r"[A-Za-z]", t[:2]):
        return "plate"
    d = digits_only(t)
    if d and len(d) == len(re.sub(r"\s", "", t)) and 1 <= len(d) <= 6:
        return "int"
    if re.fullmatch(r"[A-Za-z .&-]{3,}", t):
        return "text"
    return "other"


def parse_copy(lines: list[Line]) -> dict[str, str | int | None]:
    """Parse one column of lines (top to bottom) into the slip fields."""
    lines = sorted(lines, key=lambda l: l.cy)
    kinds = [_classify(l.text) for l in lines]
    out: dict[str, str | int | None] = dict.fromkeys(FIELDS)
    di = next((i for i, k in enumerate(kinds) if k == "date"), None)
    if di is None:
        return out
    m = DATE_RE.search(lines[di].text.translate(_TO_DIGIT))
    out["date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    if di > 0 and kinds[di - 1] == "int":
        out["slip_no"] = int(digits_only(lines[di - 1].text))
    rest = list(zip(lines[di + 1:], kinds[di + 1:]))
    ints: list[int] = []
    for l, k in rest:
        if k == "time" and out["time"] is None:
            tm = TIME_RE.search(l.text.translate(_TO_DIGIT))
            out["time"] = f"{tm.group(1)}:{tm.group(2)}:{tm.group(3)}" if tm else None
        elif k == "plate" and out["plate"] is None:
            out["plate"] = normalise_plate(l.text)
        elif k == "int" and out["plate"] is not None and len(ints) < 3:
            ints.append(int(digits_only(l.text)))
        elif k == "text" and len(ints) == 3 and out["material"] is None:
            out["material"] = re.sub(r"[^A-Z]", "", l.text.upper())
    if len(ints) == 3:
        out["gross"], out["tare"], out["net"] = ints
    return out


def split_columns(lines: list[Line]) -> list[list[Line]]:
    """Assign lines to slip copies using the date lines as column anchors."""
    anchors = sorted(l.cx for l in lines if _classify(l.text) == "date")
    if not anchors:
        return []
    cols: list[list[Line]] = [[] for _ in anchors]
    for l in lines:
        j = min(range(len(anchors)), key=lambda j: abs(anchors[j] - l.cx))
        cols[j].append(l)
    return cols


def vote(copies: list[dict]) -> tuple[dict, dict[str, int]]:
    """Majority vote per field across copies; also the winning vote count."""
    res, votes = {}, {}
    for f in FIELDS:
        vals = [c[f] for c in copies if c.get(f) is not None]
        if vals:
            (v, n), = Counter(vals).most_common(1)
            res[f], votes[f] = v, n
        else:
            res[f], votes[f] = None, 0
    return res, votes


def parse_slip(tokens) -> dict:
    """Tokens -> {'fields','votes','n_copies','copies','footer','checks'}."""
    lines = merge_into_lines(tokens)
    cols = split_columns(lines)
    copies = [parse_copy(c) for c in cols]
    fields, votes = vote(copies)
    footer = None
    for l in lines:
        if re.search(r"weigh|essae", l.text, re.I) or (DATE_RE.search(l.text) and TIME_RE.search(l.text)):
            dm = DATE_RE.search(l.text)
            tm = TIME_RE.search(l.text[dm.end():] if dm else l.text)
            if dm and tm:
                footer = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)} {tm.group(1)}:{tm.group(2)}:{tm.group(3)}"
    g, t, n = fields["gross"], fields["tare"], fields["net"]
    checks = {"net_ok": (g - t == n) if None not in (g, t, n) else None,
              "plate_valid": fields["plate"] is not None,
              "complete": all(fields[f] is not None for f in FIELDS)}
    return {"fields": fields, "votes": votes, "n_copies": len(copies), "copies": copies,
            "footer": footer, "checks": checks}
