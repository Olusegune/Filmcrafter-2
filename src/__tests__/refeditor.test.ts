import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { bibleBacked } from "../RefEditor";
import type { RefItem } from "../api";

const item = (id: string, kind: RefItem["kind"]) => ({ id, kind, name: "x", files: [], notes: "" }) as RefItem;

describe("which references are edited in Cast & World", () => {
  it("a reference made from the Bible is edited there (so the change lasts), anything else in the library", () => {
    expect(bibleBacked(item("fc-chloe", "character"), "/film")).toBe(true);
    expect(bibleBacked(item("fc-kitchen", "set"), "/film")).toBe(true);
    expect(bibleBacked(item("fc-kettle", "prop"), "/film")).toBe(true);
    expect(bibleBacked(item("fc-chloe", "character"), undefined)).toBe(false);         // no film folder: nothing to edit it in
    expect(bibleBacked(item("fc-sm-chloe-1a2b", "character"), "/film")).toBe(false);   // a picture chosen for a moment is rebuilt, not edited
    expect(bibleBacked(item("fc-board-s01-01", "style"), "/film")).toBe(false);
    expect(bibleBacked(item("a1b2c3", "character"), "/film")).toBe(false);
    expect(bibleBacked(item("fc-wardrobe", "wardrobe"), "/film")).toBe(false);
  });
});

describe("changing an asset", () => {
  const board = readFileSync("src/Board.tsx", "utf8");
  const editor = readFileSync("src/RefEditor.tsx", "utf8");
  const cast = readFileSync("src/CastWorld.tsx", "utf8");
  it("Edit opens the form in the card you clicked, not at the top of a long list", () => {
    expect(board).toMatch(/setEditId\(it\.id\)/);
    expect(board).toMatch(/editId === it\.id/);
    expect(board).toMatch(/<RefEditor /);
  });
  it("each picture can be replaced, taken off, retyped and added, and nothing is deleted", () => {
    expect(editor).toMatch(/Replace…/);
    expect(editor).toMatch(/Remove/);
    expect(editor).toMatch(/replace_media/);
    expect(editor).toMatch(/update_media/);
    expect(editor).toMatch(/\+ Add pictures…/);
    expect(editor).toMatch(/stay in the project folder/);
    expect(editor).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen/);
  });
  it("Cast & World pictures can be replaced and retyped too", () => {
    expect(cast).toMatch(/replace_media/);
    expect(cast).toMatch(/update_media/);
    expect(cast).toMatch(/>replace</);
  });
});

describe("the edit form fits", () => {
  const css = readFileSync("src/film.css", "utf8");
  it("takes the whole row of the list (not one narrow card) and keeps file names on one line", () => {
    expect(css).toMatch(/\.lib-item\.editing \{[^}]*grid-column: 1 \/ -1/);
    expect(css).toMatch(/\.re-meta \.num \{[^}]*text-overflow: ellipsis/);
    expect(css).toMatch(/\.re-file \{ display: grid; grid-template-columns: 96px minmax\(0, 1fr\)/);
  });
});
