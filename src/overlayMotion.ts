/** How a layer moves in, as the player draws it: the same numbers the export uses (see overlays.motion in the engine). Offsets are in percent of the frame;
 *  `reveal` is how much of the layer, from its left edge, is shown (1 = all). */
export type Move = { dx: number; dy: number; k: number; reveal: number };
export type Beat = { period: number; first: number };

const clip = (v: number) => Math.max(0, Math.min(1, v));
const still: Move = { dx: 0, dy: 0, k: 1, reveal: 1 };

/** The beat grid the "pulse" movement follows, from the song map (null when the song has no usable tempo). */
export function beatGrid(map: { bpm?: number; beats?: number[]; downbeats?: number[] } | null | undefined): Beat | null {
  const bpm = Number(map?.bpm ?? 0);
  if (!(bpm >= 40 && bpm <= 240)) return null;
  const marks = map?.downbeats?.length ? map.downbeats : map?.beats ?? [];
  return { period: 60 / bpm, first: Math.max(0, marks[0] ?? 0) };
}

/** True when the person has asked their computer for less motion: the player then shows layers still, at rest. (The export is never changed by this.) */
export const reducedMotion = (): boolean => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

export const ACCENT_FOR = 0.35, ACCENT_BY = 0.08;      // a strong hit swells a layer by 8% and it settles over a third of a second (the export uses the same numbers)

export function moveAt(anim: string | undefined, t: number, start: number, end: number, fade: number, beat?: Beat | null, chars = 0, accents?: number[] | null): Move {
  const m = Math.max(fade, Math.min(1.2, (end - start) / 2));
  const p = clip((t - start) / m);
  const ease = Math.pow(1 - p, 3);                           // 1 at the start, 0 once settled
  switch (anim) {
    case "rise": return { ...still, dy: 7 * ease };
    case "drop": return { ...still, dy: -7 * ease };
    case "slide_left": return { ...still, dx: 14 * ease };
    case "slide_right": return { ...still, dx: -14 * ease };
    case "zoom_in": return { ...still, k: 0.82 + 0.18 * (1 - ease) };
    case "zoom_out": return { ...still, k: 1.18 - 0.18 * (1 - ease) };
    case "pushin": return { ...still, k: 1 + 0.08 * clip((t - start) / Math.max(0.5, end - start)) };
    case "wipe": return { ...still, reveal: p };
    case "typewriter": return { ...still, reveal: chars < 2 ? p : Math.floor(chars * p + 0.0001) / chars };      // a letter at a time (letters of unequal width are only approximate)
    case "bounce": return { ...still, dy: -9 * Math.pow(1 - p, 2) * Math.cos(3 * Math.PI * p) };                  // 9% of the frame height, settling in a few bounces
    case "pop": return { ...still, k: Math.max(0.05, 1 + 2.70158 * Math.pow(p - 1, 3) + 1.70158 * Math.pow(p - 1, 2)) };
    case "pulse": {
      if (!beat) return still;
      const ph = (((t - beat.first) % beat.period) + beat.period) % beat.period / beat.period;                    // 0 on the beat, towards 1 just before the next
      return { ...still, k: 1 + 0.06 * Math.pow(1 - ph, 3) };
    }
    case "accent": {
      const hit = (accents ?? []).filter((a) => a >= start - 0.5 && a <= end + 0.5 && a <= t).pop();                 // the latest strong hit so far
      return hit == null ? still : { ...still, k: 1 + ACCENT_BY * Math.pow(1 - clip((t - hit) / ACCENT_FOR), 3) };
    }
    default: return still;
  }
}
