export type Lang = "en" | "zh";

export const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "zh", label: "中" },
];

export const translations = {
  en: {
    appTitle: "Knitting Pattern Analyser",
    stepUpload: "1. Upload",
    stepMap: "2. Map colours",
    stepResult: "3. Result",

    uploadHeading: "Upload pattern",
    uploadFileLabel: "Pattern image (PNG / JPG)",
    uploadLegendLabel: "Legend image (optional)",
    uploadLegendHint:
      "Upload the symbol legend from the pattern for higher classification accuracy. Without a legend, K-means auto-clustering is used.",
    rows: "Rows",
    cols: "Columns",
    symbols: "Distinct symbols",
    classify: "Classify",
    classifying: "Classifying…",
    classifyHint:
      "Classification typically takes 30–60 s. The K-means step is CPU-heavy.",

    mapHeading: "Map each symbol to a colour",
    mapHint:
      "K-means assigns A–N in arbitrary order, so check the crops by eye. The Marie Wallin preset fills colours in palette order — adjust per crop.",
    fillPreset: "Fill with Marie Wallin",
    backToUpload: "← Back to upload",
    render: "Render coloured image",
    rendering: "Rendering…",

    resultHeading: "Result",
    downloadPng: "Download PNG",
    downloadCsv: "Download CSV",
    tweakColours: "← Tweak colours",
    startOver: "Start over",
  },
  zh: {
    appTitle: "編織圖片分析器",
    stepUpload: "1. 上傳",
    stepMap: "2. 配色",
    stepResult: "3. 結果",

    uploadHeading: "上傳圖片",
    uploadFileLabel: "圖片檔案（PNG / JPG）",
    uploadLegendLabel: "符號對照表(選填)",
    uploadLegendHint:
      "上傳圖片的符號對照表可提升分類準確度。未提供時將使用 K-means 自動分群。",
    rows: "列數",
    cols: "欄數",
    symbols: "符號種類數",
    classify: "開始分析",
    classifying: "分析中…",
    classifyHint:
      "分析通常需要 30–60 秒,K-means 分群會消耗較多 CPU。",

    mapHeading: "為每個符號指定顏色",
    mapHint:
      "K-means 以隨機順序標記 A–N,請依縮圖判斷對應符號。「套用 Marie Wallin」會依調色盤順序填入顏色,可再依需要個別調整。",
    fillPreset: "套用 Marie Wallin",
    backToUpload: "← 重新上傳",
    render: "產生彩色圖片",
    rendering: "渲染中…",

    resultHeading: "結果",
    downloadPng: "下載 PNG",
    downloadCsv: "下載 CSV",
    tweakColours: "← 調整顏色",
    startOver: "重新開始",
  },
} as const;

export type TranslationKey = keyof (typeof translations)["en"];
