/** The arithmetic of the blocking floor plan. The room is a box W wide and H deep; x runs right and y runs down the page. A facing or an aim is a compass angle: 0 right, 90 down, 180 left, 270 up. */
export const ROOM = { w: 100, h: 70 };
export type Pt = { x: number; y: number };

export const clampRoom = (p: Pt, margin = 1.5): Pt => ({ x: Math.max(margin, Math.min(ROOM.w - margin, p.x)), y: Math.max(margin, Math.min(ROOM.h - margin, p.y)) });
export const round1 = (n: number) => Math.round(n * 10) / 10;
const rad = (d: number) => (d * Math.PI) / 180;
export const norm360 = (d: number) => ((d % 360) + 360) % 360;

/** The angle, in degrees, from a to b. */
export const bearing = (a: Pt, b: Pt): number => norm360((Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI);

/** A point `dist` away from p in the direction `deg`. */
export const along = (p: Pt, deg: number, dist: number): Pt => ({ x: p.x + Math.cos(rad(deg)) * dist, y: p.y + Math.sin(rad(deg)) * dist });

/** The two far corners of a camera's cone of view (for a triangle drawn from the camera). */
export const coneEdges = (cam: Pt, aim: number, fov: number, len: number): [Pt, Pt] => [along(cam, aim - fov / 2, len), along(cam, aim + fov / 2, len)];

/** Where a line through a and b meets the walls of the room (to draw the line of action edge to edge); null when a and b are the same point. */
export function lineThrough(a: Pt, b: Pt): [Pt, Pt] | null {
  const dx = b.x - a.x, dy = b.y - a.y;
  if (Math.hypot(dx, dy) < 1e-6) return null;
  const hits: Pt[] = [];
  const test = (t: number) => { const p = { x: a.x + dx * t, y: a.y + dy * t }; if (p.x >= -1e-6 && p.x <= ROOM.w + 1e-6 && p.y >= -1e-6 && p.y <= ROOM.h + 1e-6) hits.push(p); };
  if (Math.abs(dx) > 1e-9) { test((0 - a.x) / dx); test((ROOM.w - a.x) / dx); }
  if (Math.abs(dy) > 1e-9) { test((0 - a.y) / dy); test((ROOM.h - a.y) / dy); }
  if (hits.length < 2) return null;
  hits.sort((p, q) => p.x - q.x || p.y - q.y);
  return [hits[0], hits[hits.length - 1]];
}

/** Which side of the line from a to b the point is on: 1, -1, or 0 on the line (the same rule as the engine). */
export const sideOf = (p: Pt, a: Pt, b: Pt): number => { const v = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x); return v > 1e-6 ? 1 : v < -1e-6 ? -1 : 0; };

/** A pointer position inside an SVG's box (in pixels) as a point in the room. */
export const toRoom = (clientX: number, clientY: number, box: { left: number; top: number; width: number; height: number }): Pt =>
  clampRoom({ x: round1(((clientX - box.left) / box.width) * ROOM.w), y: round1(((clientY - box.top) / box.height) * ROOM.h) }, 0);

/** The first letters of a name, for the dot that stands for a person. */
export const initials = (name: string): string => name.trim().split(/\s+/).map((w) => w[0] ?? "").join("").slice(0, 2).toUpperCase() || "?";
