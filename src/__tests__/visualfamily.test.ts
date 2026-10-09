import { describe, expect, it } from "vitest";
import { colours, paletteBand, swatch } from "../colorWords";
import { groupRuns, runName, runTick } from "../lightingView";
import { readTileSize, sizeText, stepIndex, TILE_MIN, writeTileSize } from "../cleanupView";
import type { LightShot } from "../api";

const hsl = (c: string) => { const m = /hsl\((\d+), (\d+)%, (\d+)%\)/.exec(c); return m ? m.slice(1).map(Number) : null; };

describe("colour names drawn as colours", () => {
  it("gives a named colour a colour of that family", () => {
    const [h] = hsl(swatch("red"))!;
    expect(h < 15 || h > 345).toBe(true);
    const [bh] = hsl(swatch("blue"))!;
    expect(bh).toBeGreaterThan(200); expect(bh).toBeLessThan(240);
    expect(swatch("jade")).not.toBe(swatch("gold"));
  });
  it("lets a describing word change the colour: dusty is greyer, deep is darker, pale is lighter", () => {
    const [, s0, l0] = hsl(swatch("orange"))!;
    const [, sd, ] = hsl(swatch("dusty orange"))!;
    const [, , ld] = hsl(swatch("deep orange"))!;
    const [, , lp] = hsl(swatch("pale orange"))!;
    expect(sd).toBeLessThan(s0); expect(ld).toBeLessThan(l0); expect(lp).toBeGreaterThan(l0);
  });
  it("reads the colour word wherever it sits in the phrase", () => {
    expect(swatch("faded denim")).toBe(colours("faded denim")[0]);
    expect(colours("ink black")).toHaveLength(1);
    expect(hsl(swatch("neon pink"))![1]).toBe(100);
  });
  it("draws a phrase that names several colours as all of them", () => {
    expect(colours("black and white")).toHaveLength(2);
    expect(colours("primary accents")).toHaveLength(3);
    expect(swatch("black and white")).toContain("linear-gradient");
  });
  it("gives a word it does not know a calm colour of its own, always the same one", () => {
    const a = swatch("depends on the location");
    expect(a).toBe(swatch("depends on the location"));
    expect(hsl(a)).not.toBeNull();
    expect(swatch("zzz qqq")).not.toBe(swatch("another thing"));
    expect(hsl(swatch("")) ).not.toBeNull();
  });
  it("never throws for odd input", () => {
    for (const v of [undefined, null, 3, "", "   ", "!!!", "a".repeat(500)] as unknown[]) expect(() => swatch(v as string)).not.toThrow();
  });
  it("makes a band of crisp blocks, one per colour, and copes with none or one", () => {
    const b = paletteBand(["amber", "magenta neon", "deep teal"]);
    expect(b.startsWith("linear-gradient(90deg")).toBe(true);
    expect(b.match(/hsl\(/g)).toHaveLength(3);                       // one stop per colour, each with the stretch it covers
    expect(b).toContain("0% 33%"); expect(b).toContain("67% 100%");
    expect(paletteBand([])).toContain("linear-gradient");
    expect(paletteBand(["gold"])).toBe(swatch("gold"));
    expect(paletteBand(["a", "b", "c", "d", "e", "f", "g"], 4).match(/hsl\(/g)).toHaveLength(4);
    expect(paletteBand(["black and white"]).match(/#/g)).toHaveLength(2);   // a phrase counts as its colours
  });
});

const light = (shot: string, label: string, design: string, kelvin: number, over: Partial<LightShot> = {}): LightShot => ({ shot, scene: 1, start: 0, end: 2, section: "", mood: label.toLowerCase(), label, valence: 0, arousal: 0, intensity: 0, why: "", design: { label: design, kelvin, level: 1, wording: "" }, ...over } as unknown as LightShot);

describe("runs of the same light", () => {
  const rows = [light("S01", "Calm", "Golden hour", 5600), light("S02", "Calm", "Golden hour", 5600), light("S03", "Tension", "Single hard key", 5600), light("S04", "Calm", "Golden hour", 5600)];
  it("joins neighbours with exactly the same mood and light, and only neighbours", () => {
    const runs = groupRuns(rows);
    expect(runs.map((r) => r.shots.map((s) => s.shot))).toEqual([["S01", "S02"], ["S03"], ["S04"]]);
  });
  it("tells a different temperature, a different level and a chosen light apart", () => {
    expect(groupRuns([light("A", "Calm", "Golden hour", 5600), light("B", "Calm", "Golden hour", 4500)])).toHaveLength(2);
    const hard = light("B", "Calm", "Golden hour", 5600); hard.design.level = 3;
    expect(groupRuns([light("A", "Calm", "Golden hour", 5600), hard])).toHaveLength(2);
    expect(groupRuns([light("A", "Calm", "Golden hour", 5600), light("B", "Calm", "Golden hour", 5600, { user_set: true })])).toHaveLength(2);
  });
  it("remembers whether a run was held steady or chosen by the person", () => {
    const [r] = groupRuns([light("A", "Calm", "Golden hour", 5600), light("B", "Calm", "Golden hour", 5600, { held: true })]);
    expect(r.held).toBe(true); expect(r.own).toBe(false);
    expect(groupRuns([light("A", "Calm", "Golden hour", 5600, { user_set: true })])[0].own).toBe(true);
  });
  it("names a run by its first and last shot", () => {
    const runs = groupRuns(rows);
    expect(runName(runs[0])).toBe("S01 – S02");
    expect(runName(runs[1])).toBe("S03");
    expect(groupRuns([])).toEqual([]);
  });
  it("says how much of a run is ticked", () => {
    const [r] = groupRuns(rows);
    expect(runTick(r, new Set())).toBe("none");
    expect(runTick(r, new Set(["S01"]))).toBe("some");
    expect(runTick(r, new Set(["S01", "S02", "S09"]))).toBe("all");
  });
});

describe("Clean up sizing and browsing", () => {
  const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); } }; };
  it("shows large pictures unless the person chose otherwise, and remembers the choice", () => {
    const s = memory();
    expect(readTileSize(s)).toBe("large");
    writeTileSize("small", s);
    expect(readTileSize(s)).toBe("small");
    s.setItem("pf-cleanup-size", "enormous");
    expect(readTileSize(s)).toBe("large");
  });
  it("copes with storage that is missing or blocked", () => {
    const blocked = { getItem: () => { throw new Error("no"); }, setItem: () => { throw new Error("no"); } };
    expect(readTileSize(blocked)).toBe("large");
    expect(() => writeTileSize("medium", blocked)).not.toThrow();
    expect(readTileSize(null)).toBe("large");
  });
  it("makes each size bigger than the one before, with large clearly larger than the old tile", () => {
    expect(TILE_MIN.small).toBeLessThan(TILE_MIN.medium);
    expect(TILE_MIN.medium).toBeLessThan(TILE_MIN.large);
    expect(TILE_MIN.large).toBeGreaterThanOrEqual(2 * 150);
  });
  it("steps through the files, round the ends, and says when there are none", () => {
    expect(stepIndex(0, 1, 3)).toBe(1);
    expect(stepIndex(2, 1, 3)).toBe(0);
    expect(stepIndex(0, -1, 3)).toBe(2);
    expect(stepIndex(0, 1, 0)).toBe(-1);
    expect(stepIndex(-1, 1, 3)).toBe(0);
  });
  it("writes file sizes the way the screen does", () => {
    expect(sizeText(500)).toBe("1 KB");
    expect(sizeText(12_400_000)).toBe("12 MB");
    expect(sizeText(2_400_000_000)).toBe("2.4 GB");
  });
});
