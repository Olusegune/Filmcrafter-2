/** The arithmetic of the Home screen's director's board: an orbit that the cameras ride, the storyboard frames around the words, and the timeline along the bottom. Pure functions, so they can be tested. */
export type Pt = { x: number; y: number };
export type Rect = { x: number; y: number; w: number; h: number };
export type Orbit = { cx: number; cy: number; rx: number; ry: number; rot: number };

/** The orbit: a wide, slightly tilted ellipse around the middle of the box. */
export const orbitFor = (w: number, h: number): Orbit => ({ cx: w / 2, cy: h * 0.5, rx: w * 0.4, ry: h * 0.34, rot: (-7 * Math.PI) / 180 });

/** A point on the orbit at angle t (radians), and the way a camera travelling anticlockwise there is heading. */
export function onOrbit(o: Orbit, t: number): Pt & { heading: number } {
  const ex = o.rx * Math.cos(t), ey = o.ry * Math.sin(t);
  const c = Math.cos(o.rot), s = Math.sin(o.rot);
  const dx = -o.rx * Math.sin(t), dy = o.ry * Math.cos(t);
  return { x: o.cx + ex * c - ey * s, y: o.cy + ex * s + ey * c, heading: Math.atan2(dx * s + dy * c, dx * c - dy * s) };
}

/** How far a camera's cone reaches: far enough to take in a frame, short of the words in the middle. */
export const coneLength = (w: number, h: number): number => Math.min(w, h) * 0.38;

/** The angle from a to b. */
export const aimAt = (from: Pt, to: Pt): number => Math.atan2(to.y - from.y, to.x - from.x);

/** The storyboard frames: four, kept away from the middle column where the words are. Each has a label. */
export function framesFor(w: number, h: number): (Rect & { label: string; scene: "coast" | "arch" | "city" | "platform" })[] {
  const fw = Math.max(96, Math.min(200, w * 0.16)), fh = fw * 0.62;
  return [
    { x: w - fw - w * 0.05, y: h * 0.1, w: fw, h: fh, label: "SC. 03", scene: "coast" },
    { x: w * 0.045, y: h - fh - h * 0.12, w: fw, h: fh, label: "SC. 01", scene: "arch" },
    { x: w - fw * 1.08 - w * 0.04, y: h - fh - h * 0.1, w: fw * 1.08, h: fh * 1.08, label: "SC. 02", scene: "city" },
    { x: w * 0.17, y: h * 0.27, w: fw * 0.72, h: fh * 0.72, label: "SC. 04", scene: "platform" },
  ];
}

/** The timeline along the bottom: where it starts and ends, and the playhead's place at time t seconds (it loops every `period` seconds). */
export function timelineFor(w: number, h: number): { x0: number; x1: number; y: number } { return { x0: w * 0.2, x1: w * 0.8, y: h * 0.9 }; }
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
