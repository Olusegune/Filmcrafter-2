import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/api/webview", () => ({ getCurrentWebview: () => ({ onDragDropEvent: () => Promise.resolve(() => {}) }) }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { checkNotes } from "../Keyframe";

describe("what the keyframe check says", () => {
  it("passes quietly", () => {
    expect(checkNotes({ ok: true, problems: [] })).toEqual({ state: "pass", label: "Check passed", details: [] });
  });
  it("names the problems of a failed still in plain words", () => {
    const n = checkNotes({ ok: false, problems: [{ kind: "anatomy", severity: "major", detail: "Fused fingers." }, { kind: "text", detail: "A title." }] });
    expect(n).toEqual({ state: "fail", label: "hands and body, text on the picture", details: ["Fused fingers.", "A title."] });
  });
  it("says 'Check failed' when no problem was listed", () => {
    expect(checkNotes({ ok: false, problems: [] }).label).toBe("Check failed");
  });
  it("shows a passed still with soft hands as one to look at, and says what", () => {
    const n = checkNotes({ ok: true, problems: [{ kind: "anatomy", severity: "minor", detail: "The left hand is soft." }] });
    expect(n.state).toBe("look");
    expect(n.label).toBe("Passed · look at the hands and body");
    expect(n.details).toEqual(["The left hand is soft."]);
  });
  it("is 'not checked' when the check could not run", () => {
    expect(checkNotes({ ok: null, error: "no key" })).toMatchObject({ state: "unchecked", label: "Not checked" });
  });
});
