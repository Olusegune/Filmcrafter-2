import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { encodeWav, lineFor, nextUnvoiced, peaksOf, personAt, trimSilence } from "../voiceLogic";
import type { VoiceShot } from "../api";

describe("the waveform outline of a recording", () => {
  it("takes the loudest sample of each slice and scales the loudest slice to 1", () => {
    const p = peaksOf([0, 0.1, -0.5, 0.2, 0, 0, 0.25, -0.1], 4);
    expect(p).toEqual([0.2, 1, 0, 0.5]);
  });
  it("keeps silence at zero, handles an empty file and gives as many bars as asked", () => {
    expect(peaksOf(new Float32Array(100), 8)).toEqual(new Array(8).fill(0));
    expect(peaksOf([], 5)).toEqual([0, 0, 0, 0, 0]);
    expect(peaksOf([0.3, 0.6], 0)).toEqual([]);
    expect(peaksOf(new Float32Array(10), 96)).toHaveLength(96);
  });
  it("is drawn beside each recording's player, and the shell may read the user's own files to draw it", () => {
    expect(readFileSync("src/VoiceoverPanel.tsx", "utf8")).toContain("<Waveform src=");
    const csp = JSON.parse(readFileSync("src-tauri/tauri.conf.json", "utf8")).app.security.csp["connect-src"] as string;
    expect(csp).toContain("asset:");
    expect(csp).not.toContain("*");
  });
});

describe("big films", () => {
  it("skip drawing the Make cards and the shot-list scenes that are out of view", () => {
    const css = readFileSync("src/film.css", "utf8");
    expect(css).toMatch(/\.mk-card \{ content-visibility: auto; contain-intrinsic-size: auto \d+px; \}/);
    expect(css).toMatch(/\.sl-scene \{ content-visibility: auto; contain-intrinsic-size: auto \d+px; \}/);
  });
});

const shot = (id: string, people: [string, boolean, string[]?][]): VoiceShot => ({ id, scene: 1, title: "", seconds: 3, others: [], notes: [],
  people: people.map(([name, rec, lines]) => ({ name, key: name.toLowerCase(), lines: lines ?? [], recording: rec ? { file: "x", name: "x", seconds: 1, rms_db: -20, peak_db: -3 } : null })) });

describe("recording in the app", () => {
  it("makes a real mono 16-bit WAV: header, rate, length and clipped samples", () => {
    const w = encodeWav([0, 0.5, -0.5, 2, -2], 44100);
    const v = new DataView(w.buffer);
    expect(String.fromCharCode(...w.slice(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...w.slice(8, 12))).toBe("WAVE");
    expect(v.getUint16(22, true)).toBe(1);               // mono
    expect(v.getUint32(24, true)).toBe(44100);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getUint32(40, true)).toBe(10);
    expect(w.length).toBe(44 + 10);
    expect(v.getInt16(44 + 2 * 3, true)).toBe(32767);    // 2 clipped to full scale
    expect(v.getInt16(44 + 2 * 4, true)).toBe(-32768);
  });
  it("trims silence from both ends, keeps a breath, and leaves an all-quiet take alone", () => {
    const rate = 1000, x = new Float32Array(3000);
    for (let i = 1000; i < 1500; i++) x[i] = 0.4;
    const t = trimSilence(x, rate, -45, 0.1);
    expect(t.length).toBeGreaterThanOrEqual(500);
    expect(t.length).toBeLessThanOrEqual(500 + 2 * 100 + 60);
    expect(Math.max(...t)).toBeCloseTo(0.4);
    const quiet = new Float32Array(500);
    expect(trimSilence(quiet, rate)).toBe(quiet);
  });
  it("moves on to the next shot with someone still to record, wrapping round, and says when none is left", () => {
    const shots = [shot("S01-01", [["Lila", true]]), shot("S01-02", [["Lila", false]]), shot("S01-03", [["Chloe", true], ["Lila", false]]), shot("S01-04", [])];
    expect(nextUnvoiced(shots)?.id).toBe("S01-02");
    expect(nextUnvoiced(shots, "S01-02")?.id).toBe("S01-03");
    expect(nextUnvoiced(shots, "S01-03")?.id).toBe("S01-02");
    expect(nextUnvoiced([shot("S01-01", [["Lila", true]])])).toBeNull();
  });
  it("shows the line of the person who is speaking, and which person's name a dropped file is over", () => {
    const s = shot("S01-02", [["Lila", false, ["She eats", "the weirdest stuff."]], ["Chloe", false, ["Ew."]]]);
    expect(lineFor(s, "Lila")).toBe("She eats the weirdest stuff.");
    expect(lineFor(s, "Nobody")).toBe("");
    const chips = [{ who: "Lila", left: 0, top: 0, right: 100, bottom: 20 }, { who: "Chloe", left: 0, top: 24, right: 100, bottom: 44 }];
    expect(personAt(chips, { x: 50, y: 30 })).toBe("Chloe");
    expect(personAt(chips, { x: 50, y: 22 })).toBeNull();      // between the two: the whole shot, so the match table decides
  });
  it("is reachable from a card, the Voiceover rows and its missing-voices button; the shell saves only a WAV", () => {
    expect(readFileSync("src/VoiceChip.tsx", "utf8")).toContain("data-voice-person");
    expect(readFileSync("src/VoiceChip.tsx", "utf8")).toContain("<VoiceRecorder");
    const panel = readFileSync("src/VoiceoverPanel.tsx", "utf8");
    expect(panel).toContain("Record the missing voices");
    expect(panel).toContain("<VoiceRecorder");
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    expect(rust).toMatch(/fn save_voice_take/);
    expect(rust).toContain("wav_ok(bytes)");
    expect(rust).toContain("MAX_TAKE_BYTES");
    expect(rust).toMatch(/invoke_handler[\s\S]*save_voice_take/);
  });
  it("tells you what to do when the microphone is blocked or missing", () => {
    const src = readFileSync("src/VoiceRecorder.tsx", "utf8");
    expect(src).toContain("NotAllowedError");
    expect(src).toContain("Privacy & security");
    expect(src).toContain("NotFoundError");
  });
});
