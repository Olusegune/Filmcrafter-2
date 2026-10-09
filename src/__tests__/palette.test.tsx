import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Palette, filterPalette, type Command } from "../Palette";

const run = vi.fn();
const cmds: Command[] = [
  { id: "layers", label: "Open the Layers panel", hint: "Text, pictures, shapes drawn over the film", keys: "Y", run },
  { id: "export", label: "Export the film", keys: "Ctrl+E", run },
  { id: "colour", label: "Colour match", hint: "Even out brightness between shots", run },
];
const shots = ["S01-01", "S01-04", "S02-04", "S10-01"].map((id, i) => ({ id, start: i }));

describe("command palette", () => {
  it("lists every command when nothing is typed, and no shots", () => {
    const r = filterPalette("", cmds, shots);
    expect(r.commands).toHaveLength(3);
    expect(r.shots).toHaveLength(0);
  });

  it("matches commands on every word, in the label, the hint or the key", () => {
    expect(filterPalette("layers", cmds, shots).commands.map((c) => c.id)).toEqual(["layers"]);
    expect(filterPalette("film export", cmds, shots).commands.map((c) => c.id)).toEqual(["export"]);
    expect(filterPalette("brightness", cmds, shots).commands.map((c) => c.id)).toEqual(["colour"]);
    expect(filterPalette("ctrl+e", cmds, shots).commands.map((c) => c.id)).toEqual(["export"]);
    expect(filterPalette("zzz", cmds, shots).commands).toEqual([]);
  });

  it("puts a match in the label before a match only in the hint", () => {
    const list: Command[] = [{ id: "a", label: "Ask the Director", hint: "Change the video in plain words", run }, { id: "b", label: "Layers", run }, { id: "c", label: "Open the Layers panel", run }];
    expect(filterPalette("la", list, []).commands.map((c) => c.id)).toEqual(["b", "c", "a"]);
  });

  it("finds a shot by its number, with or without the S, 'shot' or 'go to'", () => {
    expect(filterPalette("01-04", cmds, shots).shots.map((s) => s.id)).toEqual(["S01-04"]);
    expect(filterPalette("s02-04", cmds, shots).shots.map((s) => s.id)).toEqual(["S02-04"]);
    expect(filterPalette("go to shot 04", cmds, shots).shots.map((s) => s.id)).toEqual(["S01-04", "S02-04"]);
  });

  it("caps the shots it lists", () => {
    const many = Array.from({ length: 70 }, (_, i) => ({ id: `S01-${String(i + 1).padStart(2, "0")}`, start: i }));
    expect(filterPalette("01", [], many).shots).toHaveLength(8);
  });

  it("draws a labelled search box and a list of options with the keys beside them", () => {
    const html = renderToStaticMarkup(<Palette commands={cmds} shots={shots} onShot={() => {}} onClose={() => {}} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Search commands and shots"');
    expect(html).toContain('role="listbox"');
    expect((html.match(/role="option"/g) ?? []).length).toBe(3);
    expect(html).toContain("<kbd>Ctrl+E</kbd>");
    expect(html).toContain('aria-selected="true"');                 // the first one is chosen, so Enter does something
  });
});
