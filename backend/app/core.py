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
from sklearn.neural_network import MLPClassifier

CELL_SIZE = 32
MAX_SYMBOLS = 26        # A–Z
INK_VALLEY_FRAC = 0.01  # histogram-valley cutoff relative to the ink peak
FEATURE_BLUR_SIGMA = 1.5  # softens ±1 px grid-rounding offsets

# Periodic-pattern refinement knobs (see _refine_grid)
REFINE_MAX_PERIOD = 12   # largest horizontal motif period considered
REFINE_MIN_AGREE = 0.85  # row must be this periodic for refinement
REFINE_TOLERANCE = 2.0   # pixel-distance slack for accepting a pattern fix
REFINE_MAX_PASSES = 3    # wrong witnesses can unblock after other fixes

# Overcluster-then-merge knobs (see classify_image)
OVERCLUSTER_EXTRA = 6   # surplus K-means clusters absorbing context splits
BAR_DEPTH = 3           # border rows/cols checked for boundary bars
BAR_SPAN_FRAC = 0.8     # ink fraction that marks a line as a boundary bar
MATCH_SHIFT = 4         # ± translation search in _glyph_dist (tile px)
FILL_MARGIN = 4         # central-window inset for the fill channel
EDGE_MARGIN = 8         # deeper inset for the edge channel
EDGE_WEIGHT = 0.4       # weight of the edge channel in _glyph_dist
MASS_WEIGHT = 0.2       # weight of the ink-mass-ratio penalty
MASS_SMOOTH = 20.0      # additive smoothing for the mass ratio
MIN_INK_PIXELS = 4      # below this a cell is treated as blank

# HOG-based reference matching (legend mode)
HOG_NORM_SIZE = 32
HOG_CELL_SHRINK = 0.85
_HOG = cv2.HOGDescriptor(
    _winSize=(HOG_NORM_SIZE, HOG_NORM_SIZE),
    _blockSize=(16, 16),
    _blockStride=(8, 8),
    _cellSize=(8, 8),
    _nbins=9,
)


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


def _ink_binarize(img: np.ndarray) -> np.ndarray:
    """Binarize keeping only true symbol ink (0=ink, 255=background).

    Charts render symbols at one darkest shade; overlays such as
    semi-transparent watermarks are strictly lighter — but a watermark
    also *lightens* the glyph ink it covers, so a single threshold either
    keeps watermark strokes or erodes covered glyphs. Hysteresis solves
    both: strong ink (histogram valley above the darkest mode) seeds the
    mask, and lighter sub-Otsu pixels are kept only when they belong to a
    connected component containing a seed. Watermark strokes over blank
    background have no seed and vanish; watermark-covered glyphs are
    restored to full weight. On clean antialiased charts the valley walk
    approaches Otsu and this degrades gracefully to Otsu binarization.
    """
    otsu_t, _ = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_t = int(otsu_t)
    hist = np.bincount(img.ravel(), minlength=256)
    dark = hist[:otsu_t]
    if dark.sum() == 0:
        return np.full_like(img, 255)
    ink_mode = int(np.argmax(dark))
    floor = max(1.0, INK_VALLEY_FRAC * hist[ink_mode])
    t = ink_mode
    while t + 1 < otsu_t and hist[t + 1] >= floor:
        t += 1

    strong = img <= t
    weak = (img < otsu_t).astype(np.uint8)
    n_cc, cc = cv2.connectedComponents(weak, connectivity=8)
    seeded = np.zeros(n_cc, dtype=bool)
    seeded[np.unique(cc[strong])] = True
    seeded[0] = False
    return np.where(seeded[cc], 0, 255).astype(np.uint8)


def _remove_grid_lines(binary: np.ndarray, ch: float, cw: float) -> np.ndarray:
    """Erase thin full-length grid/section lines from an ink mask.

    A grid line is ink that forms a straight run much longer than a cell
    but is only a few pixels thick. Solid blocks (filled cells) also
    contain long runs, so pixels surviving a blocky opening are kept.
    """
    ink = (binary < 128).astype(np.uint8)
    len_h = max(3, int(round(cw * 1.8)))
    len_v = max(3, int(round(ch * 1.8)))
    h_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, len_h), np.uint8))
    v_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((len_v, 1), np.uint8))
    blocky = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    lines = ((h_lines | v_lines) & ~blocky).astype(bool)
    out = binary.copy()
    out[lines] = 255
    return out


