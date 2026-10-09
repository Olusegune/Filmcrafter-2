import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { normaliseListing } from "../Supervisor";

describe("the Supervisor's list is made safe to draw", () => {
  it("an empty or missing answer is an empty list that is ready for release, not a crash (the sheet used to take the whole screen down)", () => {
    for (const raw of [undefined, null, [], "x", 5, {}]) {
      const l = normaliseListing(raw);
      expect(l.items).toEqual([]);
      expect(l.groups).toEqual([]);
      expect(l.summary).toEqual({ open: 0, major: 0, minor: 0, info: 0, decided: 0, ready: true });
    }
  });
  it("keeps what the engine sent and fills in only what is missing from the summary", () => {
    const l = normaliseListing({ items: [{ id: "a" }], groups: [{ key: "g" }], summary: { major: 3, ready: false } });
    expect(l.items).toHaveLength(1);
    expect(l.groups).toHaveLength(1);
    expect(l.summary).toEqual({ open: 0, major: 3, minor: 0, info: 0, decided: 0, ready: false });
  });
  it("ignores parts of the wrong type", () => {
    const l = normaliseListing({ items: "no", groups: { a: 1 }, summary: "none" });
    expect(l.items).toEqual([]);
    expect(l.groups).toEqual([]);
    expect(l.summary.ready).toBe(true);
  });
});
