import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
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

describe("custom voices with ElevenLabs", () => {
  it("says the price in characters and credits, never dollars, and says a repeat is free", async () => {
    vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
    vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
    const { priceWords } = await import("../CastVoices");
    expect(priceWords({ characters: 1240, credits: 620 })).toContain("1,240 characters, about 620 credits of your ElevenLabs plan");
    expect(priceWords({ characters: 1240, credits: 620 })).not.toContain("$");
    expect(priceWords({ characters: 0, credits: 0 })).toContain("costs nothing");
    expect(priceWords({ characters: 1, credits: 1 })).toContain("1 character,");
  });
  it("asks for a yes before speaking, hears options only after asking, needs consent to clone, and is reachable from the Voiceover screen, cards and the shell", () => {
    const src = readFileSync("src/CastVoices.tsx", "utf8");
    expect(src.indexOf("await ask(")).toBeGreaterThan(-1);
    expect(src.indexOf("await ask(")).toBeLessThan(src.indexOf('castVoice("speak"'));          // the yes is asked before the first spoken line is sent
    expect(src).toContain("confirmed: true");
    expect(src).toContain("Hear options");
    expect(src).toMatch(/disabled=\{[^}]*!consent/);
    expect(src).toContain("consent,");
    expect(readFileSync("src/VoiceoverPanel.tsx", "utf8")).toContain("<CastVoices");
    expect(readFileSync("src/VoiceChip.tsx", "utf8")).toContain("speakLine(");
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    expect(rust).toMatch(/fn film_cast_voice/);
    expect(rust).toMatch(/invoke_handler[\s\S]*film_cast_voice/);
    expect(rust).toContain('("ELEVENLABS_KEY"');
  });
  it("shows a spoken line as spoken by ElevenLabs, so it is not mistaken for your own voice", () => {
    expect(readFileSync("src/VoiceoverPanel.tsx", "utf8")).toContain("spoken by ElevenLabs");
  });
});

describe("the Home card", () => {
  it("is snugger than before: a short card with modest padding", () => {
    const css = readFileSync("src/film.css", "utf8");
    const last = [...css.matchAll(/\.dropcard\.story \{ min-height: (\d+)px; padding: (\d+)px 28px (\d+)px;/g)].pop()!;
    expect(Number(last[1])).toBeLessThanOrEqual(460);
    expect(Number(last[2])).toBeLessThanOrEqual(60);
  });
});

describe("voices on the timeline and the line studio", () => {
  it("lists who speaks in the order they first do, and lays two people in one shot one after the other", async () => {
    const { speakers, offsetIn } = await import("../VoiceLanes");
    const sh = [shot("S01-01", [["Lila", true]]), shot("S01-02", [["Chloe", true], ["Lila", true]]), shot("S01-03", [["Ethan", false]])];
    expect(speakers({ shots: sh, people: 4, recorded: 3, missing: 1, problems: 0 }).map((p) => p.name)).toEqual(["Lila", "Chloe", "Ethan"]);
    expect(speakers(null)).toEqual([]);
    expect(offsetIn(sh[1], "chloe")).toBe(0);
    expect(offsetIn(sh[1], "lila")).toBeCloseTo(1.25);          // Chloe's 1 s and the engine's quarter-second gap
    expect(offsetIn(sh[2], "ethan")).toBe(0);
  });
  it("puts a lane for each speaker under the shots (not in the compact timeline), and a clip is itself one person's drop target", () => {
    const studio = readFileSync("src/Studio.tsx", "utf8");
    expect(studio).toContain("<VoiceLanes");
    expect(studio).toMatch(/const voiceN = compact \|\| !voiceFilm \? 0/);
    expect(studio).toMatch(/Math\.max\(transTop \+ 28 \+ voiceH, 0\)/);
    const lanes = readFileSync("src/VoiceLanes.tsx", "utf8");
    expect(lanes).toContain("data-shot-id={s.id} data-voice-person={p.name}");
    expect(readFileSync("src/voiceHooks.ts", "utf8")).toContain('card.matches("[data-voice-person]")');
  });
  it("offers [tags] only for the models that read them, matching the engine's list, and never edits the shot's dialogue", () => {
    const studio = readFileSync("src/LineStudio.tsx", "utf8");
    const screen = /const TAGGED = new Set\(\[([^\]]+)\]\)/.exec(studio)![1].match(/"(\w+)"/g)!.map((x) => x.replace(/"/g, "")).sort();
    const engine = readFileSync("analysis/filmcrafter_engine/cast_voice.py", "utf8");
    const py = /TAGGED = \{([^}]+)\}/.exec(engine)![1].match(/"(\w+)"/g)!.map((x) => x.replace(/"/g, "")).sort();
    expect(screen).toEqual(py);
    expect(py).toContain("eleven_v4");
    expect(studio).toContain("The film's written dialogue is not changed");
    expect(studio.indexOf("await ask(")).toBeLessThan(studio.indexOf('castVoice("speak"'));       // the yes comes before the first spoken line is sent
    expect(studio).toContain("switching between them is free");
  });
  it("can be opened from the timeline, a shot card and the Voiceover rows, and the shell lets takes through", () => {
    for (const f of ["src/VoiceLanes.tsx", "src/VoiceChip.tsx", "src/VoiceoverPanel.tsx"]) expect(readFileSync(f, "utf8")).toContain("<LineStudio");
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    expect(rust).toMatch(/ACTIONS: \[&str; \d+\] = \["status", "library", "set", "clear", "design", "design_save", "clone", "estimate", "speak", "preview", "takes", "use_take", "sample"\]/);
  });
});

describe("library voice samples play", () => {
  it("are fetched into the film first and played locally (the app's policy only plays local audio), never from a remote link", () => {
    const src = readFileSync("src/CastVoices.tsx", "utf8");
    expect(src).toContain("function SamplePlayer");
    expect(src).toContain('castVoice<{ file: string }>("sample"');
    expect(src).not.toMatch(/<audio[^>]*src=\{v\.preview_url\}/);
    const csp = JSON.parse(readFileSync("src-tauri/tauri.conf.json", "utf8")).app.security.csp["media-src"] as string;
    expect(csp).not.toMatch(/https?:\/\/(?!asset\.localhost)/);       // no remote audio was let in to fix it
  });
});
