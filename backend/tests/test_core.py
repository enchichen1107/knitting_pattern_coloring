"""Regression: classify image.png and spot-check structural properties.

The K-means cluster labels A–N are assigned in arbitrary order, so we can't
assert specific letters across versions. Instead we verify:

  - the grid has the expected shape and label set
  - columns expected to be uniform are uniform
  - columns expected to share a pattern across rows share that pattern
"""

from __future__ import annotations

from pathlib import Path

from app.core import classify_image

ROOT = Path(__file__).resolve().parents[2]
IMAGE_PATH = ROOT / "image.png"


def _column(grid: list[list[str]], col_1based: int) -> list[str]:
    return [row[col_1based - 1] for row in grid]


def _pattern(values: list[str]) -> tuple[int, ...]:
    """Equivalence-class signature: ('A','A','B','A') → (0,0,1,0)."""
    seen: dict[str, int] = {}
    out: list[int] = []
    for v in values:
        if v not in seen:
            seen[v] = len(seen)
        out.append(seen[v])
    return tuple(out)


def test_classify_image_png() -> None:
    assert IMAGE_PATH.exists(), f"Missing test fixture: {IMAGE_PATH}"

    result = classify_image(IMAGE_PATH.read_bytes(), rows=10, cols=86, symbols=14)

    assert result.rows == 10
    assert result.cols == 86
    assert result.symbols == 14
    assert len(result.grid) == 10
    assert all(len(row) == 86 for row in result.grid)
    assert sorted(result.labels) == [chr(ord("A") + i) for i in range(14)]
    assert len(result.crops) == 14

    # Columns expected to be uniform (every row the same symbol).
    for col in (36, 51, 86):
        values = _column(result.grid, col)
        assert len(set(values)) == 1, f"col {col} not uniform: {values}"

    # Columns expected to follow specific patterns (per CLAUDE.md spot-checks).
    expected_patterns = {
        # col 1: A A M A A M A A M M
        1:  (0, 0, 1, 0, 0, 1, 0, 0, 1, 1),
        # col 11: C C C C C B B C C C
        11: (0, 0, 0, 0, 0, 1, 1, 0, 0, 0),
        # col 41: B K K B K K B B B K
        41: (0, 1, 1, 0, 1, 1, 0, 0, 0, 1),
        # col 52: K L L L K K K L K K
        52: (0, 1, 1, 1, 0, 0, 0, 1, 0, 0),
    }
    for col, expected in expected_patterns.items():
        got = _pattern(_column(result.grid, col))
        assert got == expected, f"col {col}: expected {expected}, got {got}"
