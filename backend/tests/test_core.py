"""Regression: classify the two fixture charts and check the CLAUDE.md
spot-check tables (Verify 1: image.png, Verify 2: test2.png).

Cluster labels are assigned in arbitrary order, so the tables can't be
compared letter-for-letter. Instead we assert that a single consistent
one-to-one mapping exists between the expected letters and the predicted
labels across *all* checked cells — which is equivalent to the table
holding up to a renaming of labels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import classify_image

ROOT = Path(__file__).resolve().parents[2]

# CLAUDE.md Verify 1: image.png, 10 rows x 86 cols, 14 symbols.
# Column -> values for rows 1-10 (1-based).
VERIFY1_COLS = {
    1:  "A A M A A M A A M M",
    11: "C C C C C B B C C C",
    12: "D E E E D D E E E E",
    16: "F G G G F F G F G F",
    31: "A A M A A A M M A A",
    32: "A A M A A A M M A A",
    34: "I H I H I H H H I I",
    36: "I I I I I I I I I I",
    37: "J J J J J J J B J J",
    38: "B B B F B B B F B B",
    41: "B K K B K K B B B K",
    42: "F F B F B F F B F F",
    51: "K K K K K K K K K K",
    52: "K L L L K K K L K K",
    62: "M N M N M N M M M N",
    63: "B G B B B G G B G G",
    84: "A A G G G A A A A A",
    86: "J J J J J J J J J J",
}

# CLAUDE.md Verify 2: test2.png, 74 rows x 27 cols.
# Row -> values for cols 1-27 (1-based). The legend
# (test2_classify_ans.png) defines 11 symbols A-K; the answer key's "Q"
# in row 56 is a U glyph pixel-identical to K (the distinction existed
# only as a yarn colour in the source pattern, which the black-and-white
# chart does not encode), so it is expected to classify as K.
VERIFY2_ROWS = {
    1:  "G J J G G J J G G J J G G J J G G J J G G J J G G J J",
    2:  "G J J G G J J G G J J G G J J G G J J G G J J G G J J",
    3:  "A E A E A E A E A E A E A E A E A E A E A E A E A E A",
    4:  "E A E E E A E E E A E E E A E E E A E E E A E E E A E",
    6:  "B B B B B B B B B B B B B B B B B B B B B B B B B B B",
    8:  "D D B B B B B B B D D D B B B B B B B D D B D D B B B",
    9:  "I I B B B B B B B B I B B B B B B B B I I B I I B B B",
    10: "C E E E C C C C E E E E E C C C C E E E C C C E E E C",
    12: "H D D D D D H H H D D D H H H D D D D D H H H D D D D",
    15: "I I B B B B B B B B I B B B B B B B B I I B I I B B B",
    16: "D D B B B B B B B D D D B B B B B B B D D B D D B B B",
    17: "D B B B B B B B B B D B B B B B B B B B D B D B B B B",
    18: "B B B B B B B B B B B B B B B B B B B B B B B B B B B",
    19: "K F K F K F K F K F K F K F K F K F K F K F K F K F K",
    20: "F K F F F K F F F K F F F K F F F K F F F K F F F K F",
    21: "K F K F K F K F K F K F K F K F K F K F K F K F K F K",
    22: "A A A A A A A A A A A A A A A A A A A A A A A A A A A",
    24: "G G G A G G G A G G G A G G G A G G G A G G G A G G G",
    26: "C G G G C G C G G G C C C G G G C G C G G G C C C G G",
    27: "E E G E G G G E G E E E E E G E G G G E G E E E E E G",
    28: "E G E G G G G G E G E E E G E G G G G G E G E E E G E",
    50: "F A F F F A F F F A F F F A F F F A F F F A F F F A F",
    51: "A A A I A A A I A A A I A A A I A A A I A A A I A A A",
    52: "J H J J J H J J J H J J J H J J J H J J J H J J J H J",
    53: "A J A J A J A J A J A J A J A J A J A J A J A J A J A",
    54: "J J J A J J J A J J J A J J J A J J J A J J J A J J J",
    55: "J J J J J J J J J J J J J J J J J J J J J J J J J J J",
    56: "Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q",
    57: "K B K K K B K K K B K K K B K K K B K K K B K K K B K",
    59: "B B B B B B B B B B B B B B B B B B B B B B B B B B B",
    60: "C C C C C C C C C C C C C C C C C C C C C C C C C C C",
    # rows 62 and 67 exercise _refine_grid: each contains a cell whose
    # cluster assignment breaks the row's repeating motif until refined
    62: "D D D C D D D C D D D C D D D C D D D C D D D C D D D",
    67: "I A I I A A A I I A I I A A A I I A I I A A A I I A I",
    70: "E E E C E E E C E E E C E E E C E E E C E E E C E E E",
    71: "C E C C C E C C C E C C C E C C C E C C C E C C C E C",
    72: "D D D C D D D C D D D C D D D C D D D C D D D C D D D",
}


def _assert_relabeling(pairs: list[tuple[str, str, str]]) -> None:
    """pairs: (where, expected_letter, predicted_label).

    Asserts expected -> predicted is a function (each expected letter
    always gets the same predicted label) and injective (no two expected
    letters share a predicted label).
    """
    mapping: dict[str, str] = {}
    for where, exp, pred in pairs:
        assert mapping.setdefault(exp, pred) == pred, (
            f"{where}: expected symbol {exp!r} previously classified as "
            f"{mapping[exp]!r} but here as {pred!r}"
        )
    reverse: dict[str, str] = {}
    for exp, pred in mapping.items():
        assert reverse.setdefault(pred, exp) == exp, (
            f"expected symbols {reverse[pred]!r} and {exp!r} both map to "
            f"predicted label {pred!r}"
        )


@pytest.fixture(scope="module")
def result_image_png():
    path = ROOT / "image.png"
    assert path.exists(), f"Missing test fixture: {path}"
    return classify_image(path.read_bytes(), rows=10, cols=86, symbols=14)


@pytest.fixture(scope="module")
def result_test2_png():
    path = ROOT / "test2.png"
    assert path.exists(), f"Missing test fixture: {path}"
    return classify_image(path.read_bytes(), rows=74, cols=27, symbols=11)


def test_classify_image_png_shape(result_image_png) -> None:
    result = result_image_png
    assert result.rows == 10
    assert result.cols == 86
    assert result.symbols == 14
    assert len(result.grid) == 10
    assert all(len(row) == 86 for row in result.grid)
    assert sorted(result.labels) == [chr(ord("A") + i) for i in range(14)]
    assert len(result.crops) == 14


def test_classify_image_png_verify1(result_image_png) -> None:
    grid = result_image_png.grid
    pairs = []
    for col, values in VERIFY1_COLS.items():
        expected = values.split()
        for r in range(10):
            pairs.append((f"col {col} row {r + 1}", expected[r], grid[r][col - 1]))
    _assert_relabeling(pairs)


def test_classify_test2_png_shape(result_test2_png) -> None:
    result = result_test2_png
    assert result.rows == 74
    assert result.cols == 27
    assert result.symbols == 11
    assert len(result.grid) == 74
    assert all(len(row) == 27 for row in result.grid)
    assert sorted(result.labels) == [chr(ord("A") + i) for i in range(11)]
    assert len(result.crops) == 11


def test_classify_test2_png_verify2(result_test2_png) -> None:
    grid = result_test2_png.grid
    pairs = []
    for row, values in VERIFY2_ROWS.items():
        # Q is pixel-identical to K (see VERIFY2_ROWS note).
        expected = values.replace("Q", "K").split()
        for c in range(27):
            pairs.append((f"row {row} col {c + 1}", expected[c], grid[row - 1][c]))
    _assert_relabeling(pairs)
