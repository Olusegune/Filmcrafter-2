/** Keyframes on a layer, drawn on the player with the same formulas the export uses (see overlays.eval_keys in the engine; src/__tests__/overlayKeys.test.ts and
 *  analysis/tests/test_keyframes.py check the same cases). A key is a moment (seconds after the layer appears) and any of x, y (where the centre is, as fractions of
 *  the frame), scale and opacity (multiply the layer's own) and rotation (degrees added to its own). Between two keys a property goes from one value to the next with
 *  the first key's easing; before the first key it holds the first value, after the last key the last. A key that leaves a property out does not touch it. */
export type KeyProp = "x" | "y" | "scale" | "rotation" | "opacity";
export type Ease = "linear" | "ease_in" | "ease_out" | "ease_in_out" | "hold";
export type Key = { t: number; ease?: Ease } & Partial<Record<KeyProp, number>>;

export const KEY_PROPS: KeyProp[] = ["x", "y", "scale", "rotation", "opacity"];
export const EASES: [Ease, string][] = [["ease_in_out", "Smooth"], ["linear", "Steady"], ["ease_in", "Speeds up"], ["ease_out", "Slows down"], ["hold", "Jump at the next key"]];
export const MAX_KEYS = 12;

const ease = (name: Ease, u: number) => {
  u = Math.min(1, Math.max(0, u));
  switch (name) {
    case "linear": return u;
    case "ease_in": return u * u;
    case "ease_out": return 2 * u - u * u;
    case "hold": return 0;
    default: return u * u * (3 - 2 * u);
  }
};

export function evalKeys(keys: Key[] | undefined, t: number): Partial<Record<KeyProp, number>> {
  const out: Partial<Record<KeyProp, number>> = {};
  if (!keys?.length) return out;
  for (const prop of KEY_PROPS) {
    const pts = keys.filter((k) => k[prop] != null).map((k) => ({ t: k.t, v: k[prop] as number, e: k.ease ?? "ease_in_out" }));
    if (!pts.length) continue;
    if (t <= pts[0].t) { out[prop] = pts[0].v; continue; }
    let value = pts[pts.length - 1].v;
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i], b = pts[i + 1];
      if (t < b.t) { value = a.v + (b.v - a.v) * ease(a.e, (t - a.t) / Math.max(b.t - a.t, 1e-3)); break; }
    }
    out[prop] = value;
  }
  return out;
}

/** A key at `t` with these values: an existing key within a tenth of a second is changed instead of adding a second one. */
export function upsertKey(keys: Key[] | undefined, t: number, values: Partial<Record<KeyProp, number>>): Key[] {
  const list = [...(keys ?? [])];
  const at = list.findIndex((k) => Math.abs(k.t - t) <= 0.1);
  if (at >= 0) list[at] = { ...list[at], ...values };
  else if (list.length < MAX_KEYS) list.push({ t: Math.round(t * 1000) / 1000, ease: "ease_in_out", ...values });
  return list.sort((a, b) => a.t - b.t);
}
