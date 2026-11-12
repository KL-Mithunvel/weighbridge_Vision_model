"""Write docs/ocr/slip_gt.json from the hand-read values below.

Provenance: read by Claude (visual) from full-resolution photos on 2026-11-13
using montages from make_gt_montage.py. Every row with weights satisfies
gross - tare == net, which independently cross-checks the digit reads.
These are silver labels until the owner verifies them.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
pick = dict(json.loads((REPO / "data/ocr_labels/gt_pick.json").read_text()))


def R(serial, slip_no, date, time, plate, gross, tare, net, material="KARUVAI", doc_type="dot_matrix_slip", note=None):
    return dict(serial=serial, slip_no=slip_no, date=date, time=time, plate=plate, gross=gross, tare=tare,
                net=net, material=material, doc_type=doc_type, note=note)


ROWS = [
    R("2026-03-09-002", 156, "09-03-2026", "15:33:48", "TN76AH0245", 3880, 2190, 1690),
    R("2026-03-10-006", 168, "10-03-2026", "17:31:02", "TN76AP0801", 1760, 1150, 610),
    R("2026-03-21-005", 277, "21-03-2026", "17:12:05", "TN76AP0801", 1650, 1150, 500),
    R("2026-03-26-003", 311, "26-03-2026", "16:58:50", "TN76C5628", 1030, 610, 420),
    R("2026-04-07-004", 334, "07-04-2026", "17:05:09", "TN38CT4575", 1670, 640, 1030),
    R("2026-04-13-002", 347, "13-04-2026", "16:28:24", "TN76AS1365", 1480, 660, 820),
    R("2026-04-20-003", 364, "20-04-2026", "17:42:52", "TN76AH0245", 3910, 2180, 1730),
    R("2026-04-27-002", 375, "27-04-2026", "17:26:21", "TN76BD9867", 3880, 2420, 1460),
    R("2026-05-23-005", 459, "23-05-2026", "15:40:10", "TN45BQ1769", 1670, 650, 1020),
    R("2026-06-24-002", 652, "24-06-2026", "12:13:19", "TN74AD5565", 4140, 1990, 2150),
    R("2026-07-06-005", 730, "06-07-2026", "16:42:22", "TN76AS8660", 2500, 1830, 670),
    R("2026-07-09-002", 747, "09-07-2026", "15:33:42", "TN76AJ3396", 6110, 3370, 2740,
      note="gross first digit smudged; confirmed by gross-tare=net"),
    R("2026-07-10-009", 760, "10-07-2026", "16:27:24", "TN76T0286", 3120, 1200, 1920),
    R("2026-07-18-003", None, "18-07-2026", "10:35:00", "TN10AU6392", 3290, 1610, 1680,
      doc_type="handwritten_slip", note='hand-written on plain paper, single copy, time "10.35 AM", no slip no'),
    R("2026-07-24-005", 841, "24-07-2026", "15:22:02", "TN76B1015", 1090, 650, 440),
    R("2026-08-01-004", 814, "01-08-2026", "12:41:13", "TN60BZ0501", 2870, 2050, 820),
    R("2026-08-01-010", 820, "01-08-2026", "17:36:50", "TN76AR6028", 7590, 3100, 4490),
    R("2026-08-04-001", 825, "04-08-2026", "09:27:30", "TN56P1693", 3670, 1580, 2090),
    R("2026-08-04-003", 827, "04-08-2026", "12:14:38", "TN76H4533", 1840, 660, 1180),
    R("2026-08-04-004", 828, "04-08-2026", "14:01:29", "TN72BJ4263", 1850, 680, 1170),
    R("20260306-005", None, None, None, None, None, None, None, None, doc_type="software_screenshot",
      note='photo of weighbridge software "Vehicle Second Transaction" (ticket 136, TN 76 AJ 3396, Empty, PULI, '
           "loaded 7120 / empty 2950 / net 4170); not a slip"),
    R("20260306-008", 139, "06-03-2026", "18:51:46", "TN60AU1552", 3960, 2150, 1810),
    R("20260307-001", 140, "07-03-2026", "08:47:40", "TN798474", 5840, 2980, 2860,
      note="photo stored 90deg rotated (EXIF orientation=1); slip plate has no series letters"),
    R("20260307-004", 143, "07-03-2026", "11:22:07", "TN67M2154", 3770, 2960, 810),
]

if __name__ == "__main__":
    out = {"provenance": __doc__.strip(), "items": []}
    for d in ROWS:
        d["image"] = pick[d["serial"]].replace(chr(92), "/")
        if d["gross"] is not None:
            assert d["gross"] - d["tare"] == d["net"], d["serial"]
        out["items"].append(d)
    (REPO / "docs/ocr").mkdir(exist_ok=True)
    (REPO / "docs/ocr/slip_gt.json").write_text(json.dumps(out, indent=1))
    print(len(out["items"]), "rows written")
