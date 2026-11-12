"""Run one box-OCR engine over a list of images, one JSON per image (resumable).

Usage: python run_engine.py <engine> [--max-crashes 2]

Why a driver loop: native crashes (segfault inside CRAFT/onnx when Windows runs
out of commit — this laptop has no page file) kill the process. The parent
relaunches the child, which skips finished images; an image that crashes the
child ``max_crashes`` times is recorded as failed and skipped.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent


def cfg() -> dict:
    return yaml.safe_load((HERE / "config.yaml").read_text())


def slip_candidates() -> list[Path]:
    """Last N handheld photos per serial in the sample dir."""
    c = cfg()["sample"]
    root = REPO / c["out_dir"]
    out = []
    for d in sorted(root.iterdir()):
        fs = sorted(f for f in d.glob("*.jpg") if f.stat().st_size >= c["handheld_min_bytes"])
        out += fs[-c["last_handheld_n"]:]
    return out


def out_path(engine: str, img: Path) -> Path:
    return REPO / cfg()["runs"]["out_dir"] / engine / f"{img.parent.name}__{img.stem}.json"


def child(engine: str, skip: set[str]) -> None:
    sys.path.insert(0, str(HERE))
    from engines import ENGINES

    fn = ENGINES[engine]
    for img in slip_candidates():
        op = out_path(engine, img)
        if op.exists() or op.name in skip:
            continue
        print("START", op.name, flush=True)
        t = time.time()
        toks = fn(str(img))
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps({"image": str(img.relative_to(REPO)), "seconds": round(time.time() - t, 2),
                                  "tokens": [dataclasses.asdict(k) for k in toks]}))
        print("DONE", op.name, flush=True)


def parent(engine: str, max_crashes: int) -> None:
    crashes: dict[str, int] = {}
    failed: set[str] = set()
    while True:
        todo = [out_path(engine, i).name for i in slip_candidates()
                if not out_path(engine, i).exists() and out_path(engine, i).name not in failed]
        if not todo:
            break
        p = subprocess.run([sys.executable, __file__, engine, "--child", "--skip", *failed],
                           capture_output=True, text=True)
        last = [ln.split()[1] for ln in p.stdout.splitlines() if ln.startswith("START")]
        done = {ln.split()[1] for ln in p.stdout.splitlines() if ln.startswith("DONE")}
        if p.returncode != 0 and last and last[-1] not in done:
            n = crashes[last[-1]] = crashes.get(last[-1], 0) + 1
            print(f"crash on {last[-1]} ({n})", flush=True)
            if n >= max_crashes:
                failed.add(last[-1])
        elif p.returncode != 0:
            print("child failed:", p.stderr[-400:], flush=True)
            time.sleep(5)
    fails = REPO / cfg()["runs"]["out_dir"] / engine / "_failed.json"
    fails.parent.mkdir(parents=True, exist_ok=True)
    fails.write_text(json.dumps(sorted(failed)))
    print(f"{engine}: finished, {len(failed)} failed images")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("engine")
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--max-crashes", type=int, default=2)
    a = ap.parse_args()
    child(a.engine, set(a.skip)) if a.child else parent(a.engine, a.max_crashes)
