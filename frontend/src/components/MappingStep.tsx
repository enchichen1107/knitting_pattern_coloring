import { useEffect, useState } from "react";
import { colorize, getPalette } from "../api/client";
import { useT } from "../i18n/LanguageContext";
import type {
  ClassifyResponse,
  ColorizeResponse,
  PaletteColor,
} from "../types";
import CropTile from "./CropTile";

interface Props {
  classified: ClassifyResponse;
  initialColors?: Record<string, string>;
  onColorized: (
    result: ColorizeResponse,
    colors: Record<string, string>,
  ) => void;
  onBack: () => void;
}

const DEFAULT_HEX = "#888888";

export default function MappingStep({
  classified,
  initialColors,
  onColorized,
  onBack,
}: Props) {
  const { t } = useT();
  const [palette, setPalette] = useState<PaletteColor[]>([]);
  const [colors, setColors] = useState<Record<string, string>>(
    initialColors ?? Object.fromEntries(
      classified.labels.map((l) => [l, DEFAULT_HEX]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPalette()
      .then((p) => setPalette(p.presets[0]?.colors ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  function setColor(label: string, hex: string) {
    setColors((prev) => ({ ...prev, [label]: hex }));
  }

  function applyMarieWallinPreset() {
    if (palette.length === 0) return;
    const next: Record<string, string> = {};
    classified.labels.forEach((label, i) => {
      const swatch = palette[i % palette.length];
      next[label] = swatch.hex;
    });
    setColors(next);
  }

  async function handleColorize() {
    setBusy(true);
    setError(null);
    try {
      const result = await colorize(classified.session_id, colors);
      onColorized(result, colors);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{t("mapHeading")}</h2>
      <p className="muted">{t("mapHint")}</p>
      <div className="toolbar">
        <button
          type="button"
          className="secondary"
          onClick={applyMarieWallinPreset}
          disabled={palette.length === 0}
        >
          {t("fillPreset")}
        </button>
        <button type="button" className="secondary" onClick={onBack}>
          {t("backToUpload")}
        </button>
      </div>
      <div className="crop-grid">
        {classified.crops.map((crop) => (
          <CropTile
            key={crop.label}
            crop={crop}
            color={colors[crop.label] ?? DEFAULT_HEX}
            onChange={(hex) => setColor(crop.label, hex)}
          />
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      <button onClick={handleColorize} disabled={busy}>
        {busy ? t("rendering") : t("render")}
      </button>
    </div>
  );
}
