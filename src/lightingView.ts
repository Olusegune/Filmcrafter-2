import type { LightShot, LightingPlan } from "./api";

/** How the lighting screen shows a plan: a colour for each light, and sentences for what applying will do. Pure. */

/** The colour of light at a given temperature (Kelvin), as a hex colour for a swatch: warm tungsten orange, neutral white, cold blue. */
export function kelvinColour(k: number): string {
  const t = Math.max(1000, Math.min(12000, k)) / 100;
  const r = t <= 66 ? 255 : 329.7 * Math.pow(t - 60, -0.1332);
  const g = t <= 66 ? 99.47 * Math.log(t) - 161.12 : 288.12 * Math.pow(t - 60, -0.0755);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.52 * Math.log(t - 10) - 305.04;
  const c = (v: number) => Math.round(Math.max(0, Math.min(255, v)));
  return "#" + [r, g, b].map((v) => c(v).toString(16).padStart(2, "0")).join("");
}

/** The brightness of a swatch from how contrasty the plan is: soft light is light, hard light is dark and moody. */
export function levelOpacity(level: number): number {
  return [1, 0.92, 0.82, 0.72, 0.62][Math.max(0, Math.min(4, level))];
}

/** The colour each mood is drawn in on the strip: the temperature of the light, tinted toward the mood's own colour so that the strip reads as the film's emotional arc. */
export const MOOD_TINT: Record<string, string> = {
  joy: "#ffc94d", tenderness: "#ff9d6e", desire: "#e0405f", calm: "#9fc7d9", nostalgia: "#d9a35c", hope: "#ffd98a", awe: "#b9a8ff", triumph: "#ffb02e", ecstasy: "#ff3fd0",
  melancholy: "#5b7db5", loneliness: "#35508f", grief: "#7d879a", regret: "#8a6aa8", tension: "#6fa38a", menace: "#3f7a58", anger: "#ff3b30", defiance: "#4aa3ff",
};
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const hex = (c: number[]) => "#" + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
/** The strip colour of one shot: its light's temperature mixed with its mood's colour, a little darker the harder the light. */
export function lightColour(s: Pick<LightShot, "mood" | "design">): string {
  const a = rgb(kelvinColour(s.design.kelvin)), b = rgb(MOOD_TINT[s.mood] ?? "#cccccc");
  const dark = 1 - s.design.level * 0.1;
  return hex(a.map((v, i) => (v * 0.4 + b[i] * 0.6) * dark));
}

export type Targets = { all: LightShot[]; own: LightShot[]; targets: LightShot[]; replacing: number };

/** Which shots an Apply will write, from the ticked rows and the "also replace my own choices" switch. */
export function targets(plan: LightingPlan, ticked: Set<string>, overwrite: boolean): Targets {
  const all = plan.shots;
  const chosen = ticked.size ? all.filter((s) => ticked.has(s.shot)) : all;
  const own = chosen.filter((s) => s.user_set);
  return { all, own, targets: overwrite ? chosen : chosen.filter((s) => !s.user_set), replacing: overwrite ? own.length : 0 };
}

/** The sentence over the Apply button. */
export function applySentence(p: Targets, ticked: number, overwrite: boolean): string {
  const n = p.targets.length;
  if (!n) return p.own.length ? `Every shot here has a light you chose yourself, so nothing would change. Tick “also replace” to use the plan anyway.` : "Nothing to apply.";
  const scope = ticked ? `${n} selected shot${n === 1 ? "" : "s"}` : `all ${n} shot${n === 1 ? "" : "s"}`;
  const keep = !overwrite && p.own.length ? ` ${p.own.length} light${p.own.length === 1 ? "" : "s"} you chose yourself ${p.own.length === 1 ? "stays as it is" : "stay as they are"}.` : "";
  const over = overwrite && p.replacing ? ` This replaces ${p.replacing} light${p.replacing === 1 ? "" : "s"} you chose yourself (Undo brings them back).` : "";
  return `Use the plan for ${scope}.${keep}${over} Nothing is rendered or billed; render a shot again to see its new light.`;
}

/** One line per scene: the mood's journey and the lights it uses. */
export function sceneLine(s: LightingPlan["scenes"][number]): string {
  return `${s.arc}`;
}

export type LightRun = { key: string; shots: LightShot[]; first: LightShot; last: LightShot; own: boolean; held: boolean };

/** Neighbouring shots of a scene that get exactly the same light and mood, as one run: ten shots of "Calm, golden hour, 5600 K" are one fact, not ten. */
export function groupRuns(rows: LightShot[]): LightRun[] {
  const runs: LightRun[] = [];
  for (const s of rows) {
    const key = [s.label, s.design.label, s.design.kelvin, s.design.level, !!s.user_set].join("|");
    const cur = runs[runs.length - 1];
    if (cur && cur.key === key) { cur.shots.push(s); cur.last = s; cur.held = cur.held || !!s.held; }
    else runs.push({ key, shots: [s], first: s, last: s, own: !!s.user_set, held: !!s.held });
  }
  return runs;
}

/** "S01-02" for one shot, "S01-02 – S01-05" for a run. */
export const runName = (r: Pick<LightRun, "first" | "last" | "shots">): string => (r.shots.length === 1 ? r.first.shot : `${r.first.shot} – ${r.last.shot}`);

/** The tick state of a run from the set of ticked shots: none, some or all of it. */
export function runTick(r: Pick<LightRun, "shots">, ticked: ReadonlySet<string>): "none" | "some" | "all" {
  const n = r.shots.filter((s) => ticked.has(s.shot)).length;
  return n === 0 ? "none" : n === r.shots.length ? "all" : "some";
}
