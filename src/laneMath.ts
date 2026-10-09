/** The arithmetic of layer lanes on the timeline: which lane a layer sits in, and what a drag does to its start and end. No screen code, so it can be tested. */
export type Span = { id: string; start: number; end: number };

export const MIN_LEN = 0.3;          // a layer is never trimmed shorter than this (seconds)
export const SNAP_PX = 7;            // a drag snaps to a beat, lyric or shot edge when it is this close on screen

/** Lane numbers for layers (0 = the first lane above the shots). A layer takes the first lane where it does not overlap another, so lanes stay few. Stable: the same input gives the same lanes.
 *  With `backToFront` (the layers in drawing order, the last drawn on top) the lane IS the stacking order, as in a video editor: the layer in front takes the highest lane (lane 0), and a layer
 *  that overlaps it in time sits below it. Layers that never overlap share a lane. */
export function packLanes(spans: Span[], backToFront?: string[]): Record<string, number> {
  const out: Record<string, number> = {};
  if (backToFront) {
    const rank = new Map(backToFront.map((id, i) => [id, i]));
    const lanes: Span[][] = [];
    const frontFirst = [...spans].sort((a, b) => (rank.get(b.id) ?? -1) - (rank.get(a.id) ?? -1) || a.start - b.start || a.id.localeCompare(b.id));
    for (const s of frontFirst) {
      let lane = lanes.findIndex((l) => l.every((o) => o.end <= s.start + 1e-6 || o.start >= s.end - 1e-6));
      if (lane < 0) { lane = lanes.length; lanes.push([]); }
      lanes[lane].push(s);
      out[s.id] = lane;
    }
    return out;
  }
  const ends: number[] = [];
  for (const s of [...spans].sort((a, b) => a.start - b.start || a.end - b.end || a.id.localeCompare(b.id))) {
    let lane = ends.findIndex((e) => e <= s.start + 1e-6);
    if (lane < 0) { lane = ends.length; ends.push(0); }
    ends[lane] = s.end;
    out[s.id] = lane;
  }
  return out;
}

/** Moving a layer to another lane means a new place in the drawing order: up puts it in front of the layers it overlaps in the lanes it crosses, down puts it behind them.
 *  Returns the position in the drawing order for the engine's reorder (counted after the layer is taken out), or null when nothing it overlaps is in the way (so the move would change nothing). */
export function restack(order: string[], spans: Span[], lanes: Record<string, number>, id: string, target: number): number | null {
  const me = spans.find((s) => s.id === id);
  const from = lanes[id];
  const i = order.indexOf(id);
  if (!me || from === undefined || i < 0 || !Number.isFinite(target) || target === from || target < 0) return null;
  const overlaps = (o: Span) => o.id !== id && o.start < me.end - 1e-6 && o.end > me.start + 1e-6;
  const up = target < from;
  const crossed = spans.filter((o) => overlaps(o) && order.includes(o.id) && lanes[o.id] !== undefined && (up ? lanes[o.id] >= target && lanes[o.id] < from : lanes[o.id] > from && lanes[o.id] <= target));
  if (!crossed.length) return null;
  if (up) { const x = Math.max(...crossed.map((o) => order.indexOf(o.id))); return x > i ? x : x + 1; }
  const x = Math.min(...crossed.map((o) => order.indexOf(o.id)));
  return x > i ? x - 1 : x;
}

/** Which lane a vertical position falls in (0 at the top), kept inside the lanes that exist. */
export function laneAt(y: number, laneHeight: number, count: number): number {
  return Math.max(0, Math.min(Math.max(0, count - 1), Math.floor(y / Math.max(1, laneHeight))));
}

/** The time under a horizontal position in the lane row (pixels from its left edge), kept inside the song and rounded to a tenth of a second. */
export function timeAtX(x: number, pps: number, duration: number): number {
  return Math.round(Math.max(0, Math.min(Math.max(0, duration - 0.5), x / Math.max(1, pps))) * 10) / 10;
}

/** The nearest snap point to t within `reach` seconds, or t itself. */
export function snapTo(t: number, points: number[], reach: number): number {
  let best = t, d = reach;
  for (const p of points) { const e = Math.abs(p - t); if (e <= d) { best = p; d = e; } }
  return best;
}

export type Drag = "move" | "trim-start" | "trim-end";

/** The new start and end after dragging by `dt` seconds. Moving keeps the length and stays inside the song; trimming keeps at least MIN_LEN and stays inside the song. Snaps to `points`. */
export function drag(kind: Drag, from: { start: number; end: number }, dt: number, duration: number, points: number[] = [], reach = 0): { start: number; end: number } {
  const len = from.end - from.start;
  const round = (v: number) => Math.round(v * 100) / 100;
  if (kind === "move") {
    let s = from.start + dt;
    const sa = snapTo(s, points, reach), eb = snapTo(s + len, points, reach);           // the start or the end may snap; if both do, the closer one wins
    const hitA = sa !== s, hitB = eb !== s + len;
    if (hitA && hitB) s = Math.abs(sa - s) <= Math.abs(eb - (s + len)) ? sa : eb - len;
    else if (hitA) s = sa;
    else if (hitB) s = eb - len;
    s = Math.max(0, Math.min(Math.max(0, duration - len), s));
    return { start: round(s), end: round(s + len) };
  }
  if (kind === "trim-start") {
    const s = Math.max(0, Math.min(from.end - MIN_LEN, snapTo(from.start + dt, points, reach)));
    return { start: round(s), end: from.end };
  }
  const e = Math.min(duration || Infinity, Math.max(from.start + MIN_LEN, snapTo(from.end + dt, points, reach)));
  return { start: from.start, end: round(e) };
}

/** Where a layer's bar and keyframe diamonds sit, in pixels, for a given zoom. Keyframe times are relative to the layer's start. */
export function barBox(o: { start: number; end: number; keys?: { t: number }[] }, pps: number) {
  return { left: o.start * pps, width: Math.max(6, (o.end - o.start) * pps), keys: (o.keys ?? []).map((k) => (k.t) * pps) };
}

/** Snap points: beat grid downbeats, lyric starts, shot edges, the playhead. De-duplicated and sorted. */
export function snapPoints(parts: { downbeats?: number[]; lyrics?: { start?: number | null }[]; shots?: { start: number; end: number }[]; playhead?: number }): number[] {
  const s = new Set<number>();
  for (const d of parts.downbeats ?? []) s.add(Math.round(d * 100) / 100);
  for (const l of parts.lyrics ?? []) if (l.start != null) s.add(Math.round(l.start * 100) / 100);
  for (const sh of parts.shots ?? []) { s.add(Math.round(sh.start * 100) / 100); s.add(Math.round(sh.end * 100) / 100); }
  if (parts.playhead != null) s.add(Math.round(parts.playhead * 100) / 100);
  return [...s].sort((a, b) => a - b);
}

/** Where to put the playhead when a layer is chosen: nowhere if it is already inside the layer, else just inside its start, so the layer is on the player at full strength and can be dragged into place. */
export function seekInto(time: number, start: number, end: number): number | null {
  if (!(end > start) || (time >= start && time <= end)) return null;
  return Math.round(Math.min(end - 0.05, start + Math.min(0.5, (end - start) / 2)) * 100) / 100;
}
