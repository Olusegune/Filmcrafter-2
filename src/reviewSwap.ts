import type { Job } from "./api";

/**
 * Review's "New versions ready": after Fix re-renders a shot, the finished take waits here until you swap it in, one at a time or all together.
 * The take that is in your video is the approved one; with none approved, the newest finished one (the same rule the engine uses to build the video).
 */

const ACTIVE = ["queued", "submitting", "submitted"];
const isTake = (j: Job) => (j.kind ?? "video") !== "image" && j.kind !== "asset";

/** Finished video takes of a shot (lip-synced ones included), in the plan of its newest take. */
export function takesOf(shotId: string, jobs: Job[]): Job[] {
  const mine = jobs.filter((j) => j.shot_id === shotId && j.state === "ready" && !!j.output && isTake(j));
  const newest = [...mine].sort((a, b) => b.created - a.created)[0];
  return newest ? mine.filter((j) => j.plan === newest.plan) : [];
}

/** The take that is in the video for this shot. */
export function inUseTake(shotId: string, jobs: Job[], approvedId: string | null | undefined): Job | undefined {
  const takes = takesOf(shotId, jobs);
  return takes.find((j) => j.id === approvedId) ?? [...takes].sort((a, b) => b.created - a.created)[0];
}

/** A finished take newer than the one in use, ready to swap in. Not offered while the shot is still rendering (a lip-sync pass may be coming after the video). */
export function newVersion(cur: Job, jobs: Job[]): Job | null {
  if (jobs.some((j) => j.shot_id === cur.shot_id && j.plan === cur.plan && isTake(j) && ACTIVE.includes(j.state))) return null;
  const newer = takesOf(cur.shot_id, jobs).filter((j) => j.created > cur.created && j.id !== cur.id);
  return [...newer].sort((a, b) => b.created - a.created)[0] ?? null;
}

export type Verdict = "good" | "minor" | "major" | "checking" | "unchecked";

/** What the automatic check said about a take, in the three words the screen uses. */
export function verdictOf(j: Job): Verdict {
  const r = j.review;
  if (!r || !r.reviewed) return r?.accepted ? "good" : "checking";
  if (r.status === "unchecked") return r.accepted ? "good" : "unchecked";
  if (r.accepted || r.status === "good") return "good";
  return r.status === "needs_attention" ? "major" : "minor";
}

export const VERDICT_WORDS: Record<Verdict, string> = { good: "Looks good", minor: "Minor issues", major: "Still needs attention", checking: "Being checked", unchecked: "Not checked visually" };

export type Upgrade<S> = { shot: S; cur: Job; next: Job; verdict: Verdict };

export function upgradesFor<S extends { id: string }>(shots: S[], jobs: Job[], inUse: Record<string, string | null | undefined>, declined: Set<string>): Upgrade<S>[] {
  return shots.flatMap((shot) => {
    const cur = inUseTake(shot.id, jobs, inUse[shot.id]);
    const next = cur ? newVersion(cur, jobs) : null;
    return cur && next && !declined.has(next.id) ? [{ shot, cur, next, verdict: verdictOf(next) }] : [];
  });
}

/** The sentence over the "use all" buttons. */
export function swapSummary(ups: { verdict: Verdict }[]): string {
  const n = ups.length;
  const bad = ups.filter((u) => u.verdict === "minor" || u.verdict === "major").length;
  const wait = ups.filter((u) => u.verdict === "checking").length;
  const blind = ups.filter((u) => u.verdict === "unchecked").length;
  const base = `${n} new version${n === 1 ? " is" : "s are"} ready to swap in.`;
  if (bad) return `${base} ${bad} still ${bad === 1 ? "has" : "have"} issues the check found; the rest look good.`;
  if (wait) return `${base} ${wait} ${wait === 1 ? "is" : "are"} still being checked.`;
  if (blind) return `${base} ${blind === 1 ? "It was" : blind + " were"} not checked by eye (no vision model is set), so look before you swap.`;
  return `${base} All of them look good.`;
}

/** The one quiet sentence under the Review title: how many takes there are and how they look. */
export function reviewHeadline(c: { rendered: number; shots: number; good: number; minor: number; major: number; unchecked: number; rendering: number }): string {
  const bits: string[] = [];
  if (c.good > 0) bits.push(`${c.good} look${c.good === 1 ? "s" : ""} good`);
  if (c.minor > 0) bits.push(`${c.minor} ${c.minor === 1 ? "has" : "have"} small notes`);
  if (c.major > 0) bits.push(`${c.major} need${c.major === 1 ? "s" : ""} attention`);
  if (c.unchecked > 0) bits.push(`${c.unchecked} ${c.unchecked === 1 ? "was" : "were"} not checked by eye`);
  if (c.rendering > 0) bits.push(`${c.rendering} ${c.rendering === 1 ? "is" : "are"} being made`);
  return `${c.rendered} of ${c.shots} shots have a take${bits.length ? `: ${bits.join(", ")}` : ""}.`;
}

/** Issues most serious first; only the first is shown at once, the rest wait behind "more details". */
export function splitIssues<T extends { severity: string }>(issues: T[] | undefined): { first: T | null; rest: T[] } {
  const ordered = [...(issues ?? [])].sort((a, b) => Number(b.severity === "major") - Number(a.severity === "major"));
  return { first: ordered[0] ?? null, rest: ordered.slice(1) };
}

/** The two lines over the "use all" button: what is ready, and the one thing worth knowing about it. */
export function swapHeadline(ups: { verdict: Verdict }[]): { title: string; detail: string } {
  const n = ups.length;
  const bad = ups.filter((u) => u.verdict === "minor" || u.verdict === "major").length;
  const wait = ups.filter((u) => u.verdict === "checking").length;
  const blind = ups.filter((u) => u.verdict === "unchecked").length;
  const title = `${n} new version${n === 1 ? "" : "s"} ready to swap in`;
  if (bad) return { title, detail: n === 1 ? "It still has issues the check found." : bad === n ? "All of them still have issues the check found." : `${bad} of them still ${bad === 1 ? "has" : "have"} issues the check found.` };
  if (wait) return { title, detail: `${wait} ${wait === 1 ? "is" : "are"} still being checked.` };
  if (blind) return { title, detail: "They were not checked by eye (no vision model is set): look before you swap." };
  return { title, detail: "All of them look good." };
}
