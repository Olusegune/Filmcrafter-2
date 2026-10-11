/** The export formats, one per shape a film's frame can take (the engine's export.PRESETS, with the same ids). The film's own shape is offered first and chosen for you. */
export type ExportFormat = { id: string; label: string; sub: string; ar: number };

export const EXPORT_FORMATS: ExportFormat[] = [
  { id: "youtube", label: "YouTube", sub: "16:9 · 1920×1080", ar: 16 / 9 },
  { id: "widescreen", label: "Ultra-wide", sub: "21:9 · 2520×1080", ar: 21 / 9 },
  { id: "cinema", label: "Cinema", sub: "2.39:1 · 1920×804", ar: 2.39 },
  { id: "standard", label: "Classic", sub: "4:3 · 1440×1080", ar: 4 / 3 },
  { id: "square", label: "Square", sub: "1:1 · 1080×1080", ar: 1 },
  { id: "portrait", label: "Portrait", sub: "4:5 · 1080×1350", ar: 4 / 5 },
  { id: "tall", label: "Tall portrait", sub: "3:4 · 1080×1440", ar: 3 / 4 },
  { id: "vertical", label: "TikTok / Reels", sub: "9:16 · 1080×1920", ar: 9 / 16 },
  { id: "ultratall", label: "Ultra-tall", sub: "9:21 · 1080×2520", ar: 9 / 21 },
];

/** Which format matches a film's frame shape (YouTube when it is not one of them). */
const BY_ASPECT: Record<string, string> = { "16:9": "youtube", "21:9": "widescreen", "2.39:1": "cinema", "4:3": "standard", "1:1": "square", "4:5": "portrait", "3:4": "tall", "9:16": "vertical", "9:21": "ultratall" };
export const formatFor = (aspect?: string | null): string => BY_ASPECT[aspect ?? ""] ?? "youtube";
