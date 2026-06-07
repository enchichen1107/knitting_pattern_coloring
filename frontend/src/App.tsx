import { useState } from "react";
import UploadStep from "./components/UploadStep";
import MappingStep from "./components/MappingStep";
import ResultStep from "./components/ResultStep";
import LanguageToggle from "./components/LanguageToggle";
import { useT } from "./i18n/LanguageContext";
import type { ClassifyResponse, ColorizeResponse } from "./types";

type Step = "upload" | "map" | "result";

export default function App() {
  const { t } = useT();
  const [step, setStep] = useState<Step>("upload");
  const [classified, setClassified] = useState<ClassifyResponse | null>(null);
  const [colorized, setColorized] = useState<ColorizeResponse | null>(null);
  const [colors, setColors] = useState<Record<string, string>>({});

  function reset() {
    setClassified(null);
    setColorized(null);
    setColors({});
    setStep("upload");
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>{t("appTitle")}</h1>
        <LanguageToggle />
      </header>
      <div className="steps">
        <span className={`step ${step === "upload" ? "active" : ""}`}>
          {t("stepUpload")}
        </span>
        <span className={`step ${step === "map" ? "active" : ""}`}>
          {t("stepMap")}
        </span>
        <span className={`step ${step === "result" ? "active" : ""}`}>
          {t("stepResult")}
        </span>
      </div>

      {step === "upload" && (
        <UploadStep
          onClassified={(result) => {
            setClassified(result);
            setStep("map");
          }}
        />
      )}

      {step === "map" && classified && (
        <MappingStep
          classified={classified}
          initialColors={colors}
          onColorized={(result, picked) => {
            setColorized(result);
            setColors(picked);
            setStep("result");
          }}
          onBack={reset}
        />
      )}

      {step === "result" && classified && colorized && (
        <ResultStep
          classified={classified}
          colorized={colorized}
          onTweak={() => setStep("map")}
          onStartOver={reset}
        />
      )}
    </div>
  );
}
