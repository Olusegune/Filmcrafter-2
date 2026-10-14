import type { AudioAsset } from "./api";

/** The same key the engine uses for a person (voiceover.key_of): 'Friend #1' -> 'friend-1'. */
export const voiceKey = (name: string) => String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

/** "rain, night ,, soft" -> ["rain", "night", "soft"] */
export const commaList = (text: string): string[] => String(text || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

/** A short line of facts about an asset: its length and approval, in words. */
export function audioFacts(a: Pick<AudioAsset, "seconds" | "approval">): string {
  const s = Math.max(0, Number(a.seconds) || 0);
  const len = s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  return a.approval === "approved" ? `${len} · approved` : a.approval === "rejected" ? `${len} · rejected` : len;
}

export const SOUND_FIELDS: [string, string, string][] = [
  ["philosophy", "The idea of the sound", "Quiet and close, like being in the room. Or big and stylised."],
  ["realism", "Real or stylised", "Everyday sounds as they are, or exaggerated for the story."],
  ["ambience", "Ambience", "How much of the world is always heard: a busy street, or nearly silence."],
  ["dialogue", "Dialogue first", "How clear the voices must stay above everything else."],
  ["silence", "When to be silent", "Moments where no sound at all is stronger."],
];
export const MUSIC_FIELDS: [string, string, string][] = [
  ["genre", "Genre", "Chamber, folk, electronic, orchestral…"],
  ["instrumentation", "Instruments", "Solo piano, strings, a music box…"],
  ["mood", "Mood", "Tender, uneasy, hopeful."],
  ["tempo", "Tempo", "Slow and unhurried, or driving."],
  ["influences", "Influences", "Describe the qualities you want, not a piece to copy."],
  ["palette", "Emotional palette", "The feelings the music moves between."],
  ["motifs", "Recurring motifs", "A theme that returns, and who it belongs to."],
  ["intensity", "Intensity", "How loud and present the music is, scene by scene."],
  ["silence", "Where music should stay out", "Grief, quiet kitchens, the last shot."],
];
export const PROFILE_FIELDS: [string, string, string][] = [
  ["description", "In a sentence", "Warm, a little tired, kind."],
  ["age_range", "Age and range", "Thirties, low and steady."],
  ["accent", "Accent and language", "Northern English."],
  ["timbre", "Texture of the voice", "Breathy, bright, gravelly."],
  ["pace", "Speaking pace", "Slow, with pauses."],
  ["emotional_range", "Emotional range", "Mostly restrained; breaks once."],
  ["delivery", "Usual delivery", "Quiet, understated."],
  ["notes", "Notes for a performance", "Never shouts; laughs when nervous."],
];
