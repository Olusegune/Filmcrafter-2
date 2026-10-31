// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));

import { SmartEditorSheet } from "../../SmartEditor";

const recipe = { id: "restrained_drama", label: "Restrained character drama", for: "Quiet scenes." };
const tighten = { id: "t1", kind: "tighten", title: "Tighten the end of S1", what: "End S1 1.0 s sooner.", why: "It runs long.", clips: ["c1"], shots: ["S1"], saves: 1, window: [0, 5], ops: [] };
const react = { id: "r1", kind: "react", title: "Give S2 a little more time", what: "Hold S2 longer.", why: "A listener.", clips: ["c2"], shots: ["S2"], saves: -0.6, window: [4, 8], ops: [] };
let left = [tighten, react];

const backend = (_n: string, a: { action: string; data: { id?: string } }) => {
  switch (a.action) {
    case "recipes": return Promise.resolve({ default: "restrained_drama", recipes: [{ id: "restrained_drama", label: "Restrained character drama", for: "Quiet scenes.", built: true }, { id: "suspense", label: "Suspense", for: "", built: false }] });
    case "suggest": return Promise.resolve({ recipe, proposals: left, kept: [{ kind: "tighten", shot: "S3", clip: "c3", why: "Kept the pause at the end of S3: you asked to hold the reaction longer there." }] });
    case "accept": case "reject": left = left.filter((p) => p.id !== a.data.id); return Promise.resolve({});
    case "preview": return Promise.resolve({ before: "b.mp4", after: "a.mp4" });
    case "ask": return Promise.resolve({ understood: false, message: "I did not understand that as something I can do yet.", recipe, proposals: [], kept: [] });
    default: return Promise.resolve({ cleared: 0 });
  }
};
afterEach(() => { cleanup(); invoke.mockReset(); left = [tighten, react]; });
const sent = (action: string) => invoke.mock.calls.filter(([, a]) => a.action === action).map(([, a]) => a.data);

describe("the Smart Editor sheet", () => {
  it("lists each suggestion with what, why, the clips and how much time it saves or adds, and what was left alone", async () => {
    invoke.mockImplementation(backend);
    render(<SmartEditorSheet dir="p" onClose={() => {}} />);
    const card = await screen.findByRole("listitem", { name: "Tighten the end of S1" });
    expect(card).toHaveTextContent("What: End S1 1.0 s sooner.");
    expect(card).toHaveTextContent("Why: It runs long.");
    expect(card).toHaveTextContent("Clips: S1");
    expect(card).toHaveTextContent("Saves 1.0 s");
    expect(screen.getByRole("listitem", { name: "Give S2 a little more time" })).toHaveTextContent("Adds 0.6 s");
    expect(screen.getByRole("region", { name: "Left alone on purpose" })).toHaveTextContent("Kept the pause at the end of S3");
    expect(sent("accept")).toEqual([]);                                                       // looking accepts nothing
  });

  it("previews before accepting, and accepting sends one accept for that suggestion and says how to undo it", async () => {
    invoke.mockImplementation(backend);
    const changed = vi.fn();
    render(<SmartEditorSheet dir="p" onClose={() => {}} onChanged={changed} />);
    const card = await screen.findByRole("listitem", { name: "Tighten the end of S1" });
    fireEvent.click(card.querySelector("button")!);                                        // Preview before and after
    expect(await screen.findByLabelText("Before")).toHaveAttribute("src", "p/b.mp4");
    expect(screen.getByLabelText("After the suggestion")).toHaveAttribute("src", "p/a.mp4");
    expect(sent("accept")).toEqual([]);
    fireEvent.click(within(card).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(sent("accept")).toEqual([{ id: "t1", recipe: "restrained_drama" }]));
    expect(await screen.findByText(/Done: Tighten the end of S1\. Ctrl\+Z puts it back\./)).toBeInTheDocument();
    expect(changed).toHaveBeenCalled();
  });

  it("refusing sends a reject for that suggestion only", async () => {
    invoke.mockImplementation(backend);
    render(<SmartEditorSheet dir="p" onClose={() => {}} />);
    const card = await screen.findByRole("listitem", { name: "Give S2 a little more time" });
    fireEvent.click(card.querySelectorAll("button")[2]);                                   // Not this one
    await waitFor(() => expect(sent("reject")).toEqual([{ id: "r1", recipe: "restrained_drama" }]));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Give S2 a little more time" })).toBeNull());
    expect(screen.getByRole("listitem", { name: "Tighten the end of S1" })).toBeInTheDocument();
  });

  it("an engine refusal shows as an alert and keeps the suggestion on screen", async () => {
    invoke.mockImplementation((n: string, a: { action: string; data: { id?: string } }) => a.action === "accept" ? Promise.reject("That suggestion no longer applies: the cut has changed since it was made. Ask again.") : backend(n, a));
    render(<SmartEditorSheet dir="p" onClose={() => {}} />);
    fireEvent.click((await screen.findByRole("listitem", { name: "Tighten the end of S1" })).querySelectorAll("button")[1]);
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer applies");
    expect(screen.getByRole("listitem", { name: "Tighten the end of S1" })).toBeInTheDocument();
  });

  it("sends a plain request as it was typed, shows what was understood or not, and does not offer an unbuilt style", async () => {
    invoke.mockImplementation(backend);
    render(<SmartEditorSheet dir="p" onClose={() => {}} />);
    await screen.findByRole("listitem", { name: "Tighten the end of S1" });
    expect(screen.getByRole("option", { name: "Suspense (not built yet)" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Or ask in your own words"), { target: { value: "make this cinematic" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(sent("ask")).toEqual([{ text: "make this cinematic" }]));
    expect(await screen.findByText(/did not understand that as something I can do yet/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing to suggest for this cut/)).toBeInTheDocument();
  });
});
