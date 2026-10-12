import type { VoiceMatch, VoiceShot, VoiceStatus } from "./api";

export const AUDIO = ["wav", "mp3", "m4a", "flac", "aac", "ogg"];
export const FILTERS = [{ name: "Recordings", extensions: AUDIO }];

/** What a row of the match table will do, in words. */
export const MATCH_WORDS: Record<VoiceMatch["status"], string> = {
  ok: "Ready", replace: "Replaces the recording now there", ambiguous: "Who is this?", no_shot: "Which shot?", no_speaker: "Who is speaking?",
  not_in_shot: "Not in this shot", duplicate: "Already in this batch", bad_file: "Can't use this file",
};
/** A row the person can confirm as it stands. */
export const usable = (r: VoiceMatch) => (r.status === "ok" || r.status === "replace") && !!r.shot && !!r.speaker;

/** The people a recording can be for in a shot: those who speak, then those who are only there. */
export const peopleOf = (s: VoiceShot | undefined): string[] => (s ? [...(s.people ?? []).map((p) => p.name), ...(s.others ?? [])] : []);

/** Only audio files are taken from a drop. */
export const audioFiles = (paths: string[]): string[] => paths.filter((p) => new RegExp(`\\.(${AUDIO.join("|")})$`, "i").test(p));

/** How much of the shot the recordings fill, as a percentage for a bar, and whether they overflow it (the shot is then lengthened). */
export const fill = (s: Pick<VoiceShot, "people" | "seconds">): { pct: number; over: boolean; total: number } => {
  const recs = (s.people ?? []).map((p) => p.recording?.seconds ?? 0).filter((x) => x > 0);
  const total = recs.reduce((a, b) => a + b, 0) + Math.max(0, recs.length - 1) * 0.25;
  return { total, pct: s.seconds > 0 ? Math.min(100, Math.round((total / s.seconds) * 100)) : 0, over: total > s.seconds + 0.001 };
};

export const summary = (st: VoiceStatus) => st.people === 0 ? "Nobody speaks in this film yet." : st.missing === 0 ? `Every voice is recorded (${st.recorded}).` : `${st.recorded} of ${st.people} voices recorded; ${st.missing} still to attach.`;


/** The outline of a recording for a waveform: the loudest sample in each of `n` equal slices, scaled so the loudest slice is 1 (silence stays 0). */
export const peaksOf = (samples: ArrayLike<number>, n: number): number[] => {
  if (n <= 0) return [];
  const out = new Array<number>(n).fill(0);
  const len = samples.length;
  if (len === 0) return out;
  for (let i = 0; i < n; i++) {
    const a = Math.floor((i * len) / n), b = Math.max(a + 1, Math.floor(((i + 1) * len) / n));
    let m = 0;
    for (let j = a; j < b && j < len; j++) { const v = Math.abs(samples[j]); if (v > m) m = v; }
    out[i] = m;
  }
  const top = Math.max(...out);
  return top > 0 ? out.map((v) => v / top) : out;
};

/** A mono 16-bit PCM WAV file from samples in -1..1. */
export const encodeWav = (samples: ArrayLike<number>, rate: number): Uint8Array => {
  const n = samples.length;
  const out = new Uint8Array(44 + n * 2);
  const v = new DataView(out.buffer);
  const txt = (at: number, s: string) => { for (let i = 0; i < s.length; i++) out[at + i] = s.charCodeAt(i); };
  txt(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); txt(8, "WAVE"); txt(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  txt(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) { const x = Math.max(-1, Math.min(1, samples[i])); v.setInt16(44 + i * 2, x < 0 ? Math.round(x * 32768) : Math.round(x * 32767), true); }
  return out;
};

/** Cuts the quiet from the start and end of a take (a breath of `padSeconds` is kept on each side). Silence is below `floorDb` (relative to full scale) over a short window. */
export const trimSilence = (samples: Float32Array, rate: number, floorDb = -45, padSeconds = 0.12): Float32Array => {
  const win = Math.max(1, Math.round(rate * 0.02)), floor = Math.pow(10, floorDb / 20);
  const loud = (at: number) => { let m = 0; for (let i = at; i < Math.min(samples.length, at + win); i++) m = Math.max(m, Math.abs(samples[i])); return m > floor; };
  let a = 0, b = samples.length;
  while (a < b && !loud(a)) a += win;
  if (a >= b) return samples;                                   // all quiet: leave it for the engine to refuse with its own words
  while (b > a && !loud(Math.max(0, b - win))) b -= win;
  const pad = Math.round(rate * padSeconds);
  return samples.slice(Math.max(0, a - pad), Math.min(samples.length, b + pad));
};

/** The next shot that still has someone speaking with no recording, after `after` (wrapping round to the start); null when every voice is recorded. */
export const nextUnvoiced = (shots: VoiceShot[], after?: string): VoiceShot | null => {
  const open = (s: VoiceShot) => (s.people ?? []).some((p) => !p.recording);
  const i = after ? shots.findIndex((s) => s.id === after) : -1;
  return [...shots.slice(i + 1), ...shots.slice(0, Math.max(0, i + 1))].find(open) ?? null;
};

/** Which of a card's people is under the pointer: the rectangles are those of the people's chips, `at` is the pointer. */
export const personAt = (chips: { who: string; left: number; top: number; right: number; bottom: number }[], at: { x: number; y: number }): string | null =>
  chips.find((c) => at.x >= c.left && at.x <= c.right && at.y >= c.top && at.y <= c.bottom)?.who ?? null;

/** The first line a person has in a shot, for reading from: what they say, in the order the shot has it. */
export const lineFor = (s: VoiceShot | undefined, who: string): string => ((s?.people ?? []).find((p) => p.name === who)?.lines ?? []).join(" ");
