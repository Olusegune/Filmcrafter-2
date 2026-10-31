// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));

import { MotionGraphicsSheet } from "../../MotionGraphics";

const templates = [
  { id: "lower_third", name: "Lower third", use: "A name at the bottom.", seconds: 4.5, layers: 4, slots: [{ id: "name", label: "Name", default: "Sarah" }, { id: "role", label: "Role", default: "Nurse" }] },
  { id: "callout", name: "Callout", use: "Point at something.", seconds: 4, layers: 3, slots: [{ id: "text", label: "Label", default: "Look here" }] },
];
const backend = (fail = false) => (_n: string, a: { action: string; data: Record<string, unknown> }) => {
  switch (a.action) {
    case "builtin_list": return Promise.resolve({ templates });
    case "builtin_preview": return Promise.resolve({ path: "cache/x.png", id: a.data.id });
    case "builtin_apply": return fail ? Promise.reject(new Error("Remove some layers first.")) : Promise.resolve({ made: 4, group: "tpl:lowerthird:1" });
    case "template_remove": return Promise.resolve({ removed: 4 });
    default: return Promise.resolve({});
  }
};
afterEach(() => { cleanup(); invoke.mockReset(); });
const sent = (action: string) => invoke.mock.calls.filter(([, a]) => a.action === action).map(([, a]) => a.data);

describe("the motion graphics sheet", () => {
  it("adds the chosen one at the playhead with exactly the words typed, and takes only that group away", async () => {
    invoke.mockImplementation(backend());
    const seen = vi.fn();
    window.addEventListener("pf-overlays-changed", seen);
    render(<MotionGraphicsSheet dir="p" time={12.34} onClose={() => {}} />);
    const side = await screen.findByRole("complementary", { name: "Lower third words" });
    fireEvent.change(within(side).getByLabelText("Name"), { target: { value: "Ada" } });
    fireEvent.click(within(side).getByRole("button", { name: "Add at the playhead (12.3 s)" }));
    await waitFor(() => expect(sent("builtin_apply")).toEqual([{ id: "lower_third", at: 12.3, texts: { name: "Ada", role: "Nurse" } }]));
    const done = await screen.findByRole("status");
    expect(done).toHaveTextContent("Added Lower third: 4 layers from 12.3 s");
    expect(seen).toHaveBeenCalled();
    fireEvent.click(within(done).getByRole("button", { name: "Take it away again" }));
    await waitFor(() => expect(sent("template_remove")).toEqual([{ group: "tpl:lowerthird:1" }]));
    window.removeEventListener("pf-overlays-changed", seen);
  });

  it("keeps each template's words apart and says plainly when it cannot be added", async () => {
    invoke.mockImplementation(backend(true));
    render(<MotionGraphicsSheet dir="p" time={0} onClose={() => {}} />);
    fireEvent.click(within(await screen.findByRole("listitem", { name: "Callout" })).getByRole("button"));
    const side = screen.getByRole("complementary", { name: "Callout words" });
    fireEvent.change(within(side).getByLabelText("Label"), { target: { value: "Here" } });
    fireEvent.click(within(screen.getByRole("listitem", { name: "Lower third" })).getByRole("button"));
    expect(within(screen.getByRole("complementary", { name: "Lower third words" })).getByLabelText("Name")).toHaveValue("Sarah");
    fireEvent.click(screen.getByRole("button", { name: /Add at the playhead/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Remove some layers first.");
    expect(screen.queryByRole("status")).toBeNull();
  });
});
