/** The arithmetic of the Home screen's director's board: an orbit that the cameras ride, the storyboard frames around the words, and the timeline along the bottom. Pure functions, so they can be tested. */
export type Pt = { x: number; y: number };
export type Rect = { x: number; y: number; w: number; h: number };
export type Orbit = { cx: number; cy: number; rx: number; ry: number; rot: number };

/** The orbit: a wide, slightly tilted ellipse around the middle of the box. */
export const orbitFor = (w: number, h: number): Orbit => ({ cx: w / 2, cy: h * 0.5, rx: w * 0.34, ry: h * 0.29, rot: (-6 * Math.PI) / 180 });

/** A point on the orbit at angle t (radians), and the way a camera travelling anticlockwise there is heading. */
export function onOrbit(o: Orbit, t: number): Pt & { heading: number } {
  const ex = o.rx * Math.cos(t), ey = o.ry * Math.sin(t);
  const c = Math.cos(o.rot), s = Math.sin(o.rot);
  const dx = -o.rx * Math.sin(t), dy = o.ry * Math.cos(t);
  return { x: o.cx + ex * c - ey * s, y: o.cy + ex * s + ey * c, heading: Math.atan2(dx * s + dy * c, dx * c - dy * s) };
}

/** How far a camera's cone reaches: far enough to take in a frame, short of the words in the middle. */
export const coneLength = (w: number, h: number): number => Math.min(w, h) * 0.34;

/** The angle from a to b. */
export const aimAt = (from: Pt, to: Pt): number => Math.atan2(to.y - from.y, to.x - from.x);

/** The storyboard frames: four, each in a different shape (square, ultra-wide, vertical, widescreen), kept away from the middle column where the words are. Each has a label and its ratio. */
export type BoardFrame = Rect & { label: string; ratio: string; scene: "coast" | "arch" | "city" | "platform" };
export function framesFor(w: number, h: number): BoardFrame[] {
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  const h0 = clamp(h * 0.27, 56, 104);
  const sq = h0 * 0.78;
  const w3 = clamp(w * 0.2, 112, 210), h3 = (w3 * 9) / 21;
  const h1 = h0 * 1.4, w1 = (h1 * 9) / 16;
  const w2 = clamp(w * 0.17, 100, 180), h2 = (w2 * 9) / 16;
  return [
    { x: w * 0.065, y: h * 0.17, w: sq, h: sq, label: "SC. 04", ratio: "1:1", scene: "platform" },
    { x: w - w3 - w * 0.05, y: h * 0.14, w: w3, h: h3, label: "SC. 03", ratio: "21:9", scene: "coast" },
    { x: w * 0.05, y: h - h1 - h * 0.1, w: w1, h: h1, label: "SC. 01", ratio: "9:16", scene: "arch" },
    { x: w - w2 - w * 0.06, y: h - h2 - h * 0.1, w: w2, h: h2, label: "SC. 02", ratio: "16:9", scene: "city" },
  ];
}

/** The timeline along the bottom: where it starts and ends, and the playhead's place at time t seconds (it loops every `period` seconds). */
export function timelineFor(w: number, h: number): { x0: number; x1: number; y: number } { return { x0: w * 0.27, x1: w * 0.73, y: h * 0.9 }; }
export const playhead = (tl: { x0: number; x1: number }, t: number, period = 14): number => tl.x0 + (tl.x1 - tl.x0) * (((t % period) + period) % period) / period;

/** Whether a camera's cone (centred on `aim`, `fov` wide) takes in a point. */
export const sees = (cam: Pt, aim: number, fov: number, p: Pt): boolean => {
  let d = (aimAt(cam, p) - aim) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return Math.abs(d) <= fov / 2;
};

/** A small deterministic random generator (the same board every time). */
export function seeded(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

/** The shortest signed turn from angle a to angle b, in radians. */
export const turnBetween = (a: number, b: number): number => { let d = (b - a) % (Math.PI * 2); if (d > Math.PI) d -= Math.PI * 2; if (d < -Math.PI) d += Math.PI * 2; return d; };

/** Turn `cur` toward `target` by a fraction k of the shortest way round (a camera that swings smoothly). */
export const turnToward = (cur: number, target: number, k: number): number => cur + turnBetween(cur, target) * Math.min(1, Math.max(0, k));

/** Where a camera should look: at the nearest frame that is within reach (so it glances at each as it passes), otherwise at the middle of the room. */
export function lookTarget(cam: Pt, frames: Rect[], reach: number, middle: Pt): Pt {
  let best: Pt | null = null, bestD = reach;
  for (const f of frames) {
    const mid = { x: f.x + f.w / 2, y: f.y + f.h / 2 };
    const d = Math.hypot(mid.x - cam.x, mid.y - cam.y);
    if (d < bestD) { best = mid; bestD = d; }
  }
  return best ?? middle;
}
