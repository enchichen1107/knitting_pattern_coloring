"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefCropOut(BaseModel):
    label: str
    png_base64: str


class ClassifyResponse(BaseModel):
    session_id: str
    rows: int
    cols: int
    symbols: int
    labels: list[str]
    grid: list[list[str]]
    csv: str
    crops: list[RefCropOut]


class ColorizeRequest(BaseModel):
    session_id: str
    colors: dict[str, str] = Field(
        ...,
        description="Map label → colour string (hex / R,G,B / named).",
    )


class ColorizeResponse(BaseModel):
    png_base64: str
    width: int
    height: int


class PaletteColor(BaseModel):
    name: str
    hex: str


class PalettePreset(BaseModel):
    id: str
    name: str
    colors: list[PaletteColor]


class PaletteResponse(BaseModel):
    presets: list[PalettePreset]
