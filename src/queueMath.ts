import type { Job } from "./api";

/** What the Render queue shows: every job that is waiting, being made, or finished lately, with a plain phase, how long it has been going, and about how long is left. Pure: no clock, no network. */

export const ACTIVE = ["queued", "submitting", "submitted"];
export const RECENT_S = 900;                 // a take that finished in the last 15 minutes still shows in the queue
export type Phase = "waiting" | "sending" | "rendering" | "done" | "failed" | "check";
export type QueueRow = { job: Job; phase: Phase; elapsed: number | null; fraction: number | null; etaS: number | null; label: string };
export type QueueSummary = { rows: QueueRow[]; waiting: number; sending: number; rendering: number; active: number; done: QueueRow[]; failed: QueueRow[]; etaS: number | null; estUsd: number | null };

export const KIND_LABEL: Record<string, string> = { video: "Video", image: "Keyframe", lipsync: "Lip-sync", asset: "Reference picture" };
export const kindLabel = (j: Job) => KIND_LABEL[j.kind ?? "video"] ?? "Render";

/** The usual time a model takes here: the middle one of its finished takes (from sent to ready). Needs at least one finished take; ignores absurd ones. */
export function typicalSeconds(model: string, kind: string | undefined, jobs: Job[]): number | null {
  const k = kind ?? "video";
  const secs = jobs.filter((j) => j.state === "ready" && j.model === model && (j.kind ?? "video") === k && j.submitted && j.updated > j.submitted)
    .map((j) => j.updated - j.submitted!).filter((s) => s >= 3 && s <= 3600).sort((a, b) => a - b);
  if (!secs.length) return null;
  const m = secs.length >> 1;
  return secs.length % 2 ? secs[m] : Math.round((secs[m - 1] + secs[m]) / 2);
}

export function phaseOf(j: Job): Phase {
  switch (j.state) {
    case "queued": return "waiting";
    case "submitting": return "sending";
    case "submitted": return "rendering";
    case "ready": return "done";
    case "uncertain": return "check";
    default: return "failed";
  }
}

const PHASE_WORDS: Record<Phase, string> = { waiting: "Waiting its turn", sending: "Sending to the provider", rendering: "Rendering", done: "Ready", failed: "Failed", check: "Needs a check" };

export function rowFor(j: Job, jobs: Job[], now: number): QueueRow {
  const phase = phaseOf(j);
  const started = phase === "rendering" || phase === "sending" ? (j.submitted ?? j.updated) : null;
  const elapsed = started ? Math.max(0, now - started) : null;
  const typical = typicalSeconds(j.model, j.kind, jobs);
  let fraction: number | null = null, etaS: number | null = null;
  if (phase === "rendering") {
    if (typeof j.progress === "number") fraction = j.progress;
    else if (typical && elapsed != null) fraction = Math.min(0.95, elapsed / typical);       // an honest guess, never "done" before it is
    if (typical && elapsed != null) etaS = Math.max(0, fraction != null && typeof j.progress === "number" && j.progress > 0.02 && elapsed > 5 ? Math.round(elapsed / j.progress - elapsed) : typical - elapsed);
  }
  const label = j.detail && phase === "rendering" ? `${PHASE_WORDS[phase]} · ${j.detail}` : PHASE_WORDS[phase];
  return { job: j, phase, elapsed, fraction, etaS, label };
}

export function queueSummary(all: Job[], now: number): QueueSummary {
  const live = all.filter((j) => j.state !== "dismissed");
  const rows = live.filter((j) => ACTIVE.includes(j.state)).map((j) => rowFor(j, live, now))
    .sort((a, b) => ({ rendering: 0, sending: 1, waiting: 2 } as Record<string, number>)[a.phase] - ({ rendering: 0, sending: 1, waiting: 2 } as Record<string, number>)[b.phase] || a.job.created - b.job.created);
  const done = live.filter((j) => j.state === "ready" && now - j.updated <= RECENT_S).sort((a, b) => b.updated - a.updated).map((j) => rowFor(j, live, now));
  const failed = live.filter((j) => j.state === "failed" || j.state === "uncertain").filter((j) => now - j.updated <= 86400).sort((a, b) => b.updated - a.updated).map((j) => rowFor(j, live, now));
  const waiting = rows.filter((r) => r.phase === "waiting").length;
  // time left: the longest of what is rendering now, then the waiting ones in lanes of the number rendering (providers run several at once; at least one lane)
  const known = rows.map((r) => r.etaS ?? typicalSeconds(r.job.model, r.job.kind, live));
  let etaS: number | null = null;
  if (rows.length && known.every((x) => x != null)) {
    const rest = rows.filter((r) => r.phase !== "rendering").map((r) => typicalSeconds(r.job.model, r.job.kind, live)!);
    const now_ = rows.filter((r) => r.phase === "rendering").map((r) => r.etaS ?? 0);
    const lanes = Math.max(1, now_.length);
    etaS = Math.max(0, ...now_) + Math.ceil(rest.reduce((a, b) => a + b, 0) / lanes);
  }
  const usd = rows.map((r) => r.job.estimate_usd).filter((x): x is number => typeof x === "number");
  return { rows, waiting, sending: rows.filter((r) => r.phase === "sending").length, rendering: rows.filter((r) => r.phase === "rendering").length, active: rows.length,
    done, failed, etaS, estUsd: usd.length ? Math.round(usd.reduce((a, b) => a + b, 0) * 100) / 100 : null };
}

export function fmtDuration(s: number): string {
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return r ? `${m} min ${r} s` : `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** One sentence for the chip, the Review banner and screen readers. */
export function queueSentence(q: QueueSummary): string {
  if (!q.active) return "";
  const parts = [];
  if (q.rendering + q.sending) parts.push(`${q.rendering + q.sending} rendering`);
  if (q.waiting) parts.push(`${q.waiting} waiting`);
  return parts.join(" · ") + (q.etaS != null && q.etaS > 0 ? ` · about ${fmtDuration(q.etaS)} left` : "");
}

/** The message when a batch settles: what came out. `since` is when the batch began (seconds). */
export function batchOutcome(all: Job[], since: number): { ready: number; failed: number; text: string } {
  const mine = all.filter((j) => j.updated >= since && j.state !== "dismissed");
  const ready = mine.filter((j) => j.state === "ready").length;
  const failed = mine.filter((j) => j.state === "failed" || j.state === "uncertain").length;
  const text = !ready && !failed ? "Renders finished." : `Renders finished: ${ready} ready${failed ? `, ${failed} failed` : ""}.`;
  return { ready, failed, text };
}
