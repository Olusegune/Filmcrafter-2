import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { filmDirOfDoc, filmDirOfRender, isRenderDir } from "../filmPaths";

describe("finding a film from its render project or its document", () => {
  it("works with Windows backslashes (the case that sent the Storyboard button to Home) and with slashes", () => {
    expect(filmDirOfRender("C:\\Users\\a\\Documents\\FilmCrafter\\My Film\\render")).toBe("C:\\Users\\a\\Documents\\FilmCrafter\\My Film");
    expect(filmDirOfRender("/Users/a/Documents/FilmCrafter/My Film/render")).toBe("/Users/a/Documents/FilmCrafter/My Film");
    expect(filmDirOfRender("C:\\Films\\X\\render\\")).toBe("C:\\Films\\X");
    expect(filmDirOfRender("C:\\Films\\X\\Render")).toBe("C:\\Films\\X");
  });
  it("leaves any other folder alone", () => {
    expect(filmDirOfRender("C:\\Films\\X")).toBe("C:\\Films\\X");
    expect(filmDirOfRender("C:\\Films\\renderfarm")).toBe("C:\\Films\\renderfarm");
    expect(filmDirOfRender("")).toBe("");
  });
  it("finds the film's folder from its document, either way round", () => {
    expect(filmDirOfDoc("C:\\Films\\X\\X.filmcrafter")).toBe("C:\\Films\\X");
    expect(filmDirOfDoc("/films/x/X.filmcrafter")).toBe("/films/x");
    expect(filmDirOfDoc("C:\\Films\\X")).toBe("C:\\Films\\X");
  });
  it("knows a render folder", () => {
    expect(isRenderDir("C:\\Films\\X\\render")).toBe(true);
    expect(isRenderDir("/films/x/render/")).toBe(true);
    expect(isRenderDir("C:\\Films\\X")).toBe(false);
  });
  it("is what the app uses, with no hand-written separator patterns left to go wrong", () => {
    const app = readFileSync("src/App.tsx", "utf8");
    expect(app).toContain("filmDirOfRender(dir)");
    expect(app).toContain("filmDirOfDoc(dir)");
    expect(app).not.toMatch(/\.replace\(\/\[\\\/\]/);
  });
});
