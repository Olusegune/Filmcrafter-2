import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { isProducerPackage } from "../filmPaths";
import { endNote, money, sectionGroups } from "../SelectReview";
import type { Estimate, Section } from "../api";

const est = (e: Partial<Estimate>): Estimate => ({ provider: "fal", model: "m", shots: 1, usd: null, usd_known: 0, unknown: 0, basis: "", ...e });

describe("isProducerPackage", () => {
  it("recognises Producer packages and nothing else", () => {
    expect(isProducerPackage("C:\\Users\\a\\Type 7.pfproducer")).toBe(true);
    expect(isProducerPackage("C:\\Users\\a\\FILMCRAFTER_Producer_v1.0.0.ZIP")).toBe(true);
    expect(isProducerPackage("C:\\pkg\\manifest.json")).toBe(true);
    expect(isProducerPackage("/Users/a/pkg/manifest.json")).toBe(true);
    expect(isProducerPackage("C:\\a\\project.json")).toBe(false);
    expect(isProducerPackage("C:\\a\\song.mp3")).toBe(false);
    expect(isProducerPackage("C:\\a\\Film.pulse")).toBe(false);
    expect(isProducerPackage("C:\\a\\notmanifest.json")).toBe(false);
  });
});

describe("money", () => {
  it("shows the price the way each provider bills", () => {
    expect(money(null, "fal")).toBe("…");
    expect(money(est({ usd: 0.4 }), "comfyui")).toBe("free");
    expect(money(est({ kie_credits_est: 11.6 }), "kie")).toBe("≈ 12 Kie credits");
    expect(money(est({ usd: 1.234 }), "fal")).toBe("≈ $1.23");
    expect(money(est({ usd: null, usd_known: 0.5, unknown: 2 }), "fal")).toBe("≈ $0.50 + 2 unpriced");
    expect(money(est({ usd: null, usd_known: 0, unknown: 9 }), "openai")).toMatch(/not known/);
  });
});

describe("sectionGroups", () => {
  const sec = (label: string, start: number, end: number): Section => ({ label, start, end, group: "", energy: 0, mood: "" });
  it("merges neighbours, numbers repeats and drops sections without shots", () => {
    const s = [sec("INTRO", 0, 5), sec("VERSE", 5, 10), sec("VERSE", 10, 20), sec("CHORUS", 20, 30), sec("VERSE", 30, 40), sec("OUTRO", 40, 50)];
    const shots = [{ start: 0, end: 4 }, { start: 12, end: 14 }, { start: 22, end: 26 }, { start: 33, end: 36 }];
    expect(sectionGroups(s, shots).map((g) => g.label)).toEqual(["Intro", "Verse 1", "Chorus", "Verse 2"]);
    expect(sectionGroups(s, shots)[1]).toMatchObject({ start: 5, end: 20 });
  });
});

describe("endNote", () => {
  it("says which shots switch model and which can't use their end frame", () => {
    expect(endNote(null)).toBe("");
    expect(endNote(est({}))).toBe("");
    const e = { ...est({}), end_frame_models: [{ shot: "S01-02", title: "Kling 3 Pro" }], end_frame_unsupported: ["S01-05"] } as Estimate;
    expect(endNote(e)).toContain("S01-02 → Kling 3 Pro");
    expect(endNote(e)).toContain("won't be sent for: S01-05");
  });
});
