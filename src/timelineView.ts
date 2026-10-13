/** How the timeline is laid out (zoom, height, compact) is remembered for each project, so a long film and a short one each keep their own view.
 *  Storage can be missing or blocked, and what it holds may be damaged, so every read is checked and clamped and every write is guarded. */
type Store = Pick<Storage, "getItem" | "setItem">;
const local = (): Store | null => { try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; } };

export type TlLayout = { pps?: number; height?: number; compact?: boolean; sized?: boolean; edit?: boolean; voices?: boolean };   // sized: the person dragged the height themselves, so it is kept however short

export const PPS_MIN = 6;
export const PPS_MAX = 400;
export const HEIGHT_MIN = 150;
export const HEIGHT_MAX = 1200;
/** The height of the timeline in compact mode: the song map and the shot cards, no more. */
export const COMPACT_HEIGHT = 170;
/** The height of a shot card in the Film strip: one size, so a picture is never squashed or stretched. */
export const STRIP_CARD_H = 112;
const MAX_KEY = 300;

const keyFor = (dir: string) => `pf-tl:${String(dir).slice(0, MAX_KEY)}`;
const num = (v: unknown, lo: number, hi: number): number | undefined => (typeof v === "number" && Number.isFinite(v) ? Math.max(lo, Math.min(hi, Math.round(v))) : undefined);

/** This project's layout. Anything missing or damaged is left out (the caller's default applies); a project with no layout of its own starts from the old shared zoom and height. */
export function readLayout(dir: string, store: Store | null = local()): TlLayout {
  let own: unknown = null;
  try { const raw = store?.getItem(keyFor(dir)); own = raw ? JSON.parse(raw) : null; } catch { own = null; }
  const o = own && typeof own === "object" && !Array.isArray(own) ? (own as Record<string, unknown>) : {};
  const legacy = (k: string) => { try { const n = Number(store?.getItem(k)); return Number.isFinite(n) && n > 0 ? n : undefined; } catch { return undefined; } };
  const out: TlLayout = {};
  const pps = num(o.pps ?? legacy("pf-zoom"), PPS_MIN, PPS_MAX);
  const height = num(o.height ?? legacy("pf-tl-h"), HEIGHT_MIN, HEIGHT_MAX);
  if (pps !== undefined) out.pps = pps;
  if (height !== undefined) out.height = height;
  if (o.compact === true) out.compact = true;
  if (o.sized === true) out.sized = true;
  if (o.edit === true) out.edit = true;
  if (o.voices === true) out.voices = true;                // the Voices band shows every person, not the first three                  // the full, flexible timeline; the Film strip is the default
  return out;
}

/** Remember a change to this project's layout (the rest of it is kept). */
export function writeLayout(dir: string, patch: TlLayout, store: Store | null = local()): void {
  try {
    const next = { ...readLayout(dir, store), ...patch };
    store?.setItem(keyFor(dir), JSON.stringify(next));
  } catch { /* remembering is a convenience only */ }
}

/** Start times of the shots that need a look, in order. */
export function attentionStarts(shots: { id: string; start: number }[], needs: ReadonlySet<string>): number[] {
  return shots.filter((s) => needs.has(s.id)).map((s) => s.start).sort((a, b) => a - b);
}

/** The next (dir 1) or previous (dir -1) start time from `time`, or null when there is none that way. A small margin keeps the shot you are on from counting as "next". */
export function stepAttention(starts: number[], time: number, dir: 1 | -1): number | null {
  if (dir === 1) return starts.find((t) => t > time + 0.05) ?? null;
  return [...starts].reverse().find((t) => t < time - 0.25) ?? null;
}
