import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { actionWords, beatLabel, momentumWords } from "../choreoWords";

describe("action scene words", () => {
  it("names the kinds and the beats plainly", () => {
    expect(actionWords("fight")).toBe("Fist fight");
    expect(actionWords("vehicle")).toBe("Vehicle chase");
    expect(actionWords("mystery")).toBe("mystery");
    expect(beatLabel("insert")).toBe("Cut to a detail");
    expect(beatLabel("aftermath")).toBe("How it ends");
  });
  it("says who has the upper hand", () => {
    expect(momentumWords("A", "Mara", "Dov")).toBe("Mara has the upper hand");
    expect(momentumWords("B", "Mara", "Dov")).toBe("Dov has the upper hand");
    expect(momentumWords("even")).toBe("Evenly matched");
  });
});

describe("the action scene screen", () => {
  const t = readFileSync("src/ActionChoreo.tsx", "utf8");
  it("only plans and adds new shots: nothing paid, nothing sent", () => {
    expect(t).toMatch(/filmChoreography/);
    expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true|fetch\(/);
  });
  it("says that no existing shot is changed", () => {
    expect(t).toMatch(/no existing shot is changed/);
  });
  it("is reachable from the Shots screen", () => {
    expect(readFileSync("src/ShotLab.tsx", "utf8")).toMatch(/Action scene…/);
  });
});

describe("the materials button is visible on every film", () => {
  it("the film header has a Materials button next to Guide and Costs", () => {
    const t = readFileSync("src/FilmView.tsx", "utf8");
    expect(t).toMatch(/setMaterials\(true\)[^\n]*Materials/);
  });
});
