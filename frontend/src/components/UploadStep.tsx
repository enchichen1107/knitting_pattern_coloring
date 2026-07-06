import { useState, type FormEvent } from "react";
import { classify } from "../api/client";
import { useT } from "../i18n/LanguageContext";
import type { ClassifyResponse } from "../types";

interface Props {
  onClassified: (result: ClassifyResponse) => void;
}

export default function UploadStep({ onClassified }: Props) {
  const { t } = useT();
  const [image, setImage] = useState<File | null>(null);
  const [legend, setLegend] = useState<File | null>(null);
  const [rows, setRows] = useState(10);
  const [cols, setCols] = useState(86);
  const [symbols, setSymbols] = useState(14);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!image) return;
    setBusy(true);
    setError(null);
    try {
      const result = await classify(image, rows, cols, symbols, legend);
      onClassified(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{t("uploadHeading")}</h2>
      <form onSubmit={handleSubmit}>
        <label>
          <span className="label-text">{t("uploadFileLabel")}</span>
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => setImage(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <label>
          <span className="label-text">{t("uploadLegendLabel")}</span>
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => setLegend(e.target.files?.[0] ?? null)}
          />
          <p className="muted" style={{ fontSize: "0.8rem", marginTop: "0.25rem" }}>
            {t("uploadLegendHint")}
          </p>
        </label>
        <div className="row">
          <label>
            <span className="label-text">{t("rows")}</span>
            <input type="number" min={1} value={rows}
              onChange={(e) => setRows(parseInt(e.target.value || "0", 10))} />
          </label>
          <label>
            <span className="label-text">{t("cols")}</span>
            <input type="number" min={1} value={cols}
              onChange={(e) => setCols(parseInt(e.target.value || "0", 10))} />
          </label>
          <label>
            <span className="label-text">{t("symbols")}</span>
            <input type="number" min={2} max={26} value={symbols}
              onChange={(e) => setSymbols(parseInt(e.target.value || "0", 10))} />
          </label>
        </div>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy || !image}>
          {busy ? t("classifying") : t("classify")}
        </button>
        <p className="muted" style={{ marginTop: "1rem" }}>
          {t("classifyHint")}
        </p>
      </form>
    </div>
  );
}
