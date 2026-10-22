import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("yellow tint, noise and waxy skin (Colour match)", () => {
  const t = readFileSync("src/ColourMatch.tsx", "utf8");
  it("offers the cast, the noise, the grain and the prompt wording as separate, plainly named choices", () => {
    expect(t).toMatch(/Take out a colour cast that runs through the whole film/);
    expect(t).toMatch(/Reduce noise a little/);
    expect(t).toMatch(/Add a fine, even grain/);
    expect(t).toMatch(/ask the models for natural skin, neutral colour and a clean image/);
  });
  it("says what it found, and that the takes are never changed", () => {
    expect(t).toMatch(/This film leans/);
    expect(t).toMatch(/Your takes are never changed/);
  });
  it("only sends settings to the free local colour tool: nothing paid", () => {
    expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true/);
  });
});
