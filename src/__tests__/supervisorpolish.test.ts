import { describe, expect, it } from "vitest";
import changes from "../DirectorChanges.tsx?raw";
import { readLayout, writeLayout } from "../timelineView";

const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); } }; };

describe("Director changes", () => {
  it("declares every hook before its early return (a hook after it crashed the whole sheet)", () => {
    const early = changes.indexOf("if (!a) return null");
    expect(early).toBeGreaterThan(0);
    expect(changes.slice(early)).not.toMatch(/\buse(State|Effect|Callback|Memo|Ref)\(/);
  });
});

describe("a timeline height the person chose", () => {
  it("is remembered as chosen, however short", () => {
    const s = memory();
    writeLayout("p", { height: 160, sized: true }, s);
    expect(readLayout("p", s)).toMatchObject({ height: 160, sized: true });
  });
  it("is not marked chosen when only a height was stored", () => {
    const s = memory();
    writeLayout("p", { height: 260 }, s);
    expect(readLayout("p", s).sized).toBeUndefined();
  });
});
