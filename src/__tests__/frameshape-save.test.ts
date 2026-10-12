import { beforeEach, describe, expect, it, vi } from "vitest";

const calls: [string, ...unknown[]][] = [];
vi.mock("../api", () => ({
  api: {
    setProjectSettings: vi.fn(async (...a: unknown[]) => { calls.push(["setProjectSettings", ...a]); }),
    film: vi.fn(async (...a: unknown[]) => { calls.push(["film", ...a]); return {}; }),
  },
}));

vi.stubGlobal("window", { dispatchEvent: vi.fn() });

import { saveFrame } from "../frame";

const WIN_FILM = "C:\\Users\\me\\Documents\\FilmCrafter\\My Film";

describe("choosing a frame shape", () => {
  beforeEach(() => { calls.length = 0; });
  it("sets the film's shape too when it is chosen on a film's render project (so a later sync does not put 16:9 back)", async () => {
    await saveFrame(WIN_FILM + "\\render", "aspect_ratio", "21:9");
    expect(calls).toEqual([
      ["setProjectSettings", WIN_FILM + "\\render", { aspect_ratio: "21:9" }],
      ["film", "set_aspect", WIN_FILM, { aspect_ratio: "21:9" }],
    ]);
  });
  it("works with forward slashes too, and leaves quality and other projects alone", async () => {
    await saveFrame("/home/me/films/F/render/", "aspect_ratio", "9:16");
    expect(calls[1]).toEqual(["film", "set_aspect", "/home/me/films/F", { aspect_ratio: "9:16" }]);
    calls.length = 0;
    await saveFrame("C:/films/F/render", "quality", "high");
    await saveFrame("C:/projects/not-a-film", "aspect_ratio", "1:1");
    expect(calls.map((c) => c[0])).toEqual(["setProjectSettings", "setProjectSettings"]);
  });
});
