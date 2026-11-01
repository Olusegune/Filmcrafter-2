import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { ALL, FEATURED_IDS, byId, cardMeta, featured, find, presetAspect, stackedNames, TYPES } from "../presetShelf";

describe("the presets Home shows come from the engine's own list", () => {
  it("is the same list, with the same ids, as the engine's file (one set of definitions)", () => {
    const engine = JSON.parse(readFileSync("analysis/filmcrafter_engine/presets_builtin.json", "utf8")).presets as { id: string }[];
    expect(ALL.map((p) => p.id)).toEqual(engine.map((p) => p.id));
    expect(ALL).toHaveLength(37);
  });
  it("has a picture file for every preset, so no card is empty", () => {
    for (const p of ALL) { expect(p.thumbnail, p.id).toBeTruthy(); expect(existsSync(`public/${p.thumbnail}`), p.id).toBe(true); }
  });
  it("features six presets that exist, are different, and are not all one kind", () => {
    expect(featured()).toHaveLength(6);
    expect(new Set(FEATURED_IDS).size).toBe(6);
    expect(new Set(featured().map((p) => p.type)).size).toBeGreaterThan(1);
  });
  it("knows every named kind", () => {
    expect(new Set(ALL.map((p) => p.type))).toEqual(new Set(TYPES));
  });
});

describe("searching and describing presets", () => {
  it("searches the name, the description and the use, ignoring case, and filters by kind", () => {
    expect(find(ALL, "", "all")).toHaveLength(37);
    expect(find(ALL, "MICRO-drama", "all").map((p) => p.id)).toContain("vertical_micro_drama");
    expect(find(ALL, "storybook", "visual").every((p) => p.type === "visual")).toBe(true);
    expect(find(ALL, "zzzz", "all")).toEqual([]);
    expect(find(ALL, "", "performance")).toHaveLength(3);
    expect(find(ALL, "  ", "color").length).toBeGreaterThan(0);
  });
  it("says what a production preset stacks, by name, and what frame shape it asks for", () => {
    const v = byId("vertical_micro_drama")!;
    expect(stackedNames(v)).toContain("Vertical social 9:16");
    expect(presetAspect(v)).toBe("9:16");
    expect(presetAspect(byId("natural_acting")!)).toBeNull();
  });
  it("words a recent film's card from what is known, leaving out what is not", () => {
    expect(cardMeta("Story locked", "9:16", "Today")).toBe("Story locked · 9:16 · Today");
    expect(cardMeta("Screenplay", undefined, "3 days ago")).toBe("Screenplay · 3 days ago");
  });
});

describe("Home reaches nothing it should not", () => {
  it("starts no paid work and calls no provider from the Home screen or its preset sheets", () => {
    for (const f of ["src/Home.tsx", "src/HomePresets.tsx", "src/presetShelf.ts"]) {
      expect(readFileSync(f, "utf8"), f).not.toMatch(/queueRender|\.generate\(|confirmed:\s*true|renderStart|api\.make\(|api\.render/);
    }
  });
});

import { LENGTHS, layerChoices, lengthOptions, lengthWords, presetLength, setupStack } from "../presetShelf";
import { shouldWelcome } from "../homePrefs";

describe("setting a film up from a preset", () => {
  it("offers real layer presets of the right kind, and an empty choice leaves each layer to the preset", () => {
    expect(layerChoices("visual").length).toBeGreaterThan(5);
    expect(layerChoices("performance")).toHaveLength(3);
    expect(layerChoices("editing")).toHaveLength(3);
    expect(layerChoices("color")).toHaveLength(2);
    const v = byId("vertical_micro_drama")!;
    expect(setupStack(v, {})).toEqual(["vertical_micro_drama"]);
    expect(setupStack(v, { visual: "storybook_epic", color: "warm_storybook_balanced" })).toEqual(["vertical_micro_drama", "storybook_epic", "warm_storybook_balanced"]);
    expect(setupStack(v, { acting: "not_a_preset" })).toEqual(["vertical_micro_drama"]);               // an id that is not a preset is never sent
  });
  it("lists lengths in order, adds the preset's own when it is not one of them, and says them in words", () => {
    expect(lengthOptions(null)).toEqual(LENGTHS);
    expect(lengthOptions(90)).toEqual(LENGTHS);
    expect(lengthOptions(240)).toContain(240);
    expect([...lengthOptions(240)].sort((a, b) => a - b)).toEqual(lengthOptions(240));
    expect(lengthWords(90)).toBe("90 seconds");
    expect(lengthWords(300)).toBe("5 minutes");
    expect(lengthWords(150)).toBe("2.5 minutes");
    expect(presetLength(byId("vertical_micro_drama")!)).toBe(90);
    expect(presetLength(byId("natural_acting")!)).toBeNull();
  });
});

describe("the first-launch question", () => {
  it("is asked only of someone with no films who has not answered, once the list has loaded", () => {
    expect(shouldWelcome(0, true, false)).toBe(true);
    expect(shouldWelcome(0, false, false)).toBe(false);          // not before we know whether there are films
    expect(shouldWelcome(3, true, false)).toBe(false);
    expect(shouldWelcome(0, true, true)).toBe(false);
  });
});
