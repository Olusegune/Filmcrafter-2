/** The sums behind comparing two takes side by side: one clock for both videos, one frame at a time, and the facts that differ. Pure, so it can be tested without a video. */
import type { Version } from "./api";

export const FRAME_FPS = 24;                    // a step is one frame of a typical 24 fps take
export const DRIFT_TOLERANCE = 0.12;            // seconds the two videos may disagree before the follower is pulled back
export const RATES = [0.25, 0.5, 1, 2] as const;

export const clampTime = (t: number, dur: number): number => (Number.isFinite(t) ? Math.max(0, Math.min(dur > 0 ? dur : 0, t)) : 0);

/** One frame forward (dir 1) or back (dir -1) from `t`, kept inside the clip. */
export const stepTime = (t: number, dir: 1 | -1, dur: number, fps: number = FRAME_FPS): number => clampTime(t + dir / (fps > 0 ? fps : FRAME_FPS), dur);

/** Whether the follower has drifted far enough from the clock that it should be moved. A clip that has already ended is left where it is. */
export const needsResync = (clock: number, follower: number, followerDur: number, tol: number = DRIFT_TOLERANCE): boolean =>
  Math.abs(Math.min(clock, followerDur) - follower) > tol;

/** Where the clock goes when it reaches the end of the longer clip: back to the start when looping, else it stays on the last frame. */
export const atEnd = (t: number, dur: number): boolean => dur > 0 && t >= dur - 0.02;

export function fmtClock(t: number): string {
  const s = Math.max(0, t);
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}.${String(Math.floor((s % 1) * 100)).padStart(2, "0")}`;
}

export type Fact = { label: string; a: string; b: string; differs: boolean; note?: string };

const modelName = (m: string) => m.split("/").slice(-2).join("/");
const secs = (n: number | null) => (n == null || !Number.isFinite(n) ? "…" : `${Math.round(n * 100) / 100} s`);
const cost = (v: Version) => (v.cost == null ? "not known" : `${v.cost} ${v.cost_unit === "credits" ? "credits" : "USD"}`);

/** What differs between two takes: model, length, price. Each row says whether the two sides disagree, and the price row says which was cheaper when both are in the same unit. */
export function compareFacts(a: Version, b: Version, lenA: number | null, lenB: number | null): Fact[] {
  const rows: Fact[] = [
    { label: "Model", a: `${a.provider}: ${modelName(a.model)}`, b: `${b.provider}: ${modelName(b.model)}`, differs: a.provider !== b.provider || a.model !== b.model },
    { label: "Length", a: secs(lenA), b: secs(lenB), differs: lenA != null && lenB != null && Math.abs(lenA - lenB) > 0.05 },
  ];
  const price: Fact = { label: "Price", a: cost(a), b: cost(b), differs: a.cost !== b.cost || a.cost_unit !== b.cost_unit };
  if (a.cost != null && b.cost != null && a.cost_unit === b.cost_unit && a.cost !== b.cost) price.note = a.cost < b.cost ? "Left cost less" : "Right cost less";
  rows.push(price);
  return rows;
}
