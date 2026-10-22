import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("places nobody described", () => {
  const t = readFileSync("src/PlaceNotice.tsx", "utf8");
  it("says what is wrong in plain words and offers a free fix and the way to Cast & World", () => {
    expect(t).toMatch(/no description or picture/);
    expect(t).toMatch(/invents the background again in every shot/);
    expect(t).toMatch(/Fill in from the story \(free\)/);
    expect(t).toMatch(/Open Places in Cast &amp; World/);
  });
  it("only reads and writes descriptions: nothing paid, nothing sent", () => {
    expect(t).toMatch(/filmPlaces/);
    expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true|fetch\(/);
  });
  it("shows above the pictures and the panels, not above the video", () => {
    expect(readFileSync("src/MakeFilm.tsx", "utf8")).toMatch(/stage !== "video" && <PlaceNotice/);
  });
  it("Open Places goes to the Places tab of Cast & World", () => {
    expect(readFileSync("src/FilmView.tsx", "utf8")).toMatch(/goPlaces \? "environment"/);
  });
});
