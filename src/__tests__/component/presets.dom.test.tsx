// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));
const save = vi.fn();
const open = vi.fn();
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: (o: unknown) => save(o), open: (o: unknown) => open(o) }));

import { PresetsSheet, say } from "../../PresetLibrary";
import type { PresetCatalog, PresetPlan } from "../../api";

const row = (id: string, name: string, type = "production", over = {}) => ({ id, name, type, group: "Production", description: `${name} description`, use: "", version: 1, thumbnail: null, includes: [], settings: {}, complexity: 1, mine: false, favorite: false, recent: false, in_stack: false, ...over });
const catalog = (over: Partial<PresetCatalog> = {}): PresetCatalog => ({ presets: [row("a", "Alpha"), row("b", "Beta", "visual", { group: "Visual" }), row("m", "My own", "custom", { mine: true, group: "Mine" })], stack: [], types: [], applied: 0, current: {}, is_film: true, ...over });
const plan = (): PresetPlan => ({ stack: ["a"], order: ["a"], notes: ["Nothing is regenerated and no provider is called: only settings change, and every change can be undone."],
  changes: [{ key: "look", status: "yours", now: "claymation", to: "anime", by: "b", set: true }, { key: "acting", status: "new", now: "natural", to: "restrained", by: "a", set: false }] });
const backend = (cat: PresetCatalog) => (_n: string, a: { action: string; data: Record<string, unknown> }) => {
  switch (a.action) {
    case "catalog": return Promise.resolve(cat);
    case "plan": return Promise.resolve(plan());
    case "apply": return Promise.resolve({ changed: ["acting"], kept: ["look"], same: [], plan: plan() });
    case "undo": return Promise.resolve({ restored: ["acting"], kept_as_changed_since: [] });
    case "favorite": return Promise.resolve({ ...cat, presets: cat.presets.map((p) => (p.id === a.data.id ? { ...p, favorite: !!a.data.on } : p)) });
    default: return Promise.resolve({});
  }
};
afterEach(() => { cleanup(); invoke.mockReset(); save.mockReset(); open.mockReset(); });
const sent = (action: string) => invoke.mock.calls.filter(([, a]) => a.action === action).map(([, a]) => a.data);

describe("the presets sheet", () => {
  it("says a setting the way a person would", () => {
    expect(say("grade", { contrast: 0.15, saturation: -0.1 })).toBe("contrast +0.15, saturation -0.1");
    expect(say("delivery", { export: "vertical", safe: { bottom: 0.2 }, captions: true })).toBe("vertical version, captions on, 20% kept clear at the bottom");
    expect(say("duration_hint_s", 90)).toBe("about 90 seconds");
    expect(say("look", null)).toBe("nothing chosen");
  });

  it("stacks presets in order, previews with the stack and the replace choices, and applies exactly that", async () => {
    invoke.mockImplementation(backend(catalog()));
    render(<PresetsSheet dir="p" onClose={() => {}} />);
    fireEvent.click(within(await screen.findByRole("listitem", { name: "Alpha" })).getByRole("button", { name: "Add to stack" }));
    fireEvent.click(within(screen.getByRole("listitem", { name: "Beta" })).getByRole("button", { name: "Add to stack" }));
    fireEvent.click(screen.getByRole("button", { name: "Move Beta earlier" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview what this changes" }));
    await waitFor(() => expect(sent("plan")).toContainEqual({ stack: ["b", "a"], replace: [] }));
    const table = await screen.findByRole("region", { name: "What would change" });
    expect(within(table).getByRole("row", { name: /Visual style/ })).toHaveTextContent("Yours, kept");
    expect(within(table).getByRole("row", { name: /Acting/ })).toHaveTextContent("New");
    fireEvent.click(within(table).getByLabelText("Replace mine"));
    await waitFor(() => expect(sent("plan")).toContainEqual({ stack: ["b", "a"], replace: ["look"] }));
    fireEvent.click(within(table).getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(sent("apply")).toEqual([{ stack: ["b", "a"], replace: ["look"] }]));
    expect(await screen.findByText(/Applied: Acting\. Kept yours: Visual style\. Undo puts it back\./)).toBeInTheDocument();
  });

  it("looking applies nothing and undo is off until something was applied", async () => {
    invoke.mockImplementation(backend(catalog()));
    render(<PresetsSheet dir="p" onClose={() => {}} />);
    fireEvent.click(within(await screen.findByRole("listitem", { name: "Alpha" })).getByRole("button", { name: "Add to stack" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview what this changes" }));
    await screen.findByRole("region", { name: "What would change" });
    expect(sent("apply")).toEqual([]);
    expect(screen.getByRole("button", { name: "Undo the last application" })).toBeDisabled();
  });

  it("undo is offered after something was applied and reports what was put back", async () => {
    invoke.mockImplementation(backend(catalog({ applied: 1 })));
    render(<PresetsSheet dir="p" onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Undo the last application" }));
    expect(await screen.findByText("Put back: Acting.")).toBeInTheDocument();
  });

  it("search and filters narrow the library, and a favourite is sent as asked", async () => {
    invoke.mockImplementation(backend(catalog()));
    render(<PresetsSheet dir="p" onClose={() => {}} />);
    await screen.findByRole("listitem", { name: "Alpha" });
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "beta" } });
    expect(screen.queryByRole("listitem", { name: "Alpha" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Mine" }));
    expect(screen.getAllByRole("listitem").map((l) => l.getAttribute("aria-label"))).toEqual(["My own"]);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.click(within(screen.getByRole("listitem", { name: "Alpha" })).getByRole("button", { name: /Mark Alpha as a favorite/ }));
    await waitFor(() => expect(sent("favorite")).toEqual([{ id: "a", on: true }]));
  });

  it("an engine refusal shows as an alert and nothing else changes", async () => {
    invoke.mockImplementation((n: string, a: { action: string; data: Record<string, unknown> }) => (a.action === "plan" ? Promise.reject("The preset \"zzz\" is not here.") : backend(catalog())(n, a)));
    render(<PresetsSheet dir="p" onClose={() => {}} />);
    fireEvent.click(within(await screen.findByRole("listitem", { name: "Alpha" })).getByRole("button", { name: "Add to stack" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview what this changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not here");
    expect(screen.queryByRole("region", { name: "What would change" })).toBeNull();
  });
});
