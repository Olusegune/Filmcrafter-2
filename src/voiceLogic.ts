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
