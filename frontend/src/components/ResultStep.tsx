import { useT } from "../i18n/LanguageContext";
import type { ClassifyResponse, ColorizeResponse } from "../types";

interface Props {
  classified: ClassifyResponse;
  colorized: ColorizeResponse;
  onTweak: () => void;
  onStartOver: () => void;
}

function downloadBase64Png(b64: string, filename: string) {
  const link = document.createElement("a");
  link.href = `data:image/png;base64,${b64}`;
  link.download = filename;
  link.click();
}

function downloadText(text: string, filename: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function ResultStep({
  classified,
  colorized,
  onTweak,
  onStartOver,
}: Props) {
  const { t } = useT();
  return (
    <div className="card">
      <h2>{t("resultHeading")}</h2>
      <img
        className="result-image"
        src={`data:image/png;base64,${colorized.png_base64}`}
        alt={t("resultHeading")}
      />
      <p className="muted">
        {colorized.width} × {colorized.height} px
      </p>
      <div className="toolbar">
        <button onClick={() => downloadBase64Png(colorized.png_base64, "colored_pattern.png")}>
          {t("downloadPng")}
        </button>
        <button
          className="secondary"
          onClick={() => downloadText(classified.csv, "pattern.csv", "text/csv")}
        >
          {t("downloadCsv")}
        </button>
        <button className="secondary" onClick={onTweak}>
          {t("tweakColours")}
        </button>
        <button className="secondary" onClick={onStartOver}>
          {t("startOver")}
        </button>
      </div>
    </div>
  );
}
