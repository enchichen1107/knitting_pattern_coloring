from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import core
from app.schemas import ClassifyResponse, RefCropOut
from app.session import Session, store

router = APIRouter()

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    image: UploadFile = File(...),
    rows: int = Form(...),
    cols: int = Form(...),
    symbols: int = Form(...),
) -> ClassifyResponse:
    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload")

    try:
        result = core.classify_image(image_bytes, rows=rows, cols=cols, symbols=symbols)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = store.create(Session(
        image_bytes=result.image_bytes,
        rows=result.rows,
        cols=result.cols,
        symbols=result.symbols,
        labels=result.labels,
        grid=result.grid,
    ))

    return ClassifyResponse(
        session_id=session_id,
        rows=result.rows,
        cols=result.cols,
        symbols=result.symbols,
        labels=result.labels,
        grid=result.grid,
        csv=core.grid_to_csv(result.grid),
        crops=[
            RefCropOut(label=c.label, png_base64=core.png_to_base64(c.png_bytes))
            for c in result.crops
        ],
    )
