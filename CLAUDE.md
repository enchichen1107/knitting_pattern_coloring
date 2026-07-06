# Knitting Pattern Analyser — Web App

A web app for encoding a knitting pattern image into a coloured chart. The user uploads an image, declares the grid dimensions and number of distinct symbols, maps each detected symbol to a colour, and downloads the coloured result.

> Originally a CLI script (`knit.py`). Now a FastAPI backend + Vite/React/TS frontend. The CLI has been removed; image-processing logic lives in `backend/app/core.py`.

---

## Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI (Python) | Re-uses OpenCV + sklearn pipeline already proven on `image.png` |
| Frontend | Vite + React + TypeScript | Pure SPA, fastest dev loop, clean separation from backend |
| Session store | In-memory dict | MVP only; swap for Redis when going multi-user |
| Deployment (later) | Single Docker container | uvicorn + static React build |

---

## Directory layout

```
knitting/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app + CORS + router wiring
│   │   ├── core.py             # pure image-processing functions
│   │   ├── palette.py          # Marie Wallin named colors + parser
│   │   ├── session.py          # in-memory session store
│   │   ├── schemas.py          # Pydantic request/response models
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── classify.py
│   │       ├── colorize.py
│   │       └── palette.py
│   ├── tests/
│   │   └── test_core.py        # regression vs image.png expected values
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx             # step state machine
│   │   ├── api/client.ts       # typed fetch wrappers
│   │   ├── components/
│   │   │   ├── UploadStep.tsx
│   │   │   ├── MappingStep.tsx
│   │   │   ├── ResultStep.tsx
│   │   │   ├── CropTile.tsx
│   │   │   └── PaletteSwatch.tsx
│   │   ├── types.ts            # mirrors backend Pydantic shapes
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts          # proxy /api → http://localhost:8000
├── image.png                   # test fixture
├── refs/                       # manual reference crops (kept; unused by web app)
└── CLAUDE.md
```

---

## API contract

Base URL: `/api`. JSON unless stated. Errors follow FastAPI default `{ "detail": "..." }`.

### `POST /api/classify`

Multipart upload.

| field | type | notes |
|---|---|---|
| `image` | file | PNG or JPG, ≤ 10 MB |
| `rows` | int | required |
| `cols` | int | required |
| `symbols` | int | required, 2–26 |

**Response 200**
```json
{
  "session_id": "uuid",
  "rows": 10,
  "cols": 86,
  "symbols": 14,
  "labels": ["A", "B", "…", "N"],
  "grid": [["A","A","M","…"], ["…"]],
  "csv": "A,A,M,…\n…",
  "crops": [
    { "label": "A", "png_base64": "iVBORw0K…" }
  ]
}
```

### `POST /api/colorize`

JSON.

```json
{
  "session_id": "uuid",
  "colors": {
    "A": "#6B3E4B",
    "B": "Wood",
    "C": "157,196,184"
  }
}
```

Color formats: hex `#RRGGBB`, named (case-insensitive, from palette), or `R,G,B`. Mapping must cover all labels returned by classify.

**Response 200**
```json
{ "png_base64": "iVBORw0K…", "width": 2752, "height": 320 }
```

### `GET /api/palette`

```json
{
  "presets": [
    {
      "id": "marie_wallin",
      "name": "Marie Wallin British Breeds",
      "colors": [
        { "name": "Walnut", "hex": "#693E4B" },
        "…"
      ]
    }
  ]
}
```

---

## Session strategy: **stateful, in-memory**

`/classify` creates a session storing `{ image_bytes, grid, ref_crops, created_at }`. `/colorize` looks it up by `session_id`. TTL: 1 hour idle eviction.

**Why stateful:** iterative re-colouring is a primary user flow. Forcing re-upload + re-classification on every tweak would be wasteful.

**Multi-user later:** swap the dict implementation in `session.py` for Redis. No API contract change.

---

## UI flow

```
UploadStep    POST /api/classify   → { session_id, crops, grid, csv }
                                      ▼
MappingStep   GET  /api/palette    → swatches
              user picks colour per crop
              "fill with Marie Wallin" button = one-click defaults
              POST /api/colorize    → { png_base64 }
                                      ▼
ResultStep    image + download (PNG, CSV)
              "tweak colours" → back to MappingStep (session still alive)
              "start over"    → new upload, old session TTL'd
```

---

## Design decisions (and why)

1. **Stateful sessions** — iterative recolouring is the primary flow; re-uploading on every tweak is wasteful.
2. **Base64 image responses** — simpler FE handling than binary; revisit if image sizes grow.
3. **Both `grid` and `csv` in classify response** — tiny payload, saves the FE a parse.
4. **One palette preset (Marie Wallin) for now** — structure allows more later with no contract change.
5. **No auth / no rate-limit / no persistence** — pure throwaway sessions. Multi-user later means Redis + auth middleware, none of which break this contract.
6. **CLI removed** — web app is the only interface. The old `knit.py` can be recovered from git if ever needed.
7. **Vite + React (not Next.js)** — FastAPI owns server logic; Next's SSR/API routes would be unused weight. Vite gives faster HMR + simpler mental model.

---

## Verify 1 (regression spot-checks)

Expected values for selected columns of `image.png` (1-based, rows 1–10):
image.png is 10 rows, 86 cols
See ./refs for each encoded pattern of A to N (each alphabet is a knitting pattern, ex: N represents a solid big circle)

