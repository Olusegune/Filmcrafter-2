import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { FAULT_TEXT, errorText } from "../api";

describe("what a failure says", () => {
  it("passes the engine's own message through untouched", () => {
    expect(errorText("Needs a video for “mode”")).toBe("Needs a video for “mode”");
    expect(errorText(new Error("The renderer refused it: zero balance."))).toBe("The renderer refused it: zero balance.");
  });

  it("says a fault in the program itself in plain words, and keeps the technical text off the screen", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const e of [new TypeError("Cannot read properties of null (reading 'x')"), new RangeError("bad"), new ReferenceError("y is not defined"), new SyntaxError("Unexpected token")]) {
      const t = errorText(e);
      expect(t).toContain("Something unexpected happened");
      expect(t).toContain("Your project is safe");
      expect(t).not.toContain(e.message);
      expect(t).not.toMatch(/TypeError|ReferenceError|properties of null/);
      expect(log).toHaveBeenCalledWith(e);          // it is still in the console for whoever supports the app
    }
    log.mockRestore();
  });

  it("does the same for a fault that was turned into text on its way (String(e))", () => {
    expect(errorText(String(new TypeError("Cannot read properties of null (reading 'providers')")))).toBe(FAULT_TEXT);
    expect(errorText("A real message from the engine: TypeError is a word here")).toContain("A real message");
  });

  it("has a fallback for anything else", () => {
    expect(errorText(undefined)).toBe("Something went wrong.");
    expect(errorText({ code: 1 })).toBe("Something went wrong.");
  });
});
