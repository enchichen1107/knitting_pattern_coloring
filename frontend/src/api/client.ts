import type {
  ClassifyResponse,
  ColorizeResponse,
  PaletteResponse,
} from "../types";

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function classify(
  image: File,
  rows: number,
  cols: number,
  symbols: number,
  legend?: File | null,
): Promise<ClassifyResponse> {
  const form = new FormData();
  form.append("image", image);
  form.append("rows", String(rows));
  form.append("cols", String(cols));
  form.append("symbols", String(symbols));
  if (legend) form.append("legend", legend);
  const res = await fetch("/api/classify", { method: "POST", body: form });
  return unwrap<ClassifyResponse>(res);
}

export async function colorize(
  sessionId: string,
  colors: Record<string, string>,
): Promise<ColorizeResponse> {
  const res = await fetch("/api/colorize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, colors }),
  });
  return unwrap<ColorizeResponse>(res);
}

export async function getPalette(): Promise<PaletteResponse> {
  const res = await fetch("/api/palette");
  return unwrap<PaletteResponse>(res);
}
