import { describe, expect, it } from "vitest";
import { readFlag, writeFlag } from "../panelState";

const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, m }; };

describe("a panel shown or hidden is remembered", () => {
  it("uses the default until something is saved", () => {
    const s = memory();
    expect(readFlag("pf-timeline", true, s)).toBe(true);
    expect(readFlag("pf-timeline", false, s)).toBe(false);
  });
  it("remembers hidden and shown", () => {
    const s = memory();
    writeFlag("pf-timeline", false, s);
    expect(s.m.get("pf-timeline")).toBe("0");
    expect(readFlag("pf-timeline", true, s)).toBe(false);
    writeFlag("pf-timeline", true, s);
    expect(readFlag("pf-timeline", false, s)).toBe(true);
  });
  it("ignores a saved value it doesn't understand", () => {
    const s = memory();
    s.setItem("pf-timeline", "maybe");
    expect(readFlag("pf-timeline", true, s)).toBe(true);
  });
  it("never throws when storage is missing or blocked", () => {
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readFlag("x", true, blocked)).toBe(true);
    expect(() => writeFlag("x", false, blocked)).not.toThrow();
    expect(readFlag("x", false, null)).toBe(false);
    expect(() => writeFlag("x", true, null)).not.toThrow();
  });
});
