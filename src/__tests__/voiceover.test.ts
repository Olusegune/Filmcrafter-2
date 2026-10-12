import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { MATCH_WORDS, peopleOf, summary, usable } from "../VoiceoverPanel";
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
  it("knows every action the shell allows, and the shell and engine agree", () => {
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    const acts = [...(rust.match(/async fn film_voice[\s\S]*?const ACTIONS: \[&str; \d+\] = \[([^\]]*)\]/)?.[1] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]);
    expect(acts.sort()).toEqual(["import", "match", "remove", "status"]);
    expect(readFileSync("src/api.ts", "utf8")).toContain('invoke<T>("film_voice"');
  });
});
