import { api } from "./api";
import type { Manifest } from "./api";

export const ASPECTS: [string, string][] = [
  ["2.39:1", "Cinema scope"], ["21:9", "Ultra-wide"], ["16:9", "Widescreen · YouTube"], ["4:3", "Classic"],
  ["1:1", "Square"], ["4:5", "Portrait feed"], ["3:4", "Tall portrait"], ["9:16", "Vertical · TikTok, Reels"], ["9:21", "Ultra-tall"],
];
export const QUALITY: [string, string][] = [
  ["draft", "Draft · fastest, cheapest"], ["standard", "Standard · 720p"], ["high", "High · 1080p"], ["max", "Max · best the model offers"],
];

/** '21:9' or '2.39:1' as a number (16:9 when it can't be read). */
export const ratioOf = (a?: string | null): number => {
  const m = String(a ?? "").match(/^\s*([\d.]+)\s*:\s*([\d.]+)\s*$/);
  const r = m ? parseFloat(m[1]) / parseFloat(m[2]) : NaN;
  return Number.isFinite(r) && r > 0 ? r : 16 / 9;
};

/** CSS aspect-ratio for a project shape. */
export const aspectCss = (a?: string | null): string => { const m = String(a ?? "").match(/^([\d.]+):([\d.]+)$/); return m ? `${m[1]} / ${m[2]}` : "16 / 9"; };

export const PROJECT_EVENT = "pf-project-settings";

/** Save an aspect or quality choice for the whole project and tell every open panel. */
export async function saveFrame(dir: string, key: "aspect_ratio" | "quality", value: string): Promise<void> {
  await api.setProjectSettings(dir, { [key]: value });
  window.dispatchEvent(new CustomEvent(PROJECT_EVENT, { detail: { [key]: value } }));
}

const PRESET = /(\d+)_(\d+)$/;

/** The shape a request will really ask the model for, read from what would be sent: {label, ratio}, or null when the model chooses. */
export function sentShape(manifest: Manifest | null, payload: Record<string, unknown>): { label: string; ratio: number } | null {
  if (!manifest) return null;
  const role = manifest.roles?.aspect_ratio;
  const ar = role ? payload[role] : undefined;
  if (typeof ar === "string" && /^\d+(\.\d+)?:\d+(\.\d+)?$/.test(ar)) return { label: ar, ratio: ratioOf(ar) };
  const size = payload["size"];
  const wh = typeof size === "string" ? size.match(/^(\d+)x(\d+)$/) : null;
  if (wh) return { label: `${wh[1]}×${wh[2]}`, ratio: parseInt(wh[1]) / parseInt(wh[2]) };
  const preset = payload["image_size"];
  if (typeof preset === "string") {
    if (preset.startsWith("square")) return { label: "1:1", ratio: 1 };
    const m = preset.match(PRESET);
    if (m) {
      const portrait = preset.startsWith("portrait");
      const r = parseInt(m[1]) / parseInt(m[2]);
      return { label: portrait ? `${m[2]}:${m[1]}` : `${m[1]}:${m[2]}`, ratio: portrait ? 1 / r : r };
    }
  }
  return null;
}

/** True when what the model will make is noticeably another shape than the project's. */
export const shapeDiffers = (shape: { ratio: number } | null, frame: string): boolean => !!shape && Math.abs(shape.ratio - ratioOf(frame)) / ratioOf(frame) > 0.03;
