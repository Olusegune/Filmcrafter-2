import type { Cut, CutClip } from "./api";

/** Small pure helpers for the cut lane: where a dragged edge snaps to, what to tell the person about the cut, and how to say a time. Times are seconds here; the engine rounds them to whole frames. */

export const SNAP_PX = 8;                                                    // how close, in pixels, an edge has to come before it snaps

export const frameSeconds = (cut: Cut): number => cut.sequence.frame_ticks / cut.sequence.ticks_per_second;

/** The times a dragged edge or clip can snap to: the film's start and end, every other clip's edges, the markers and the playhead. De-duplicated and sorted. */
export function snapPoints(cut: Cut, exceptClip: string | null, playhead: number | null): number[] {
  const s = new Set<number>([0, cut.sequence.length_s]);
  for (const t of cut.sequence.tracks) for (const c of t.clips) if (c.id !== exceptClip) { s.add(c.start_s); s.add(c.start_s + c.duration_s); }
  for (const m of cut.sequence.markers) s.add(m.at_s);
  if (playhead != null) s.add(playhead);
  return [...s].sort((a, b) => a - b);
}

/** The nearest point within `tol` seconds, else the time itself. A tie goes to the earlier point. */
export function nearest(points: number[], t: number, tol: number): number {
  let best: number | null = null;
  for (const p of points) {
    const gap = Math.abs(p - t);
    if (gap <= tol && (best === null || gap < Math.abs(best - t))) best = p;
  }
  return best === null ? t : best;
}

/** Plain-language notes about the cut: shots that are not in it, clips left out, and that it differs from the plan. */
export function cutNotes(cut: Cut, free: { start: number }[] = []): string[] {
  const out: string[] = [];
  const n = cut.unplaced.length;
  if (n) out.push(`${n === 1 ? `Shot ${cut.unplaced[0]} is` : `${n} shots (${cut.unplaced.slice(0, 3).join(", ")}${n > 3 ? "…" : ""}) are`} not in the cut, so ${n === 1 ? "it is" : "they are"} left out of the film.`);
  const o = cut.orphans.length;
  if (o) out.push(`${o === 1 ? "A clip's shot is" : `${o} clips' shots are`} no longer in the plan, so ${o === 1 ? "it is" : "they are"} left out of the film.`);
  const late = free.filter((f) => f.start >= cut.sequence.length_s).length;
  if (late) out.push(`${late} layer${late === 1 ? "" : "s"} ${late === 1 ? "starts" : "start"} after the end of the cut, so ${late === 1 ? "it" : "they"} will not be seen.`);
  return out;
}

export const clockTime = (s: number): string => {
  const t = Math.max(0, s);
  const m = Math.floor(t / 60);
  const sec = t - m * 60;
  return `${m}:${sec < 10 ? "0" : ""}${sec.toFixed(2)}`;
};

export const clipName = (c: CutClip): string => `${c.shot} from ${clockTime(c.start_s)} for ${clockTime(c.duration_s)}`;

/** The clip a time falls in (the first, if the cut has more than one track), or null. */
export function clipAt(cut: Cut, t: number): CutClip | null {
  for (const tr of cut.sequence.tracks) for (const c of tr.clips) if (t >= c.start_s && t < c.start_s + c.duration_s) return c;
  return null;
}
