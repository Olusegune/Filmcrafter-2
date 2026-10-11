import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve(null)), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { Preview, SelectReview, groupByScene, type PreviewItem } from "../SelectReview";
import type { BoardShot } from "../api";

const shot = (id: string, scene: number, over: Partial<BoardShot> = {}): BoardShot => ({ id, scene, heading: scene === 1 ? "INT. KITCHEN" : "EXT. PLATFORM", start: 0, end: 4, framing: "Wide", beat: `${id} beat`, performers: [], status: "ready", locked: false,
  approved: null, thumb_src: null, thumb_source: "placeholder", preview: null, keyframe: null, versions: [], references: [], ...over } as BoardShot);

describe("grouping the shots by scene", () => {
  it("keeps the order, makes a group of each run of one scene, and carries the heading", () => {
    const g = groupByScene([shot("S01-01", 1), shot("S01-02", 1), shot("S02-01", 2), shot("S02-02", 2), shot("S02-03", 2)]);
    expect(g.map(([n]) => n)).toEqual([1, 2]);
    expect(g[0][1]).toBe("INT. KITCHEN");
    expect(g[0][2].map((s) => s.id)).toEqual(["S01-01", "S01-02"]);
    expect(g[1][2]).toHaveLength(3);
    expect(groupByScene([])).toEqual([]);
  });
  it("does not merge a scene that comes back later (the order of the film is kept)", () => {
    expect(groupByScene([shot("a", 1), shot("b", 2), shot("c", 1)]).map(([n]) => n)).toEqual([1, 2, 1]);
  });
});

describe("the larger view", () => {
  const items: PreviewItem[] = [
    { key: "a", src: "asset://a.png", title: "S01-01", sub: "0:00 · Wide", detail: "INT. KITCHEN · she pours tea", on: true, action: { label: "Deselect this shot", run: () => {} } },
    { key: "b", src: null, title: "S01-02", sub: "0:04", action: { label: "Locked", run: () => {}, disabled: true } },
  ];
  const html = (i: number) => renderToStaticMarkup(<Preview items={items} index={i} onIndex={() => {}} onClose={() => {}} />);

  it("is a labelled dialog with the picture, its name, the way on and the action", () => {
    const h = html(0);
    expect(h).toContain('role="dialog"');
    expect(h).toContain('aria-modal="true"');
    expect(h).toContain("Larger view of S01-01");
    expect(h).toContain('src="asset://a.png"');
    expect(h).toContain("INT. KITCHEN · she pours tea");
    expect(h).toContain("Deselect this shot");
    expect(h).toContain("1 of 2");
    expect(h).toContain("Esc to close");
  });
  it("cannot go back from the first picture or forward from the last", () => {
    expect(html(0)).toMatch(/<button[^>]*class="sr-pv-nav"[^>]*disabled=""[^>]*aria-label="Previous picture"/);
    expect(html(1)).toMatch(/<button[^>]*class="sr-pv-nav"[^>]*disabled=""[^>]*aria-label="Next picture"/);
  });
  it("says so plainly when there is no picture yet, and a locked shot cannot be selected from it", () => {
    const h = html(1);
    expect(h).toContain("No picture yet");
    expect(h).toMatch(/disabled=""[^>]*>Locked</);
  });
  it("shows nothing for an index past the end", () => {
    expect(renderToStaticMarkup(<Preview items={items} index={5} onIndex={() => {}} onClose={() => {}} />)).toBe("");
  });
});

describe("the select step", () => {
  const shots = [shot("S01-01", 1, { keyframe: "k1.png" }), shot("S01-02", 1), shot("S02-01", 2, { locked: true })];
  const h = renderToStaticMarkup(<SelectReview dir="f" shots={shots} sections={[]} initial={["S01-01"]} aspect="9:16" onClose={() => {}} onQueued={() => {}} />);

  it("groups the shots by scene with a way to select a whole scene", () => {
    expect(h).toContain("Scene 1");
    expect(h).toContain("Scene 2");
    expect(h).toContain("Select scene");
    expect(h).toContain("INT. KITCHEN");
  });
  it("draws each shot as a pressable tile with a name a screen reader can use, and an enlarge button", () => {
    expect(h).toMatch(/<button class="sr2-pick" aria-pressed="true"[^>]*>.*?S01-01.*?Wide/);            // named by what it shows; pressed says it is selected
    expect(h).toMatch(/<button class="sr2-pick" aria-pressed="false"[^>]*>.*?S01-02.*?Wide/);
    expect(h).not.toContain('class="sr2-pick" aria-pressed="true" aria-label');                        // no label that could drift from the visible text
    expect(h).toContain('aria-label="Enlarge S01-02"');
    expect(h).toContain('aria-pressed="true"');
  });
  it("marks a locked shot, leaves it unselectable, and offers the shots without a picture", () => {
    expect(h).toContain("Locked");
    expect(h).toMatch(/class="sr2-pick" disabled=""/);
    expect(h).toContain("Without a picture (1)");
    expect(h).toContain("1 selected");
  });
  it("follows the film's frame shape and offers three sizes", () => {
    expect(h).toContain("--ar:9 / 16");
    for (const w of ["Small", "Medium", "Large"]) expect(h).toContain(w);
    expect(h).toContain('data-size="m"');
  });
});
