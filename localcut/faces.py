"""Local face detection (YuNet ONNX via onnxruntime) and blurring (Pillow).

OpenCV has no official win_arm64 wheel, so YuNet's outputs are decoded here in numpy,
following OpenCV's FaceDetectorYN post-processing (score = sqrt(cls * obj)).
Model: face_detection_yunet_2023mar.onnx from opencv/opencv_zoo (MIT), not bundled.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import config

INPUT = 640
STRIDES = (8, 16, 32)
MODEL_NAME = "face_detection_yunet_2023mar.onnx"


@dataclass
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float

    def box(self, pad: float = 0.25) -> tuple[int, int, int, int]:
        px, py = self.w * pad, self.h * pad
        return (int(self.x - px), int(self.y - py), int(self.x + self.w + px), int(self.y + self.h + py))


def model_path() -> Path | None:
    env = os.environ.get("LOCALCUT_FACE_MODEL")
    if env:
        return Path(env)
    hits = list(config.TOOLS_DIR.rglob(MODEL_NAME)) if config.TOOLS_DIR.is_dir() else []
    return hits[0] if hits else None


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort  # imported lazily so the rest of localcut works without it

    path = model_path()
    if not path or not path.is_file():
        raise FileNotFoundError(f"{MODEL_NAME} not found (set LOCALCUT_FACE_MODEL or put it under {config.TOOLS_DIR})")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _letterbox(img: Image.Image) -> tuple[np.ndarray, float]:
    """Pad to a square at the top-left, resize to 640, return NCHW float32 BGR and the scale factor."""
    side = max(img.size)
    canvas = Image.new("RGB", (side, side))
    canvas.paste(img.convert("RGB"), (0, 0))
    scale = INPUT / side
    arr = np.asarray(canvas.resize((INPUT, INPUT), Image.BILINEAR), dtype=np.float32)[:, :, ::-1]
    return np.ascontiguousarray(arr.transpose(2, 0, 1)[None]), scale


def decode(outputs: dict[str, np.ndarray], score_threshold: float = 0.6) -> list[Face]:
    """Decode YuNet head outputs (in 640x640 input coordinates)."""
    faces: list[Face] = []
    for s in STRIDES:
        n = INPUT // s
        cls = np.clip(outputs[f"cls_{s}"].reshape(-1), 0, 1)
        obj = np.clip(outputs[f"obj_{s}"].reshape(-1), 0, 1)
        bbox = outputs[f"bbox_{s}"].reshape(-1, 4)
        score = np.sqrt(cls * obj)
        for idx in np.nonzero(score >= score_threshold)[0]:
            r, c = divmod(int(idx), n)
            cx, cy = (c + bbox[idx, 0]) * s, (r + bbox[idx, 1]) * s
            w, h = np.exp(bbox[idx, 2]) * s, np.exp(bbox[idx, 3]) * s
            faces.append(Face(float(cx - w / 2), float(cy - h / 2), float(w), float(h), float(score[idx])))
    return nms(faces)


def nms(faces: list[Face], iou_threshold: float = 0.3) -> list[Face]:
    keep: list[Face] = []
    for f in sorted(faces, key=lambda f: f.score, reverse=True):
        if all(_iou(f, k) < iou_threshold for k in keep):
            keep.append(f)
    return keep


def _iou(a: Face, b: Face) -> float:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def detect(img: Image.Image, score_threshold: float = 0.6) -> list[Face]:
    sess = _session()
    blob, scale = _letterbox(img)
    names = [o.name for o in sess.get_outputs()]
    outputs = dict(zip(names, sess.run(names, {sess.get_inputs()[0].name: blob})))
    return [Face(f.x / scale, f.y / scale, f.w / scale, f.h / scale, f.score)
            for f in decode(outputs, score_threshold)]


def blur(img: Image.Image, faces: list[Face], radius_ratio: float = 0.25) -> Image.Image:
    out = img.convert("RGB").copy()
    for f in faces:
        x1, y1, x2, y2 = f.box()
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(out.width, x2), min(out.height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        region = out.crop((x1, y1, x2, y2))
        radius = max(4, int(max(region.size) * radius_ratio))
        out.paste(region.filter(ImageFilter.GaussianBlur(radius)), (x1, y1))
    return out
