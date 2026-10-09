import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve({})), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { counter, LEVEL_LABEL, PromptPanel, promptOverrides } from "../PromptPanel";

const panel = (mode: "auto" | "mine", extra = {}) => renderToStaticMarkup(
  <PromptPanel dir="d" shot="S01-01" provider="kie" model="bytedance/seedance-2" prompt={{ mode, text: "Little Sege dissolves into light.", only: false, ...extra }} onPrompt={() => {}} direction="" onDirection={() => {}} frames />);

describe("what a take is queued with", () => {
  it("is your own words (and 'only my words') when you wrote the prompt", () => {
    expect(promptOverrides({ mode: "mine", text: "  Little Sege dissolves.  ", only: false }, "ignored")).toEqual({ _prompt: "Little Sege dissolves." });
    expect(promptOverrides({ mode: "mine", text: "Little Sege dissolves.", only: true }, "")).toEqual({ _prompt: "Little Sege dissolves.", _prompt_only: true });
  });
  it("is the one line of direction when PULSEFRAME writes it, or nothing", () => {
    expect(promptOverrides({ mode: "auto", text: "kept but unused", only: false }, "  a slow push in ")).toEqual({ _note: "a slow push in" });
    expect(promptOverrides({ mode: "auto", text: "", only: false }, "   ")).toEqual({});
  });
  it("never sends an empty prompt of your own: it falls back to PULSEFRAME's", () => {
    expect(promptOverrides({ mode: "mine", text: "   ", only: true }, "a slow push in")).toEqual({ _note: "a slow push in" });
  });
});

describe("the words on the screen", () => {
  it("counts against the model's limit when it has one", () => {
    expect(counter(179, 20000)).toBe("179 of 20000 characters");
    expect(counter(40, 0)).toBe("40 characters");
  });
  it("names the three kinds of check plainly", () => {
    expect(LEVEL_LABEL).toEqual({ problem: "Fix this", warn: "Check this", tip: "Tip" });
  });
  it("offers PULSEFRAME's prompt and your own, and starts with the one-line direction", () => {
    const html = panel("auto");
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain("PULSEFRAME writes it from the shot");
    expect(html).toContain("I&#x27;ll write it");
    expect(html).toContain("One line of direction");
    expect(html).not.toContain("Write it for me");
  });
  it("shows the writing tools, the recipes and the only-my-words switch when you write it", () => {
    const html = panel("mine");
    expect(html).toContain('aria-label="Your prompt"');
    expect(html).toContain("Write it for me");
    expect(html).toContain("Recipes for shots like this");
    expect(html).toContain("Use only my words");
    expect(html).toContain("what happens between them");
    expect(html).toContain("Show exactly what will be sent");
  });
  it("tells a plain-references shot something different from a start-to-end one", () => {
    const html = renderToStaticMarkup(<PromptPanel dir="d" shot="S01-01" provider="kie" model="m" prompt={{ mode: "mine", text: "", only: false }} onPrompt={() => {}} direction="" onDirection={() => {}} frames={false} />);
    expect(html).toContain("The reference pictures show how people and places look");
    expect(html).not.toContain("The two pictures already show");
  });
});
