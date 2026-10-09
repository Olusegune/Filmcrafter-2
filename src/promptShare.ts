/** Where the words of a video prompt go: what happens and how it is played, the locks that keep the look steady, camera and set, style and world, and the standing rules. */
export type PromptBlock = { priority: number; text: string; kept: boolean };
export type BudgetGroup = "acting" | "locks" | "camera" | "style" | "rules";

export const GROUPS: { id: BudgetGroup; label: string; what: string }[] = [
  { id: "acting", label: "Action and acting", what: "what happens, how it is played, the lines and the movement" },
  { id: "locks", label: "Locks and continuity", what: "who looks like what, who stands where, the references" },
  { id: "camera", label: "Camera, set and light", what: "the lens, the room, the light, the wardrobe" },
  { id: "style", label: "Style and world", what: "the look, the world rules and the palette" },
  { id: "rules", label: "Standing rules", what: "no text on screen, no lip-sync for others" },
];

const ACTING = /^(Emotion:|Performance|Face:|Body and blocking:|Choreography|Dance direction|Movement style|Movement direction|Keep people alive|Near-stillness|Lively micro-motion|Charged stillness|Constant rhythmic life|Play it|Underplay|Commit fully|Let the feeling|Heighten|Spoken dialogue|Emotional arc|Signature gestures|Opening moment|Relaxed)/;
const SPEECH = /\b(says|voices these words|sings|speaks|calls)\b[^"]*"/;
const LOCKS = /^(Characters:|Locked design|Continuity for this shot|References:|Blocking \(|Always:|Never show:|Motion references:)/;
const CAMERA = /^(Camera:|Focus:|Setting:|Lighting:|Wardrobe:)/;
const STYLE = /^(Look:|World:|Palette:|Mood and colour:)/;

/** Which group a block belongs to. The first block is the shot's own description of what happens. */
export function groupOf(text: string, first = false): BudgetGroup {
  const t = text.trim();
  if (first) return "acting";
  if (ACTING.test(t) || SPEECH.test(t)) return "acting";
  if (LOCKS.test(t)) return "locks";
  if (CAMERA.test(t)) return "camera";
  if (STYLE.test(t)) return "style";
  return "rules";
}

export type Budget = { total: number; shares: { id: BudgetGroup; chars: number; pct: number }[]; dropped: number };

/** The characters the prompt spends on each group (only what is sent), and how many blocks the model's length limit dropped. */
export function budgetOf(blocks: PromptBlock[]): Budget {
  const chars: Record<BudgetGroup, number> = { acting: 0, locks: 0, camera: 0, style: 0, rules: 0 };
  let dropped = 0;
  blocks.forEach((b, i) => { if (b.kept) chars[groupOf(b.text, i === 0)] += b.text.length; else dropped++; });
  const total = Object.values(chars).reduce((a, b) => a + b, 0);
  return { total, dropped, shares: GROUPS.map((g) => ({ id: g.id, chars: chars[g.id], pct: total ? Math.round((chars[g.id] / total) * 100) : 0 })) };
}

/** One plain sentence about the balance, or nothing when it is fine. */
export function budgetNote(b: Budget): string {
  const pct = (id: BudgetGroup) => b.shares.find((s) => s.id === id)?.pct ?? 0;
  if (!b.total) return "";
  if (b.dropped) return `${b.dropped} block${b.dropped === 1 ? " was" : "s were"} left out to fit this model's length limit, starting with the least important.`;
  if (pct("acting") < 25) return `Only ${pct("acting")}% of this prompt is what happens and how it is played; ${pct("locks") + pct("style") + pct("rules")}% is locks, world and rules. A model gives the acting less attention the further it is buried.`;
  return "";
}
