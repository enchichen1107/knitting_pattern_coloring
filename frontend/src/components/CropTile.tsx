import type { RefCrop } from "../types";

interface Props {
  crop: RefCrop;
  color: string;          // hex (#RRGGBB) currently selected
  onChange: (hex: string) => void;
}

function isHex(s: string): boolean {
  return /^#[0-9A-Fa-f]{6}$/.test(s);
}

export default function CropTile({ crop, color, onChange }: Props) {
  const swatchValue = isHex(color) ? color : "#888888";

  return (
    <div className="crop-tile">
      <div className="label-text">{crop.label}</div>
      <img
        src={`data:image/png;base64,${crop.png_base64}`}
        alt={`Symbol ${crop.label}`}
      />
      <label className="color-picker" style={{ background: swatchValue }}>
        <input
          type="color"
          value={swatchValue}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
        />
      </label>
      <div className="hex-readout">{swatchValue.toUpperCase()}</div>
    </div>
  );
}
