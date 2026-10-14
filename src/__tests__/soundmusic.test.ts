import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { audioFacts, commaList, MUSIC_FIELDS, PROFILE_FIELDS, SOUND_FIELDS, voiceKey } from "../soundWords";

describe("the words of the Sound & Music tab", () => {
  it("turns a name into the engine's person key", () => {
    expect(voiceKey("Friend #1")).toBe("friend-1");
    expect(voiceKey("CHLOE DAD")).toBe("chloe-dad");
    expect(voiceKey("  Lila ")).toBe("lila");
  });
  it("reads a comma list without blanks", () => {
    expect(commaList("rain, night ,, soft")).toEqual(["rain", "night", "soft"]);
    expect(commaList("")).toEqual([]);
    expect(commaList("Yard\nKitchen")).toEqual(["Yard", "Kitchen"]);
  });
  it("describes an asset's length and the person's decision in plain words", () => {
    expect(audioFacts({ seconds: 1.4, approval: "pending" })).toBe("1.4 s");
    expect(audioFacts({ seconds: 42.5, approval: "approved" })).toBe("43 s · approved");
    expect(audioFacts({ seconds: 96, approval: "rejected" })).toBe("1:36 · rejected");
    expect(audioFacts({ seconds: 3600, approval: "pending" })).toBe("60:00");
  });
  it("offers the style and profile fields the engine keeps, and no others", () => {
    const py = readFileSync("analysis/filmcrafter_engine/bible.py", "utf8");
    const list = (name: string) => [...(new RegExp(`${name} = \\(([^)]*)\\)`).exec(py)![1].matchAll(/"(\w+)"/g))].map((m) => m[1]);
    expect(PROFILE_FIELDS.map((f) => f[0])).toEqual(list("VOICE_PROFILE_FIELDS"));
    const ss = /SOUND_STYLE_FIELDS = \{"sound": \(([^)]*)\),\s*"music": \(([^)]*)\)\}/.exec(py)!;
    expect(SOUND_FIELDS.map((f) => f[0])).toEqual([...ss[1].matchAll(/"(\w+)"/g)].map((m) => m[1]));
    expect(MUSIC_FIELDS.map((f) => f[0])).toEqual([...ss[2].matchAll(/"(\w+)"/g)].map((m) => m[1]));
  });
});

describe("the tab is wired in and promises only what it does (wiring guard)", () => {
  const cast = readFileSync("src/CastWorld.tsx", "utf8");
  const sm = readFileSync("src/SoundMusic.tsx", "utf8");
  it("is a fifth tab of Cast & World after Props, with no count and no second database", () => {
    expect(cast).toMatch(/\{ id: "prop", label: "Props" \}, \{ id: "sound", label: "Sound & Music" \}/);
    expect(cast).toContain("<SoundMusic dir={dir} b={b} run={run} />");
    expect(cast).toContain('t.id !== "sound"');
  });
  it("has the four areas the brief asks for", () => {
    for (const w of ["Voices", "Sound effects", "Music", "Sound style"]) expect(sm).toContain(`label: "${w}"`);
  });
  it("says it costs nothing and never calls a paid or generating action", () => {
    expect(sm).toContain("Nothing on this page costs anything");
    expect(sm).not.toMatch(/castVoice\("(design|design_save|clone|speak|preview)"/);          // choosing a voice goes through the existing VoiceMaker, which asks first
    expect(sm).not.toContain("confirmed: true");
    expect(sm).toContain("import { VoiceMaker }");
  });
  it("approval is the person's act, asked for, and removing says the file is kept", () => {
    expect(sm).toMatch(/await ask\(`Approve /);
    expect(sm).toContain("not deleted");
    expect(sm).toContain("Bring it back");
  });
  it("the shell allows exactly the audio actions the engine has", () => {
    const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
    expect(rust).toMatch(/ACTIONS: \[&str; 6\] = \["list", "import", "update", "approve", "remove", "restore"\]/);
    expect(rust).toContain('"update_sound_style", "set_voice_profile"');
    expect(readFileSync("src/api.ts", "utf8")).toContain('invoke<T>("film_audio"');
  });
});
