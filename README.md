# Knitting Pattern Analyser

Web app that turns a knitting-chart image into a CSV plus a coloured rendering. Upload an image, declare grid dimensions, map each detected symbol to a colour, download the result.

See [CLAUDE.md](./CLAUDE.md) for architecture and API contract.

## Run locally

### Backend (FastAPI, port 8000)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Frontend (Vite, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The frontend proxies `/api/*` to the backend.

## Test

```bash
cd backend && .venv/bin/pytest
```

The regression test classifies `image.png` and checks structural spot-checks from CLAUDE.md.
