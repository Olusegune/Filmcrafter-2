import { getCurrentWebview } from "@tauri-apps/api/webview";
import { currentMonitor } from "@tauri-apps/api/window";

/** Interface size: the whole app scales like browser zoom, so large and 4K screens (TVs) read at a normal size. */
export const UI_SCALES: { id: string; label: string }[] = [
  { id: "1", label: "100% (recommended)" }, { id: "auto", label: "Automatic (only very large screens)" }, { id: "0.9", label: "90%" }, { id: "1.25", label: "125%" },
  { id: "1.5", label: "150%" }, { id: "1.75", label: "175%" }, { id: "2", label: "200%" }, { id: "2.5", label: "250%" },
];

/** Only very large desktops (2880+ logical pixels wide) get scaled up, in quarter steps. */
export async function autoScale(): Promise<number> {
  // the monitor's real size in logical pixels (physical ÷ Windows scaling); the page's own screen size changes with the zoom
  let w = window.screen.width;
  try { const m = await currentMonitor(); if (m) w = m.size.width / m.scaleFactor; } catch { /* browser preview */ }
  if (w < 2880) return 1;   // up to 1440p-class desktops (and TVs at Windows scaling) look best at 100%
  return Math.min(2, Math.max(1, Math.round((w / 1920) * 4) / 4));
}

export function savedScale(): string {
  try { return localStorage.getItem("pf-ui-scale") || "1"; } catch { return "1"; }
}

export async function applyScale(choice = savedScale()): Promise<number> {
  const s = choice === "auto" ? await autoScale() : Number(choice) || 1;
  try { await getCurrentWebview().setZoom(s); } catch { /* browser preview: ignore */ }
  return s;
}

export async function setScale(choice: string): Promise<number> {
  try { localStorage.setItem("pf-ui-scale", choice); } catch { /* optional */ }
  return applyScale(choice);
}