def _strip_boundary_bars(cell_bin: np.ndarray) -> np.ndarray:
    """Clear near-full-length ink lines hugging the cell border.

    A row/column of ink spanning most of the cell right at its edge is a
    grid-line remnant or a neighbouring solid cell bleeding across the
    boundary — never glyph: the widest glyph strokes span ~75 % of a
    cell. Solid cells lose a uniform frame, which is consistent across
    all of them and therefore harmless to clustering.
    """
    h, w = cell_bin.shape
    ink = cell_bin < 128
    out = cell_bin.copy()
    for i in range(BAR_DEPTH):
        if ink[i].mean() >= BAR_SPAN_FRAC:
            out[i] = 255
        if ink[h - 1 - i].mean() >= BAR_SPAN_FRAC:
            out[h - 1 - i] = 255
        if ink[:, i].mean() >= BAR_SPAN_FRAC:
            out[:, i] = 255
        if ink[:, w - 1 - i].mean() >= BAR_SPAN_FRAC:
            out[:, w - 1 - i] = 255
    return out


def _cell_tile(cell_bin: np.ndarray) -> np.ndarray:
    """Normalized CELL_SIZE tile of one binarized cell.

    Raw whole-cell appearance: scan-quality charts draw glyphs that
    overflow their cells, so the cell context (including consistent
    neighbour overflow) is part of the signal and must not be discarded
    by centering or bbox cropping.
    """
    cleaned = _strip_boundary_bars(cell_bin)
    return cv2.resize(cleaned, (CELL_SIZE, CELL_SIZE), interpolation=cv2.INTER_AREA)


def _cell_feature(tile: np.ndarray) -> np.ndarray:
    """Clustering vector: blurred tile, tolerant to the ±1 px offsets
    introduced by fractional cell boundaries."""
    blurred = cv2.GaussianBlur(tile, (0, 0), sigmaX=FEATURE_BLUR_SIGMA)
    return blurred.flatten().astype(np.float32) / 255.0


