from __future__ import annotations

from fastapi import APIRouter

from app import palette as palette_module
from app.schemas import PaletteColor, PalettePreset, PaletteResponse

router = APIRouter()


@router.get("/palette", response_model=PaletteResponse)
def get_palette() -> PaletteResponse:
    return PaletteResponse(
        presets=[
            PalettePreset(
                id="marie_wallin",
                name="Marie Wallin British Breeds",
                colors=[
                    PaletteColor(name=c["name"], hex=c["hex"])
                    for c in palette_module.marie_wallin_preset()
                ],
            ),
        ],
    )
