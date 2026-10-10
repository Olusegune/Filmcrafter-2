/** The arithmetic of the Home screen's car chase: a looping road, cars that travel along it, and cameras that follow with a little lag. Pure functions, so they can be tested. */
export type Pt = { x: number; y: number };
export type Track = { pts: Pt[]; cum: number[]; total: number };
export type Pose = Pt & { angle: number };

/** A closed road that runs around the edge of a w by h box (a rounded rectangle with a few gentle bends), leaving the middle clear for the words. n points around it. */
export function makeTrack(w: number, h: number, n = 480): Track {
  const A = w * 0.44, B = h * 0.38, p = 0.55;
  const sg = (v: number) => (v < 0 ? -1 : 1);
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2;
    const bend = 1 + 0.07 * Math.sin(3 * t) + 0.04 * Math.sin(5 * t + 1);
    const c = Math.cos(t), s = Math.sin(t);
    pts.push({ x: w / 2 + A * bend * sg(c) * Math.pow(Math.abs(c), p), y: h / 2 + B * bend * sg(s) * Math.pow(Math.abs(s), p) });
  }
  const cum = [0];
  for (let i = 1; i <= n; i++) {
    const a = pts[i - 1], b = pts[i % n];
    cum.push(cum[i - 1] + Math.hypot(b.x - a.x, b.y - a.y));
  }
  return { pts, cum, total: cum[n] };
}

/** The point and heading at a distance along the road (the road loops, so any distance works, including a negative one). */
export function at(track: Track, dist: number): Pose {
  const n = track.pts.length;
  const d = ((dist % track.total) + track.total) % track.total;
  let lo = 0, hi = n;
  while (lo < hi - 1) { const mid = (lo + hi) >> 1; if (track.cum[mid] <= d) lo = mid; else hi = mid; }
  const a = track.pts[lo], b = track.pts[(lo + 1) % n];
  const span = track.cum[lo + 1] - track.cum[lo] || 1;
  const f = (d - track.cum[lo]) / span;
  return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, angle: Math.atan2(b.y - a.y, b.x - a.x) };
}

/** A point `side` to the left (positive) or right (negative) of a pose, as seen travelling along it. */
export const beside = (p: Pose, side: number, ahead = 0): Pt => ({
  x: p.x + Math.cos(p.angle) * ahead - Math.sin(p.angle) * side,
  y: p.y + Math.sin(p.angle) * ahead + Math.cos(p.angle) * side,
});

/** Move `cur` toward `target` by a fraction k of the gap (a camera that follows a little behind). */
export const follow = (cur: Pt, target: Pt, k: number): Pt => ({ x: cur.x + (target.x - cur.x) * k, y: cur.y + (target.y - cur.y) * k });

/** The shortest signed turn from angle a to angle b, in radians. */
export const turnBetween = (a: number, b: number): number => { let d = (b - a) % (Math.PI * 2); if (d > Math.PI) d -= Math.PI * 2; if (d < -Math.PI) d += Math.PI * 2; return d; };

/** Turn `cur` toward `target` by a fraction k of the shortest way round. */
export const turnToward = (cur: number, target: number, k: number): number => cur + turnBetween(cur, target) * k;

/** A small deterministic random generator (the same city every time). */
export function seeded(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
