import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { levelWords, rhythmHeight } from "../pacingWords";

describe("the pacing screen", () => {
  it("names the levels plainly and sizes the bars by length", () => {
    expect([levelWords("fix"), levelWords("look"), levelWords("note")]).toEqual(["Fix", "Look", "Note"]);
    expect(rhythmHeight(6, 6)).toBe(100);
    expect(rhythmHeight(3, 6)).toBe(50);
    expect(rhythmHeight(0.1, 6)).toBe(8);                  // never so short it cannot be clicked
    expect(rhythmHeight(5, 0)).toBeGreaterThan(0);
  });
  const t = readFileSync("src/PacingSheet.tsx", "utf8");
  it("only reads: nothing paid, nothing sent, nothing changed", () => {
    expect(t).toMatch(/filmPacing/);
    expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|api\.shots\(|confirmed:\s*true|fetch\(/);
  });
  it("a finding takes you to its shot, and the screen is on the Shots screen", () => {
    expect(t).toMatch(/Go to \{f\.shot\}/);
    expect(readFileSync("src/ShotLab.tsx", "utf8")).toMatch(/Pacing…/);
  });
});

describe("the composition guide", () => {
  const t = readFileSync("src/CompositionGuide.tsx", "utf8");
  it("draws the thirds and the points, and has a film-wide switch", () => {
    expect(t).toMatch(/divided into thirds/);
    expect(t).toMatch(/Ask for this composition when pictures and video are made/);
    expect(t).toMatch(/filmComposition\("set"/);
  });
  it("sits in the Camera tab and the pictures can show a thirds grid", () => {
    expect(readFileSync("src/ShotLab.tsx", "utf8")).toMatch(/<CompositionGuide /);
    expect(readFileSync("src/MakeFilm.tsx", "utf8")).toMatch(/Thirds grid/);
    expect(readFileSync("src/film.css", "utf8")).toMatch(/\.mk\.thirds \.mk-pic::after/);
  });
  it("never starts paid work", () => expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true/));
});
