"""Pure image-processing functions for the knitting pattern analyser.

Two entry points:
- classify_image: bytes + (rows, cols, symbols) → grid + representative crops
- colorize_image: bytes + grid + colour map → coloured PNG bytes

All functions are stateless and operate on bytes/arrays so they can be called
from FastAPI handlers or tests without touching the filesystem.
"""

from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass

import cv2
import numpy as np
from sklearn.cluster import KMeans

CELL_SIZE = 32
TIE_THRESHOLD = 0.005   # use histeq to break ties closer than this
MAX_SYMBOLS = 26        # A–Z


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RefCrop:
    label: str
    png_bytes: bytes


@dataclass
class ClassifyResult:
    rows: int
    cols: int
    symbols: int
    labels: list[str]
    grid: list[list[str]]
    crops: list[RefCrop]
    image_bytes: bytes  # original bytes, retained so the session can re-render


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _decode_gray(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Cannot decode image bytes")
    return img


def _decode_color(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image bytes")
    return img


def _encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def png_to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _cell_crop(img: np.ndarray, r: int, c: int, ch: float, cw: float) -> np.ndarray:
    y0, y1 = int(round(r * ch)), int(round((r + 1) * ch))
    x0, x1 = int(round(c * cw)), int(round((c + 1) * cw))
    return img[y0:y1, x0:x1]


def _preprocess(img: np.ndarray) -> np.ndarray:
    r = cv2.resize(img, (CELL_SIZE, CELL_SIZE), interpolation=cv2.INTER_AREA)
    return r.astype(np.float32) / 255.0


def _preprocess_histeq(img: np.ndarray) -> np.ndarray:
    r = cv2.resize(img, (CELL_SIZE, CELL_SIZE), interpolation=cv2.INTER_AREA)
    return cv2.equalizeHist(r).astype(np.float32) / 255.0


def _best_match(
    cell_img: np.ndarray,
    templates: list[tuple[str, np.ndarray]],
    templates_histeq: list[tuple[str, np.ndarray]],
) -> str:
    cell_raw = _preprocess(cell_img)
    scores = sorted(
        [(lbl, float(np.mean((cell_raw - ref) ** 2))) for lbl, ref in templates],
        key=lambda x: x[1],
    )
    best_lbl = scores[0][0]
    if len(scores) > 1 and (scores[1][1] - scores[0][1]) < TIE_THRESHOLD:
        top2 = [scores[0][0], scores[1][0]]
        cell_h = _preprocess_histeq(cell_img)
        ref_h = dict(templates_histeq)
        best_lbl = min(top2, key=lambda l: float(np.mean((cell_h - ref_h[l]) ** 2)))
    return best_lbl


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------

def classify_image(
    image_bytes: bytes,
    rows: int,
    cols: int,
    symbols: int,
) -> ClassifyResult:
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be positive")
    if not 2 <= symbols <= MAX_SYMBOLS:
        raise ValueError(f"symbols must be between 2 and {MAX_SYMBOLS}")

    img = _decode_gray(image_bytes)
    ih, iw = img.shape
    if ih < rows or iw < cols:
        raise ValueError(
            f"Image is too small ({iw}x{ih}) for grid {cols}x{rows}"
        )
    ch, cw = ih / rows, iw / cols

    vectors: list[np.ndarray] = []
    positions: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            crop = _cell_crop(img, r, c, ch, cw)
            resized = cv2.resize(crop, (CELL_SIZE, CELL_SIZE))
            vectors.append(resized.flatten().astype(np.float32) / 255.0)
            positions.append((r, c))

    X = np.array(vectors)

    km = KMeans(n_clusters=symbols, random_state=42, n_init=20)
    km.fit(X)

    label_names = [chr(ord("A") + i) for i in range(symbols)]
    templates: list[tuple[str, np.ndarray]] = []
    templates_histeq: list[tuple[str, np.ndarray]] = []
    crops: list[RefCrop] = []

    for cid in range(symbols):
        member_idx = [i for i, l in enumerate(km.labels_) if l == cid]
        centroid = km.cluster_centers_[cid]
        dists = [np.linalg.norm(X[i] - centroid) for i in member_idx]
        best_i = member_idx[int(np.argmin(dists))]
        r, c = positions[best_i]
        rep = _cell_crop(img, r, c, ch, cw)
        lbl = label_names[cid]

        templates.append((lbl, _preprocess(rep)))
        templates_histeq.append((lbl, _preprocess_histeq(rep)))
        crops.append(RefCrop(label=lbl, png_bytes=_encode_png(rep)))

    grid: list[list[str]] = []
    for r in range(rows):
        row = []
        for c in range(cols):
            crop = _cell_crop(img, r, c, ch, cw)
            row.append(_best_match(crop, templates, templates_histeq))
        grid.append(row)

    return ClassifyResult(
        rows=rows,
        cols=cols,
        symbols=symbols,
        labels=label_names,
        grid=grid,
        crops=crops,
        image_bytes=image_bytes,
    )


def grid_to_csv(grid: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerows(grid)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Colorize
# ---------------------------------------------------------------------------

def colorize_image(
    image_bytes: bytes,
    grid: list[list[str]],
    colors_rgb: dict[str, tuple[int, int, int]],
) -> tuple[bytes, int, int]:
    """Render the original image with each cell tinted by its mapped colour.

    Returns (png_bytes, width, height).
    """
    img = _decode_color(image_bytes)
    n_rows, n_cols = len(grid), len(grid[0])
    ih, iw = img.shape[:2]
    ch, cw = ih / n_rows, iw / n_cols

    # OpenCV is BGR; the public API takes RGB.
    color_bgr = {lbl: (rgb[2], rgb[1], rgb[0]) for lbl, rgb in colors_rgb.items()}
    fallback = (128, 128, 128)

    out = np.zeros_like(img)
    for r in range(n_rows):
        for c in range(n_cols):
            lbl = grid[r][c].strip()
            bgr = color_bgr.get(lbl, fallback)
            y0, y1 = int(round(r * ch)), int(round((r + 1) * ch))
            x0, x1 = int(round(c * cw)), int(round((c + 1) * cw))

            cell = img[y0:y1, x0:x1].astype(np.float32)
            alpha = cell / 255.0
            bg = np.array(bgr, dtype=np.float32)
            colored = alpha * bg + (1.0 - alpha) * (bg * 0.25)
            out[y0:y1, x0:x1] = np.clip(colored, 0, 255).astype(np.uint8)

    return _encode_png(out), iw, ih
