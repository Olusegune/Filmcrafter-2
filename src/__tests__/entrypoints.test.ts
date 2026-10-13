import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";

const read = (p: string) => readFileSync(p, "utf8");

describe("FilmCrafter opens films, and has no way in to the music-video app", () => {
  it("refuses anything that is not a film (or a film's own render project) with a plain message", () => {
    const app = read("src/App.tsx");
    expect(app).toContain("belongs in PULSEFRAME");
    expect(app).toMatch(/\.film\) \{ setView\(\{ name: "studio"/);       // only a film's render project reaches the Studio
    expect(app).not.toMatch(/onboarding|song_map/);
  });
  it("lists only films under Recent", () => {
    expect(read("src/Home.tsx")).toContain('projects.filter((p) => p.kind === "film")');
  });
  it("has no Autopilot, song analysis, show or dance entry in the screens, the api or the shell", () => {
    expect(existsSync("src/Autopilot.tsx")).toBe(false);
    expect(read("src/Studio.tsx")).not.toMatch(/Autopilot/);
    const api = read("src/api.ts");
    for (const gone of ["analyze_project", "dance", "is_show", "show", "voices"]) expect(api, gone).not.toMatch(new RegExp(`invoke(?:<[^(]*>)?\\("${gone}"`));
    const rust = read("src-tauri/src/lib.rs");
    for (const gone of ["async fn analyze_project", "async fn dance", "async fn show(", "async fn voices", "fn is_show"]) expect(rust, gone).not.toContain(gone);
  });
});

describe("each animation principle has its picture", () => {
  it("covers every principle the engine has", async () => {
    const { hasPrincipleIcon } = await import("../principleIcons");
    const ids = [...read("analysis/filmcrafter_engine/animation_principles.py").matchAll(/^ {4}P\("([a-z-]+)"/gm)].map((m) => m[1]);
    expect(ids.length).toBe(12);
    for (const id of ids) expect(hasPrincipleIcon(id), id).toBe(true);
  });
});
