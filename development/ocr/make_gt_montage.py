"""Build 2x2 montages of the left slip copy for hand-reading ground truth."""
import json, random, sys
from pathlib import Path
from PIL import Image, ImageDraw
REPO = Path(__file__).resolve().parents[2]
root = REPO / "data/ocr_sample"
serials = sorted(d.name for d in root.iterdir())
rng = random.Random(11)
pick = sorted(rng.sample(serials, 24))
items = []
for s in pick:
    fs = sorted(f for f in (root / s).glob("*.jpg") if f.stat().st_size >= 1_000_000)
    items.append((s, fs[-1]))
(REPO / "data/ocr_labels").mkdir(exist_ok=True)
(REPO / "data/ocr_labels/gt_pick.json").write_text(json.dumps([[s, str(f.relative_to(REPO))] for s, f in items]))
H = 900
for m in range(0, len(items), 2):
    sheet = Image.new("RGB", (1300, H), "white")
    for j, (s, f) in enumerate(items[m:m + 2]):
        im = Image.open(f).convert("RGB")
        w, h = im.size
        crop = im.crop((int(w * 0.08), 0, int(w * 0.36), int(h * 0.80)))
        crop.thumbnail((650, H))
        sheet.paste(crop, (j * 650, 0))
        ImageDraw.Draw(sheet).text((j * 650 + 4, 2), f"#{m + j} {s}", fill="red")
    sheet.save(REPO / f"data/ocr_labels/montage/m{m // 2}.jpg", quality=88)
print(len(items), "items")
