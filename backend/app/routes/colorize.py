from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import core, palette
from app.schemas import ColorizeRequest, ColorizeResponse
from app.session import store

router = APIRouter()


@router.post("/colorize", response_model=ColorizeResponse)
def colorize(req: ColorizeRequest) -> ColorizeResponse:
    session = store.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown or expired session")

    missing = [lbl for lbl in session.labels if lbl not in req.colors]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Colour mapping missing labels: {', '.join(missing)}",
        )

    try:
        colors_rgb = {
            lbl: palette.parse_color(val) for lbl, val in req.colors.items()
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    png_bytes, width, height = core.colorize_image(
        session.image_bytes, session.grid, colors_rgb,
    )
    return ColorizeResponse(
        png_base64=core.png_to_base64(png_bytes),
        width=width,
        height=height,
    )