def _shift_ncc(P: np.ndarray, Q: np.ndarray, dy: int, dx: int, m: int) -> float:
    """NCC of P (translated by dy,dx) against Q on the central window."""
    H, W = P.shape
    S = np.zeros_like(P)
    ys0, ys1 = max(0, dy), min(H, H + dy)
    xs0, xs1 = max(0, dx), min(W, W + dx)
    S[ys0:ys1, xs0:xs1] = P[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    Ac, Qc = S[m:H - m, m:W - m], Q[m:H - m, m:W - m]
    na = float(np.sqrt((Ac ** 2).sum()))
    nq = float(np.sqrt((Qc ** 2).sum()))
    if na < 1e-3 and nq < 1e-3:
        return 1.0   # both empty in this window -> identical
    if na < 1e-3 or nq < 1e-3:
        return 0.0
    return float((Ac * Qc).sum()) / (na * nq)


def _glyph_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Symbol-identity distance between two mean-tile images in [0,1].

    Minimized over small translations (fractional-boundary phase), it
    combines three channels chosen so that same-symbol clusters split by
    rendering context score below genuinely different symbols:
    - fill NCC on a central window — the outer ring carries neighbour
      context (adjacent solid cells, grid-line residue), not identity;
    - edge-map NCC on a deeper window — separates outline geometry
      (straight vs curved) and, via the both-empty fallback, treats all
      solid interiors as identical regardless of border differences;
    - smoothed ink-mass ratio — NCC is amplitude-invariant, so glyphs
      differing mainly in mass (solid square vs solid circle, dot vs
      blank) need an explicit penalty.
    """
    ka = 1.0 - a
    kb = 1.0 - b
    kern = np.ones((3, 3), np.uint8)
    ea = cv2.morphologyEx(ka, cv2.MORPH_GRADIENT, kern)
    eb = cv2.morphologyEx(kb, cv2.MORPH_GRADIENT, kern)
    best = np.inf
    for dy in range(-MATCH_SHIFT, MATCH_SHIFT + 1):
        for dx in range(-MATCH_SHIFT, MATCH_SHIFT + 1):
            f = _shift_ncc(ka, kb, dy, dx, FILL_MARGIN)
            e = _shift_ncc(ea, eb, dy, dx, EDGE_MARGIN)
            best = min(best, (1.0 - f) + EDGE_WEIGHT * (1.0 - e))
    wa = float(ka.sum()) + MASS_SMOOTH
    wb = float(kb.sum()) + MASS_SMOOTH
    return best + MASS_WEIGHT * abs(float(np.log(wa / wb)))


def _refine_grid(
    grid: list[list[str]],
    X: np.ndarray,
    centroids: dict[str, np.ndarray],
    rows: int,
    cols: int,
) -> int:
    """Fix isolated cells that break their row's repeating motif.

    Knitting charts repeat horizontally with a short period, so a lone
    cell disagreeing with all its periodic witnesses is almost certainly
    a misclassification (typically a borderline cell dragged into the
    wrong cluster by section-line residue). A row is only considered
    when it is strongly periodic, and a cell is only flipped when every
    witness agrees on one label AND the cell's own pixels are compatible
    with it — pattern evidence overrides the cluster assignment, not the
    image. Returns the number of cells changed.
    """
    fixed = 0
    for _ in range(REFINE_MAX_PASSES):
        changed = 0
        for r in range(rows):
            row = grid[r]
            best_p, best_agree = 0, 0.0
            for p in range(2, min(REFINE_MAX_PERIOD, cols // 2) + 1):
                agree = sum(row[c] == row[c + p] for c in range(cols - p)) / (cols - p)
                if agree > best_agree:
                    best_p, best_agree = p, agree
            if best_agree < REFINE_MIN_AGREE:
                continue
            p = best_p
            for c in range(cols):
                witnesses = [
                    row[c + d] for d in (-2 * p, -p, p, 2 * p)
                    if 0 <= c + d < cols
                ]
                if len(witnesses) < 2 or row[c] in witnesses:
                    continue
                if any(w != witnesses[0] for w in witnesses):
                    continue
                suggested = witnesses[0]
                vec = X[r * cols + c]
                d_sug = float(np.linalg.norm(vec - centroids[suggested]))
                d_cur = float(np.linalg.norm(vec - centroids[row[c]]))
                if d_sug <= d_cur * REFINE_TOLERANCE:
                    row[c] = suggested
                    changed += 1
        fixed += changed
        if not changed:
            break
    return fixed


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
    binary = _remove_grid_lines(_ink_binarize(img), ch, cw)

    # Cells are sampled at subpixel-exact float boundaries so that a
    # symbol's position inside its window never depends on where integer
    # rounding happened to land for that row/column.
    win = (int(round(cw)), int(round(ch)))
    tiles: list[np.ndarray] = []
    vectors: list[np.ndarray] = []
    for r in range(rows):
        for c in range(cols):
            cell = cv2.getRectSubPix(binary, win, ((c + 0.5) * cw, (r + 0.5) * ch))
            tile = _cell_tile(cell)
            tiles.append(tile)
            vectors.append(_cell_feature(tile))
    X = np.array(vectors)
    T = np.array(tiles, dtype=np.float32) / 255.0

    # Overcluster, then merge back down to `symbols`. K-means splits a
    # symbol when its cells differ in rendering context (watermark bands,
    # neighbouring solid cells, glyph strokes fused with grid lines);
    # surplus clusters absorb those splits, and single-linkage
    # agglomeration under _glyph_dist reunites them: a symbol split three
    # ways may have one variant close to only one of its siblings, so
    # groups must chain through the nearest member. Distances are frozen
    # at the initial clusters, so a merged group cannot drift.
    k = min(symbols + OVERCLUSTER_EXTRA, len(tiles))
    km = KMeans(n_clusters=k, random_state=42, n_init=20)
    km.fit(X)

    groups: dict[int, np.ndarray] = {}
    cent: dict[int, np.ndarray] = {}
    for cid in range(k):
        idx = np.where(km.labels_ == cid)[0]
        if len(idx):
            groups[cid] = idx
            cent[cid] = T[idx].mean(axis=0)

    cids = sorted(groups)
    pair_d = {
        (a, b): _glyph_dist(cent[a], cent[b])
        for i, a in enumerate(cids)
        for b in cids[i + 1:]
    }
    members: dict[int, set[int]] = {cid: {cid} for cid in cids}

    def group_dist(a: int, b: int) -> float:
        return min(
            pair_d[(x, y) if x < y else (y, x)]
            for x in members[a] for y in members[b]
        )

    while len(groups) > symbols:
        live = sorted(groups)
        best = (np.inf, live[0], live[1])
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                d = group_dist(a, b)
                if d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        groups[a] = np.concatenate([groups[a], groups[b]])
        members[a] |= members[b]
        del groups[b], members[b]

    label_names = [chr(ord("A") + i) for i in range(symbols)]
    grid: list[list[str]] = [["?"] * cols for _ in range(rows)]
    crops: list[RefCrop] = []
    centroids: dict[str, np.ndarray] = {}
    for lbl, (cid, idx) in zip(label_names, sorted(groups.items())):
        mean_vec = X[idx].mean(axis=0)
        centroids[lbl] = mean_vec
        rep_i = idx[int(np.argmin(np.linalg.norm(X[idx] - mean_vec, axis=1)))]
        r, c = divmod(int(rep_i), cols)
        rep = cv2.getRectSubPix(img, win, ((c + 0.5) * cw, (r + 0.5) * ch))
        crops.append(RefCrop(label=lbl, png_bytes=_encode_png(rep)))
        for i in idx:
            rr, cc = divmod(int(i), cols)
            grid[rr][cc] = lbl

    _refine_grid(grid, X, centroids, rows, cols)

    return ClassifyResult(
        rows=rows,
        cols=cols,
        symbols=symbols,
        labels=label_names,
        grid=grid,
        crops=crops,
        image_bytes=image_bytes,
    )


# ---------------------------------------------------------------------------
# Legend-based classification (HOG)
# ---------------------------------------------------------------------------

def _bbox_normalize_aspect(binary: np.ndarray) -> np.ndarray | None:
    """Crop to ink bbox, pad to square preserving aspect, resize to HOG_NORM_SIZE.

    binary: uint8 image where dark = ink (<128).
    Returns None if too few ink pixels.
    """
    ink = binary < 128
    if ink.sum() < 3:
        return None
    ys, xs = np.where(ink)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    cropped = binary[y0:y1, x0:x1]
    h, w = cropped.shape
    side = max(h, w) + 4
    canvas = np.full((side, side), 255, dtype=np.uint8)
    oy, ox = (side - h) // 2, (side - w) // 2
    canvas[oy:oy + h, ox:ox + w] = cropped
    return cv2.resize(canvas, (HOG_NORM_SIZE, HOG_NORM_SIZE), interpolation=cv2.INTER_AREA)


def _hog_features(norm: np.ndarray) -> np.ndarray:
    return _HOG.compute(norm).flatten()


# Weights chosen so a single topology mismatch contributes a distance
# comparable to HOG's L2 spread between similar shapes (~1–3 in practice).
_HOLE_WEIGHT = 5.0
_DENSITY_WEIGHT = 3.0
_ASPECT_WEIGHT = 1.5


def _topology_features(binary: np.ndarray) -> np.ndarray:
    """Return [holes, density, log_aspect] computed on the ink bbox.

    binary: uint8 raw cell/ref, dark=ink (<128).
    Holes count interior background components (hollow □ has 1, filled ■ has 0).
    Density is ink fraction inside the bbox.
    Log-aspect compresses extreme aspect ratios (dash ≈ 7.5 → 2).
    """
    ink = binary < 128
    if ink.sum() < 3:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32)
    ys, xs = np.where(ink)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    cropped = binary[y0:y1, x0:x1]
    h, w = cropped.shape

    ink_mask = (cropped < 128).astype(np.uint8) * 255
    contours, hierarchy = cv2.findContours(
        ink_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    holes = 0
    if hierarchy is not None:
        for i, hh in enumerate(hierarchy[0]):
            if hh[3] != -1 and cv2.contourArea(contours[i]) >= 4:
                holes += 1

    density = float(ink_mask.sum() / 255) / float(h * w)
    log_aspect = float(np.log(w / h))
    return np.array(
        [holes * _HOLE_WEIGHT, density * _DENSITY_WEIGHT, log_aspect * _ASPECT_WEIGHT],
        dtype=np.float32,
    )


def _combined_features(binary: np.ndarray) -> np.ndarray | None:
    """HOG ⊕ topology. Returns None if the input has no ink."""
    norm = _bbox_normalize_aspect(binary)
    if norm is None:
        return None
    return np.concatenate([_hog_features(norm), _topology_features(binary)])


# Augmentation knobs for per-session MLP training.
_AUG_PER_REF = 80
_AUG_TRANSLATE = 2.0  # ± pixels
_AUG_SCALE = (0.92, 1.08)
_AUG_ROTATE = 8.0     # ± degrees
_AUG_NOISE_SIGMA = 8.0
_AUG_PAD = 6


def _augment_crop(binary: np.ndarray, n: int, rng: np.random.Generator):
    """Yield n augmented variants of a binary crop via small affine + noise.

    Re-Otsu'd after noise so the result remains a clean binary image.
    """
    h, w = binary.shape
    canvas = np.full((h + 2 * _AUG_PAD, w + 2 * _AUG_PAD), 255, dtype=np.uint8)
    canvas[_AUG_PAD:_AUG_PAD + h, _AUG_PAD:_AUG_PAD + w] = binary
    cy, cx = canvas.shape[0] / 2, canvas.shape[1] / 2
    for _ in range(n):
        tx = rng.uniform(-_AUG_TRANSLATE, _AUG_TRANSLATE)
        ty = rng.uniform(-_AUG_TRANSLATE, _AUG_TRANSLATE)
        scale = rng.uniform(*_AUG_SCALE)
        angle = rng.uniform(-_AUG_ROTATE, _AUG_ROTATE)
        M = cv2.getRotationMatrix2D((cx, cy), angle, scale)
        M[0, 2] += tx
        M[1, 2] += ty
        warped = cv2.warpAffine(
            canvas, M, (canvas.shape[1], canvas.shape[0]), borderValue=255
        )
        noise = rng.normal(0, _AUG_NOISE_SIGMA, warped.shape)
        noisy = np.clip(warped.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        _, nb = cv2.threshold(noisy, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        yield nb


def _train_mlp(
    ref_crops: list[np.ndarray],
    label_names: list[str],
) -> MLPClassifier:
    """Train a tiny MLP on HOG+topology features of augmented ref crops.

    Per-session, takes ~0.1 s for 11 refs × 80 augmentations.
    """
    rng = np.random.default_rng(42)
    X: list[np.ndarray] = []
    y: list[str] = []
    for lbl, crop in zip(label_names, ref_crops):
        feat = _combined_features(crop)
        if feat is not None:
            X.append(feat)
            y.append(lbl)
        for aug in _augment_crop(crop, _AUG_PER_REF, rng):
            feat = _combined_features(aug)
            if feat is not None:
                X.append(feat)
                y.append(lbl)
    mlp = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        max_iter=300,
        random_state=42,
    )
    mlp.fit(np.asarray(X), np.asarray(y))
    return mlp


def extract_legend_symbols(
    legend_bytes: bytes,
    n_symbols: int,
) -> list[np.ndarray]:
    """Find icon-shaped components in a legend image.

    Heuristic: in a typical knitting-pattern legend, each entry is laid out
    horizontally as "X. ICON Color Name 123", so an icon is a component that
    sits 12–45 px to the right of a "label" component (the leading letter).
    Returns a list of original-bytes-uint8 grayscale crops (255=background,
    0=ink) in reading order (top-to-bottom, left-to-right).
    """
    arr = np.frombuffer(legend_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Cannot decode legend image bytes")

    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n_cc, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    # Collect candidate components. Relaxed filter to admit thin dashes
    # and narrow letters.
    comps: list[tuple[int, int, int, int, int]] = []
    for i in range(1, n_cc):
        x, y, w, h, area = stats[i]
        if h > 60 or w > 120:
            continue
        # Thin horizontal bars (dashes) — keep if wide enough
        if h < 8 and (w < 8 or w / max(h, 1) < 3):
            continue
        if area < 12:
            continue
        comps.append((int(x), int(y), int(w), int(h), int(area)))

    if not comps:
        return []

    # Cluster by Y into row bands
    comps.sort(key=lambda c: c[1])
    rows: list[list[tuple]] = []
    cur = [comps[0]]
    for c in comps[1:]:
        if c[1] - cur[-1][1] <= 18:
            cur.append(c)
        else:
            rows.append(cur)
            cur = [c]
    rows.append(cur)

    # For each row, walk left-to-right. A label is a component preceded by
    # a wide gap (or is leftmost). The icon is the next component to its
    # right with gap in [10, 45] px.
    icons: list[tuple[int, int, int, int, int]] = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        for i, comp in enumerate(row):
            x, y, w, h, _ = comp
            if i == 0:
                gap_left = x  # leftmost in row
            else:
                px, _, pw, _, _ = row[i - 1]
                gap_left = x - (px + pw)
            # Label test: leftmost OR preceded by big gap
            if not (i == 0 or gap_left > 45):
                continue
            # Look for next component in the same row that could be an icon
            for j in range(i + 1, len(row)):
                nx, ny, nw, nh, _ = row[j]
                prev = row[j - 1]
                gap = nx - (prev[0] + prev[2])
                if gap < 10:
                    continue
                if gap > 45:
                    break
                # Vertical alignment check: icon's vertical center close to label's
                if abs((ny + nh / 2) - (y + h / 2)) > 14:
                    continue
                icons.append(row[j])
                break

    # Reading-order sort (top to bottom, left to right)
    icons.sort(key=lambda c: (c[1] // 30, c[0]))

    # Extract grayscale crops with a small padding so HOG normalisation is
    # not over-tight.
    crops = []
    PAD = 3
    H, W = img.shape
    for x, y, w, h, _ in icons[:n_symbols]:
        y0, y1 = max(0, y - PAD), min(H, y + h + PAD)
        x0, x1 = max(0, x - PAD), min(W, x + w + PAD)
        # Binarize the crop region so feature comparison is consistent
        _, crop_bin = cv2.threshold(
            img[y0:y1, x0:x1], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        crops.append(crop_bin)
    return crops


def classify_image_with_legend(
    image_bytes: bytes,
    legend_bytes: bytes,
    rows: int,
    cols: int,
    symbols: int,
) -> ClassifyResult:
    """Classify pattern cells by HOG-matching against icons extracted from
    a user-supplied legend image. Falls back to ValueError if extraction
    yields fewer icons than requested.
    """
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be positive")
    if not 2 <= symbols <= MAX_SYMBOLS:
        raise ValueError(f"symbols must be between 2 and {MAX_SYMBOLS}")

    # Extract reference icons from legend
    ref_crops = extract_legend_symbols(legend_bytes, symbols)
    if len(ref_crops) < symbols:
        raise ValueError(
            f"Found only {len(ref_crops)} icons in legend; expected {symbols}. "
            "Try a clearer legend image or check the declared symbol count."
        )

    label_names = [chr(ord("A") + i) for i in range(symbols)]

    # Sanity-check each ref has ink, and stash for the API response
    ref_png_bytes: list[RefCrop] = []
    for lbl, crop in zip(label_names, ref_crops):
        if _combined_features(crop) is None:
            raise ValueError(f"Legend icon {lbl} has no ink — extraction failed")
        ref_png_bytes.append(RefCrop(label=lbl, png_bytes=_encode_png(crop)))

    # Train a tiny MLP on augmented icons. Per-session, ~0.1 s.
    mlp = _train_mlp(ref_crops, label_names)

    # Decode and binarize pattern
    img = _decode_gray(image_bytes)
    _, img_bin = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ih, iw = img_bin.shape
    if ih < rows or iw < cols:
        raise ValueError(f"Image is too small ({iw}x{ih}) for grid {cols}x{rows}")
    ch, cw = ih / rows, iw / cols

    # Classify each cell
    grid: list[list[str]] = []
    for r in range(rows):
        row = []
        for c in range(cols):
            y0 = int(round(r * ch + ch * (1 - HOG_CELL_SHRINK) / 2))
            y1 = int(round((r + 1) * ch - ch * (1 - HOG_CELL_SHRINK) / 2))
            x0 = int(round(c * cw + cw * (1 - HOG_CELL_SHRINK) / 2))
            x1 = int(round((c + 1) * cw - cw * (1 - HOG_CELL_SHRINK) / 2))
            cell = img_bin[y0:y1, x0:x1]
            feat = _combined_features(cell)
            if feat is None:
                row.append(label_names[0])
                continue
            row.append(str(mlp.predict([feat])[0]))
        grid.append(row)

    return ClassifyResult(
        rows=rows,
        cols=cols,
        symbols=symbols,
        labels=label_names,
        grid=grid,
        crops=ref_png_bytes,
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
