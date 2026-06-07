export interface RefCrop {
  label: string;
  png_base64: string;
}

export interface ClassifyResponse {
  session_id: string;
  rows: number;
  cols: number;
  symbols: number;
  labels: string[];
  grid: string[][];
  csv: string;
  crops: RefCrop[];
}

export interface ColorizeResponse {
  png_base64: string;
  width: number;
  height: number;
}

export interface PaletteColor {
  name: string;
  hex: string;
}

export interface PalettePreset {
  id: string;
  name: string;
  colors: PaletteColor[];
}

export interface PaletteResponse {
  presets: PalettePreset[];
}
