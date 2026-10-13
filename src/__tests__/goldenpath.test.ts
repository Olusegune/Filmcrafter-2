import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("@tauri-apps/api/webview", () => ({ getCurrentWebview: () => ({ onDragDropEvent: () => Promise.resolve(() => {}) }) }));

import { goldenNotes } from "../MakeFilm";
import type { MakeShot, VoiceStatus } from "../api";

const shot = (id: string, over: Partial<MakeShot> = {}): MakeShot => ({ id, scene: 1, title: id, duration: 4, framing: "Wide",
  storyboard: { options: [], chosen: null, locked: false }, keyframe: { options: [], chosen: null, locked: false }, video: { takes: [], approved: null }, ...over } as MakeShot);
const shots = (n: number) => Array.from({ length: n }, (_, i) => shot(`S01-0${i + 1}`));
const voices = (missing: number): VoiceStatus => ({ people: 3, recorded: 3 - missing, missing, problems: 0,
  shots: [{ id: "S01-02", scene: 1, title: "", seconds: 4, notes: [], others: [], people: [{ name: "Lila", key: "lila", lines: ["Hi."], recording: null }] }] });

describe("the golden path inside Make film", () => {
  it("asks for one test shot before everything is made, preferring a shot where someone speaks", () => {
    expect(goldenNotes("keyframe", shots(6), voices(1)).test?.id).toBe("S01-02");
    expect(goldenNotes("keyframe", shots(6), null).test?.id).toBe("S01-01");
  });
  it("stops asking once something has been made, and for a very short film", () => {
    const made = shots(6); made[0] = shot("S01-01", { keyframe: { options: [], chosen: "k.png", locked: false } });
    expect(goldenNotes("keyframe", made, null).test).toBeNull();
    expect(goldenNotes("keyframe", shots(3), null).test).toBeNull();
  });
  it("only offers a test video for a shot whose picture is chosen", () => {
    expect(goldenNotes("video", shots(6), null).test).toBeNull();
    const s = shots(6); s[3] = shot("S01-04", { keyframe: { options: [], chosen: "k.png", locked: false } });
    expect(goldenNotes("video", s, null).test?.id).toBe("S01-04");
  });
  it("reminds you to attach the voices before the video, and only then", () => {
    expect(goldenNotes("video", shots(6), voices(2)).voices).toBe(true);
    expect(goldenNotes("video", shots(6), voices(0)).voices).toBe(false);
    expect(goldenNotes("keyframe", shots(6), voices(2)).voices).toBe(false);
    expect(goldenNotes("video", shots(6), null).voices).toBe(false);
  });
  it("is said on the step bar too: voices before video, your recordings laid over their shots at export", () => {
    const hints = readFileSync("src/storyView.ts", "utf8");
    expect(hints).toContain("attach your voices");
    expect(hints).toContain("Your recordings are laid over their shots");
  });
});