| Col | Values |
|---|---|
| 1 | A A M A A M A A M M |
| 11 | C C C C C B B C C C |
| 12 | D E E E D D E E E E |
| 16 | F G G G F F G F G F |
| 31 | A A M A A A M M A A |
| 32 | A A M A A A M M A A |
| 34 | I H I H I H H H I I |
| 36 | I I I I I I I I I I |
| 37 | J J J J J J J B J J |
| 38 | B B B F B B B F B B |
| 41 | B K K B K K B B B K |
| 42 | F F B F B F F B F F |
| 51 | K K K K K K K K K K |
| 52 | K L L L K K K L K K |
| 62 | M N M N M N M M M N |
| 63 | B G B B B G G B G G |
| 84 | A A G G G A A A A A |
| 86 | J J J J J J J J J J |


## Verify 2 (regression spot-checks)

Expected values for selected columns of `test2.png` (1-based, cols 1–27):
test2.png is 74 rows, 27 cols
Below are encoded using `test2_classify_ans.png`, in this png you can find what does A to L represents,
ex: H is a solid big circle
Noticed that from row 25~55, a light gray watermark has been added

| Row | Values |
|---|---|
| 1 | G J J G G J J G G J J G G J J G G J J G G J J G G J J |
| 2 | G J J G G J J G G J J G G J J G G J J G G J J G G J J |
| 3 | A E A E A E A E A E A E A E A E A E A E A E A E A E A |
| 4 | E A E E E A E E E A E E E A E E E A E E E A E E E A E |
| 6 | B B B B B B B B B B B B B B B B B B B B B B B B B B B |
| 8 | D D B B B B B B B D D D B B B B B B B D D B D D B B B |
| 9 | I I B B B B B B B B I B B B B B B B B I I B I I B B B |
| 10 | C E E E C C C C E E E E E C C C C E E E C C C E E E C |
| 12 | H D D D D D H H H D D D H H H D D D D D H H H D D D D |
| 15 | I I B B B B B B B B I B B B B B B B B I I B I I B B B |
| 16 | D D B B B B B B B D D D B B B B B B B D D B D D B B B |
| 17 | D B B B B B B B B B D B B B B B B B B B D B D B B B B |
| 18 | B B B B B B B B B B B B B B B B B B B B B B B B B B B |
| 19 | K F K F K F K F K F K F K F K F K F K F K F K F K F K |
| 20 | F K F F F K F F F K F F F K F F F K F F F K F F F K F |
| 21 | K F K F K F K F K F K F K F K F K F K F K F K F K F K |
| 22 | A A A A A A A A A A A A A A A A A A A A A A A A A A A |
| 24 | G G G A G G G A G G G A G G G A G G G A G G G A G G G |
| 26 | C G G G C G C G G G C C C G G G C G C G G G C C C G G |
| 27 | E E G E G G G E G E E E E E G E G G G E G E E E E E G |
| 28 | E G E G G G G G E G E E E G E G G G G G E G E E E G E |
| 50 | F A F F F A F F F A F F F A F F F A F F F A F F F A F |
| 51 | A A A I A A A I A A A I A A A I A A A I A A A I A A A |
| 52 | J H J J J H J J J H J J J H J J J H J J J H J J J H J |
| 53 | A J A J A J A J A J A J A J A J A J A J A J A J A J A |
| 54 | J J J A J J J A J J J A J J J A J J J A J J J A J J J |
| 55 | J J J J J J J J J J J J J J J J J J J J J J J J J J J |
| 56 | Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q Q |
| 57 | K B K K K B K K K B K K K B K K K B K K K B K K K B K |
| 59 | B B B B B B B B B B B B B B B B B B B B B B B B B B B |
| 60 | C C C C C C C C C C C C C C C C C C C C C C C C C C C |
| 70 | E E E C E E E C E E E C E E E C E E E C E E E C E E E |
| 71 | C E C C C E C C C E C C C E C C C E C C C E C C C E C |
| 72 | D D D C D D D C D D D C D D D C D D D C D D D C D D D |

**Note on `Q` (row 56):** the `Q` glyph is pixel-identical to `K`'s U glyph (same shape, position, and color — verified by pixel diff). The Q/K distinction existed only as a yarn colour in the original coloured pattern, which the black-and-white chart does not encode, so no classifier can recover it. The chart physically contains the 11 legend symbols A–K; tests classify `test2.png` with `symbols=11` and expect row 56 to come back as `K`.

**Note:** Cluster labels A–N are assigned in K-means order, which is arbitrary. The web app handles this by surfacing the auto-extracted representative crops so the user can map them to colours by sight.

---

## Marie Wallin palette (built-in named colours)

| Name | RGB |
|---|---|
| Walnut | 105, 62, 75 |
| Wood | 139, 94, 60 |
| Pale Oak | 200, 168, 124 |
| Chestnut | 123, 63, 0 |
| Eau de Nil | 157, 196, 184 |
| Russet | 128, 70, 27 |
| Quince | 212, 165, 32 |
| Dark Apple | 61, 107, 61 |
| Lime Flower | 212, 224, 160 |
| Foxglove | 185, 131, 145 |
| Blossom | 240, 192, 184 |
| Rose | 208, 112, 128 |
| Silver Birch | 184, 180, 168 |
| Mallard | 44, 95, 107 |

Also accepts basic CSS names: `red`, `green`, `blue`, `white`, `black`, `gray`/`grey`, `yellow`, `orange`, `purple`, `pink`, `brown`, `teal`.
