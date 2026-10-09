/** How a shot enters from the one before it. The same list, labels and default lengths as analysis/filmcrafter_engine/transitions.py (a test keeps them in step). */
export type TransitionInfo = { id: string; label: string; group: "Basic" | "Wipe" | "Move"; secs: number };
export const TRANSITION_LIST: TransitionInfo[] = [
  { id: "cut", label: "Cut", group: "Basic", secs: 0 },
  { id: "dissolve", label: "Cross-dissolve", group: "Basic", secs: 0.5 },
  { id: "black", label: "Dip to black", group: "Basic", secs: 0.3 },
  { id: "white", label: "Flash of white", group: "Basic", secs: 0.3 },
  { id: "wipe_right", label: "Wipe to the right", group: "Wipe", secs: 0.5 },
  { id: "wipe_left", label: "Wipe to the left", group: "Wipe", secs: 0.5 },
  { id: "wipe_down", label: "Wipe down", group: "Wipe", secs: 0.5 },
  { id: "wipe_up", label: "Wipe up", group: "Wipe", secs: 0.5 },
  { id: "slide_left", label: "Slide off to the left", group: "Move", secs: 0.45 },
  { id: "slide_right", label: "Slide off to the right", group: "Move", secs: 0.45 },
  { id: "slide_up", label: "Slide off upward", group: "Move", secs: 0.45 },
  { id: "slide_down", label: "Slide off downward", group: "Move", secs: 0.45 },
  { id: "whip_left", label: "Whip to the left", group: "Move", secs: 0.25 },
  { id: "whip_right", label: "Whip to the right", group: "Move", secs: 0.25 },
  { id: "zoom_through", label: "Zoom through", group: "Move", secs: 0.6 },
];
export const MIN_TRANSITION_S = 0.1;
export const MAX_TRANSITION_S = 2.0;
export const transitionInfo = (id: string | undefined): TransitionInfo => TRANSITION_LIST.find((t) => t.id === id) ?? TRANSITION_LIST[0];
/** The length in force: the one chosen for the shot, else the transition's own; never more than half the shot (the engine does the same). */
export const transitionSeconds = (id: string | undefined, chosen: number | null | undefined, shotLength: number): number => {
  const t = transitionInfo(id);
  if (t.id === "cut") return 0;
  const want = chosen != null && chosen > 0 ? Math.min(MAX_TRANSITION_S, Math.max(MIN_TRANSITION_S, chosen)) : t.secs;
  return Math.min(want, Math.max(0.1, shotLength / 2));
};
/** A one-character picture for a transition's handle on the timeline. */
export const transitionGlyph = (id: string | undefined): string => {
  const k = transitionInfo(id).id;
  if (k === "cut") return "|";
  if (k === "dissolve") return "◐";
  if (k === "black") return "●";
  if (k === "white") return "○";
  if (k.startsWith("wipe_")) return { right: "▶", left: "◀", up: "▲", down: "▼" }[k.slice(5) as "right"];
  if (k.startsWith("slide_")) return { right: "⇢", left: "⇠", up: "⇡", down: "⇣" }[k.slice(6) as "right"];
  if (k.startsWith("whip_")) return k.endsWith("left") ? "⟸" : "⟹";
  return "✦";
};
