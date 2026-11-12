"""Detect number plates in every sampled image (YOLO) and save padded crops.

Resumable: re-running skips images already in the detections json. Output
records: {image: [{box:[x0,y0,x1,y1], conf, crop}]}.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import yaml  # noqa: E402
from PIL import Image  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((Path(__file__).with_name("config.yaml")).read_text())


def main() -> None:
    from ultralytics import YOLO

    pc = CFG["plates"]
    model = YOLO(str(REPO / pc["detector_weights"]))
    root = REPO / CFG["sample"]["out_dir"]
    out_json = REPO / pc["detections_json"]
    crops = REPO / pc["crops_dir"]
    crops.mkdir(parents=True, exist_ok=True)
    det = json.loads(out_json.read_text()) if out_json.exists() else {}
    imgs = sorted(root.glob("*/*.jpg"))
    for i, p in enumerate(imgs):
        rel = f"{p.parent.name}/{p.name}"
        if rel in det:
            continue
        r = model.predict(str(p), conf=pc["conf"], imgsz=pc["imgsz"], device="cpu", verbose=False)[0]
        im = Image.open(p).convert("RGB")
        w, h = im.size
        recs = []
        for k, b in enumerate(r.boxes):
            x0, y0, x1, y1 = [float(v) for v in b.xyxy[0]]
            px, py = (x1 - x0) * pc["crop_pad"], (y1 - y0) * pc["crop_pad"]
            c = im.crop((max(0, x0 - px), max(0, y0 - py), min(w, x1 + px), min(h, y1 + py)))
            cp = crops / f"{p.parent.name}__{p.stem}__{k}.png"
            c.save(cp)
            recs.append({"box": [x0, y0, x1, y1], "conf": float(b.conf[0]), "crop": str(cp.relative_to(REPO))})
        det[rel] = recs
        if i % 25 == 0:
            out_json.write_text(json.dumps(det))
            print(i, len(imgs), flush=True)
    out_json.write_text(json.dumps(det))
    print("done", len(det), "images,", sum(len(v) for v in det.values()), "plates")


if __name__ == "__main__":
    main()
