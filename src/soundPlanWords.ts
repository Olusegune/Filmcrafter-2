import type { SoundRoute } from "./api";

/** The plain name of how a shot's voice is made, and what the person can do about it. */
export const routeWords = (r: SoundRoute): string => ({
  none: "No voice", voice_over: "Voice-over", needs_voice: "Needs a voice", audio_in: "Model follows the recording", post_sync: "Laid over at export", native: "Model speaks",
} as Record<SoundRoute, string>)[r] ?? r;

/** Faults first: a shot that cannot be made yet, then the ones to look at, then the settled ones. */
export const routeOrder = (r: SoundRoute): number => ({ needs_voice: 0, native: 1, audio_in: 2, post_sync: 3, voice_over: 4, none: 5 } as Record<SoundRoute, number>)[r] ?? 9;

export const settingWords = (s: string): string => (s === "off" ? "Nobody on screen speaks" : s === "on" ? "Someone on screen speaks" : "Automatic");

/** The video price line: what making the shots that have people speaking would cost, and what is not priced. Never a made-up figure. */
export const videoCostWords = (c: { usd: number | null; usd_known: number | null; unknown: number; shots: number; lipsync_shots: number; model: string } | null | undefined): string => {
  if (!c || !c.shots) return "";
  const known = c.usd ?? c.usd_known ?? 0;
  const money = known ? `about $${known.toFixed(2)}` : "no price known yet";
  return `Making the video for these ${c.shots} shot${c.shots === 1 ? "" : "s"} with ${c.model} would cost ${money}${c.unknown ? ` (${c.unknown} not priced, so this is a minimum)` : ""}${c.lipsync_shots ? `, with a lip-sync pass on ${c.lipsync_shots}` : ""}. Nothing is spent until you confirm in Make.`;
};

/** "about 1,200 credits", or the honest "not priced" when a voice has no price yet. */
export const creditsWords = (credits: number, unpriced: number): string =>
  `${credits ? `about ${credits.toLocaleString("en-US")} credits` : "no credits"}${unpriced ? `, ${unpriced} line${unpriced === 1 ? "" : "s"} not priced` : ""}`;
