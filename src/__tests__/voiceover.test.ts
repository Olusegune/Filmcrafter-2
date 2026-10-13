import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { MATCH_WORDS, audioFiles, fill, peopleOf, summary, usable } from "../VoiceoverPanel";
import type { VoiceMatch, VoiceShot, VoiceStatus } from "../api";

const row = (over: Partial<VoiceMatch>): VoiceMatch => ({ file: "C:/v/CHLOE_S01-04.wav", name: "CHLOE_S01-04.wav", shot: "S01-04", speaker: "Chloe", status: "ok", note: "", seconds: 2.4, ...over });
const st = (over: Partial<VoiceStatus>): VoiceStatus => ({ shots: [], people: 5, recorded: 2, missing: 3, problems: 0, ...over });

describe("voiceover screen logic", () => {
  it("has plain words for every way a file can be matched, matching the engine's statuses", () => {
    const engine = readFileSync("analysis/filmcrafter_engine/voiceover.py", "utf8");
    const statuses = [...engine.matchAll(/status="(\w+)"/g)].map((m) => m[1]);
    for (const s of new Set(statuses)) expect(Object.keys(MATCH_WORDS), s).toContain(s);
    for (const w of Object.values(MATCH_WORDS)) expect(w.length).toBeGreaterThan(3);
  });
  it("attaches only rows that are ready, with a shot and a person", () => {
    expect(usable(row({}))).toBe(true);
    expect(usable(row({ status: "replace" }))).toBe(true);
    for (const status of ["ambiguous", "no_shot", "no_speaker", "not_in_shot", "duplicate", "bad_file"] as const) expect(usable(row({ status })), status).toBe(false);
    expect(usable(row({ speaker: null }))).toBe(false);
    expect(usable(row({ shot: null }))).toBe(false);
  });
  it("offers the people who speak in a shot first, then the ones who are only there", () => {
    const s = { id: "S01-04", scene: 1, title: "", seconds: 3, notes: [], others: ["Chloe"], people: [{ name: "Lila", key: "lila", lines: ["x"], recording: null }] } as VoiceShot;
    expect(peopleOf(s)).toEqual(["Lila", "Chloe"]);
    expect(peopleOf(undefined)).toEqual([]);
    expect(peopleOf({ id: "S01-04" } as VoiceShot)).toEqual([]);                      // a reply with a part missing does not crash the screen
  });
  it("says in a sentence how far the recording has got", () => {
    expect(summary(st({ people: 0, recorded: 0, missing: 0 }))).toMatch(/Nobody speaks/);
    expect(summary(st({}))).toBe("2 of 5 voices recorded; 3 still to attach.");
    expect(summary(st({ people: 4, recorded: 4, missing: 0 }))).toBe("Every voice is recorded (4).");
  });
  it("takes only audio files from a drop", () => {
    expect(audioFiles(["C:/a/CHLOE_S01-04.WAV", "C:/a/notes.txt", "C:/a/x.mp3", "C:/a/pic.png", "C:/a/y.M4A", "C:/a/z.wav.exe"])).toEqual(["C:/a/CHLOE_S01-04.WAV", "C:/a/x.mp3", "C:/a/y.M4A"]);
    expect(audioFiles([])).toEqual([]);
  });
  it("shows how much of a shot its recordings fill, with the gap between people", () => {
    const rec = (n: number) => ({ file: "f", name: "n", seconds: n, rms_db: -20, peak_db: -3 });
    const p = (n: number | null) => ({ name: "x", key: "x", lines: [], recording: n == null ? null : rec(n) });
    expect(fill({ seconds: 4, people: [p(2)] })).toEqual({ total: 2, pct: 50, over: false });
    expect(fill({ seconds: 4, people: [p(2), p(1.5)] }).total).toBe(3.75);
    expect(fill({ seconds: 3, people: [p(2), p(1.5)] })).toMatchObject({ pct: 100, over: true });
    expect(fill({ seconds: 3, people: [p(null)] })).toEqual({ total: 0, pct: 0, over: false });
    expect(fill({ seconds: 0, people: [p(1)] }).pct).toBe(0);
  });
  it("knows every action the shell allows, and the shell and engine agree", () => {
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    const acts = [...(rust.match(/async fn film_voice[\s\S]*?const ACTIONS: \[&str; \d+\] = \[([^\]]*)\]/)?.[1] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]);
    expect(acts.sort()).toEqual(["import", "match", "remove", "status"]);
    expect(readFileSync("src/api.ts", "utf8")).toContain('invoke<T>("film_voice"');
  });
});

describe("the voiceover can be found", () => {
  it("opens from the Studio's bar and the Export screen (so also in Simple mode, where the Shots stage is hidden), as well as from Shots", () => {
    expect(readFileSync("src/Studio.tsx", "utf8")).toMatch(/isFilm && <button.*setVoiceOpen.*>Voiceover</);
    expect(readFileSync("src/MakeFilm.tsx", "utf8")).toMatch(/setVoiceOpen\(true\)\}>Voiceover…/);
    expect(readFileSync("src/ShotLab.tsx", "utf8")).toContain("Voiceover</button>");
  });
});

describe("voice at the card and the timeline", () => {
  it("is on the Make film cards, the timeline shot cards and the Studio's shot panel, and files can be dropped on a card", () => {
    expect(readFileSync("src/MakeFilm.tsx", "utf8")).toMatch(/<VoiceChip dir=\{dir\} shotId=\{s\.id\} compact/);
    expect(readFileSync("src/MakeFilm.tsx", "utf8")).toContain('data-shot-id={s.id}');
    const board = readFileSync("src/Board.tsx", "utf8");
    expect(board).toContain("data-shot-id={s.id}");
    expect(board).toContain("kc-voice");
    const studio = readFileSync("src/Studio.tsx", "utf8");
    expect(studio).toContain("<ShotVoice dir={filmDirOfRender(project.dir)} shotId={s.id}");          // the voices are made in the Video tab (they were under Shot)
    expect(studio).toContain("useVoiceDrop(");
    expect(readFileSync("src/voiceHooks.ts", "utf8")).toContain('closest("[data-shot-id]")');
  });
});
