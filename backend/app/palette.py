"""Named colour palettes and colour-string parsing."""

from __future__ import annotations

MARIE_WALLIN: dict[str, tuple[int, int, int]] = {
    "walnut":       (105,  62,  75),
    "wood":         (139,  94,  60),
    "pale oak":     (200, 168, 124),
    "chestnut":     (123,  63,   0),
    "eau de nil":   (157, 196, 184),
    "russet":       (128,  70,  27),
    "quince":       (212, 165,  32),
    "dark apple":   ( 61, 107,  61),
    "lime flower":  (212, 224, 160),
    "foxglove":     (185, 131, 145),
    "blossom":      (240, 192, 184),
    "rose":         (208, 112, 128),
    "silver birch": (184, 180, 168),
    "mallard":      ( 44,  95, 107),
}

BASIC_CSS: dict[str, tuple[int, int, int]] = {
    "red":    (255,   0,   0),
    "green":  (  0, 128,   0),
    "blue":   (  0,   0, 255),
    "white":  (255, 255, 255),
    "black":  (  0,   0,   0),
    "gray":   (128, 128, 128),
    "grey":   (128, 128, 128),
    "yellow": (255, 255,   0),
    "orange": (255, 165,   0),
    "purple": (128,   0, 128),
    "pink":   (255, 192, 203),
    "brown":  (139,  69,  19),
    "teal":   (  0, 128, 128),
}

NAMED_COLORS: dict[str, tuple[int, int, int]] = {**MARIE_WALLIN, **BASIC_CSS}

# Preserve insertion order — used as the display order in the UI swatch.
MARIE_WALLIN_DISPLAY_ORDER: list[str] = [
    "Walnut", "Wood", "Pale Oak", "Chestnut", "Eau de Nil",
    "Russet", "Quince", "Dark Apple", "Lime Flower", "Foxglove",
    "Blossom", "Rose", "Silver Birch", "Mallard",
]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def parse_color(s: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' / 'R,G,B' / 'Walnut' → RGB tuple."""
    s = s.strip()
    if s.startswith("#") and len(s) == 7:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
        except ValueError:
            raise ValueError(f"Invalid hex colour: {s!r}")
    if s.count(",") == 2:
        try:
            parts = tuple(int(v.strip()) for v in s.split(","))
        except ValueError:
            raise ValueError(f"Invalid R,G,B colour: {s!r}")
        if any(v < 0 or v > 255 for v in parts):
            raise ValueError(f"R,G,B components out of range: {s!r}")
        return parts  # type: ignore[return-value]
    key = s.lower()
    if key in NAMED_COLORS:
        return NAMED_COLORS[key]
    raise ValueError(f"Unknown colour {s!r}. Use a name, #RRGGBB, or R,G,B.")


def marie_wallin_preset() -> list[dict[str, str]]:
    """Return Marie Wallin palette in display order as [{name, hex}, …]."""
    return [
        {"name": display, "hex": rgb_to_hex(MARIE_WALLIN[display.lower()])}
        for display in MARIE_WALLIN_DISPLAY_ORDER
    ]
