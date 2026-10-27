import type { SoundRoute } from "./api";

/** The plain name of how a shot's voice is made, and what the person can do about it. */
export const routeWords = (r: SoundRoute): string => ({
  none: "No voice", voice_over: "Voice-over", needs_voice: "Needs a voice", audio_in: "Model follows the recording", post_sync: "Laid over at export", native: "Model speaks",
} as Record<SoundRoute, string>)[r] ?? r;

/** Faults first: a shot that cannot be made yet, then the ones to look at, then the settled ones. */
export const routeOrder = (r: SoundRoute): number => ({ needs_voice: 0, native: 1, audio_in: 2, post_sync: 3, voice_over: 4, none: 5 } as Record<SoundRoute, number>)[r] ?? 9;

export const settingWords = (s: string): string => (s === "off" ? "Nobody on screen speaks" : s === "on" ? "Someone on screen speaks" : "Automatic");

/** "about 1,200 credits", or the honest "not priced" when a voice has no price yet. */
export const creditsWords = (credits: number, unpriced: number): string =>
  `${credits ? `about ${credits.toLocaleString("en-US")} credits` : "no credits"}${unpriced ? `, ${unpriced} line${unpriced === 1 ? "" : "s"} not priced` : ""}`;
