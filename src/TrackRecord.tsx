import type { ModelTrack, TrackStats } from "./api";
import "./acting.css";

const FAIL_WORDS: Record<string, string> = { credits: "out of credits", service: "provider busy or down", moderation: "refused by the provider's checks", timeout: "timed out", input: "input rejected", other: "other" };

/** The one line about the model picked: what it has done in this project. Words only, and only from what was recorded. */
export function trackLine(m: ModelTrack | undefined, name: string): string {
  if (!m) return `No takes with ${name} in this project yet.`;
  const parts = [`${m.takes} take${m.takes === 1 ? "" : "s"}`];
  if (m.failed) {
    const why = Object.entries(m.failures).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${FAIL_WORDS[k] ?? k}`).join(", ");
    parts.push(`${m.failed} failed (${why})`);
  }
  const reviewed = Object.values(m.reviews).reduce((a, b) => a + b, 0);
  if (reviewed) parts.push(`${m.reviews.good ?? 0} of ${reviewed} reviewed took as good`);
  if (m.sung) {
    const ok = m.sound.in_time ?? 0;
    const own = (m.sound.own_audio ?? 0) + (m.sound.loose ?? 0);
    parts.push(`sound in time with the voice on ${ok} of ${m.sung} spoken take${m.sung === 1 ? "" : "s"}${own ? `, made its own sound on ${own}` : ""}`);
  }
  if (m.cost > 0) parts.push(`$${m.cost.toFixed(2)} spent`);
  return `${name} in this project: ${parts.join("; ")}.`;
}

export function TrackRecord({ stats, model, title }: { stats: TrackStats | null; model: string; title?: string }) {
  if (!stats || !stats.models.length) return null;
  const mine = stats.models.find((m) => m.model === model);
  const others = stats.models.filter((m) => m.model !== model);
  return (
    <details className="tr-rec">
      <summary>{trackLine(mine, title ?? model)}</summary>
      {others.length > 0 && <ul>{others.map((m) => <li key={`${m.provider}|${m.model}`}>{trackLine(m, m.model)}</li>)}</ul>}
      <p className="dim">From your own renders in this project, so it only says something once there are a few. Sound is checked on this computer, for free.</p>
    </details>
  );
}
