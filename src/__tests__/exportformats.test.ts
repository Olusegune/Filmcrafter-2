import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { EXPORT_FORMATS, formatFor } from "../exportFormats";

const py = readFileSync("analysis/filmcrafter_engine/export.py", "utf8");
const story = readFileSync("analysis/filmcrafter_engine/story.py", "utf8");

describe("export formats", () => {
  it("has one format for every frame shape a film can take, so none is missing from the list", () => {
    const shapes = (story.match(/^ASPECTS = \(([^)]*)\)/m)?.[1] ?? "").match(/"([^"]+)"/g)!.map((x) => x.replace(/"/g, ""));
    expect(shapes.length).toBe(9);
    for (const s of shapes) {
      const f = EXPORT_FORMATS.find((x) => x.id === formatFor(s));
      expect(f, s).toBeTruthy();
      expect(f!.sub.startsWith(s), s).toBe(true);
    }
    expect(new Set(shapes.map(formatFor)).size).toBe(shapes.length);
  });
  it("uses only ids and sizes the engine knows", () => {
    for (const f of EXPORT_FORMATS) {
      const m = py.match(new RegExp(`"${f.id}": \\{"label": "[^"]+", "w": (\\d+), "h": (\\d+)\\}`));
      expect(m, f.id).toBeTruthy();
      expect(f.sub.endsWith(`${m![1]}×${m![2]}`), f.id).toBe(true);
    }
  });
  it("falls back to YouTube for a shape it does not know", () => {
    expect(formatFor("5:4")).toBe("youtube");
    expect(formatFor(undefined)).toBe("youtube");
  });
});
