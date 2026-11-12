"""OCR engine wrappers (thin I/O layer; parsing lives in slip_parse.py).

Every box-engine returns ``list[Token]`` for one image. Engines are created
lazily and cached so a benchmark run pays model load once.

Windows note: set OPENBLAS_NUM_THREADS=4 before importing numpy-heavy libs,
otherwise OpenBLAS fails with "Memory allocation still failed" on this laptop.
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

from dataclasses import dataclass  # noqa: E402
from functools import lru_cache  # noqa: E402
from typing import Callable  # noqa: E402


@dataclass(frozen=True)
class Token:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _box(points) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


# Device policy: this laptop has NO Windows page file and ~2 GB free commit, so
# any single CUDA allocation > ~500 MB fails even with 4.5 GB VRAM free
# (verified 2026-11-13). Default to CPU; set OCR_DEVICE=cuda to try the GPU.
DEVICE = os.environ.get("OCR_DEVICE", "cpu")


@lru_cache(maxsize=1)
def _easy():
    import easyocr

    return easyocr.Reader(["en"], gpu=DEVICE == "cuda", verbose=False)


def easyocr_run(path: str) -> list[Token]:
    out = []
    for pts, text, conf in _easy().readtext(path, paragraph=False, canvas_size=1600):
        out.append(Token(text, *_box(pts), float(conf)))
    return out


@lru_cache(maxsize=1)
def _rapid():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def rapidocr_run(path: str) -> list[Token]:
    # Default detector limit (736 px long side) loses small print on a 3-4k px
    # photo; raise it per call.
    result, _ = _rapid()(path, det_limit_side_len=1920, det_limit_type="max")
    return [Token(t, *_box(p), float(c)) for p, t, c in (result or [])]


@lru_cache(maxsize=1)
def _doctr():
    from doctr.models import ocr_predictor

    m = ocr_predictor(det_arch="db_resnet50", reco_arch="crnn_vgg16_bn", pretrained=True)
    return m.cuda() if DEVICE == "cuda" else m


def doctr_run(path: str) -> list[Token]:
    from doctr.io import DocumentFile

    doc = DocumentFile.from_images(path)
    res = _doctr()(doc)
    page = res.pages[0]
    h, w = page.dimensions
    out = []
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                (x0, y0), (x1, y1) = word.geometry
                out.append(Token(word.value, x0 * w, y0 * h, x1 * w, y1 * h, float(word.confidence)))
    return out


ENGINES: dict[str, Callable[[str], list[Token]]] = {
    "easyocr": easyocr_run,
    "rapidocr": rapidocr_run,
    "doctr": doctr_run,
}
