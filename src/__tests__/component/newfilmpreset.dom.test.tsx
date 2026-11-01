// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));

import { NewFilm } from "../../NewFilm";

const backend = (fail = false) => (cmd: string, a: { action?: string; data?: Record<string, unknown> }) => {
  if (cmd === "film" && a.action === "create") return Promise.resolve({ dir: "C:/films/Night" });
  if (cmd === "film" && a.action === "preview") return Promise.resolve({ kind: "idea", words: 3, scenes: 0, characters: 0, locations: 0, seconds: 0, has_headings: false });
  if (cmd === "presets") return fail ? Promise.reject(new Error("no")) : Promise.resolve({ pending: ["vertical_micro_drama"] });
  return Promise.resolve({});
};
afterEach(() => { cleanup(); invoke.mockReset(); });
const sent = (cmd: string) => invoke.mock.calls.filter(([c]) => c === cmd).map(([, a]) => a);

describe("a new film started from a preset", () => {
  it("says what the preset will do, starts at the frame shape it asks for, and only remembers the choice", async () => {
    invoke.mockImplementation(backend());
    const created = vi.fn();
    render(<NewFilm kind="idea" preset="vertical_micro_drama" onClose={() => {}} onCreated={created} />);
    expect(screen.getAllByText(/Vertical Micro-Drama/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Nothing is made or charged/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Write or paste the story/), { target: { value: "A girl waits." } });
    fireEvent.click(screen.getByRole("button", { name: "Create film" }));
    await waitFor(() => expect(created).toHaveBeenCalledWith("C:/films/Night"));
    const make = sent("film").find((a) => (a as { action: string }).action === "create") as { data: { aspect_ratio: string } };
    expect(make.data.aspect_ratio).toBe("9:16");
    const p = sent("presets") as { dir: string; action: string; data: { stack: string[] } }[];
    expect(p).toEqual([{ dir: "C:/films/Night", action: "set_pending", data: { stack: ["vertical_micro_drama"], setup: { episodes: 10 } } }]);        // remembered; never applied here
  });

  it("still makes the film if the choice cannot be remembered, and makes no preset call when none was chosen", async () => {
    invoke.mockImplementation(backend(true));
    const created = vi.fn();
    render(<NewFilm kind="idea" preset="documentary" onClose={() => {}} onCreated={created} />);
    fireEvent.change(screen.getByPlaceholderText(/Write or paste the story/), { target: { value: "A river." } });
    fireEvent.click(screen.getByRole("button", { name: "Create film" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    cleanup(); invoke.mockReset(); invoke.mockImplementation(backend());
    const again = vi.fn();
    render(<NewFilm kind="idea" onClose={() => {}} onCreated={again} />);
    fireEvent.change(screen.getByPlaceholderText(/Write or paste the story/), { target: { value: "A river." } });
    fireEvent.click(screen.getByRole("button", { name: "Create film" }));
    await waitFor(() => expect(again).toHaveBeenCalled());
    expect(sent("presets")).toEqual([]);
  });

  it("sends the length, the episodes and any layer you changed, with the preset first so yours come after it", async () => {
    invoke.mockImplementation(backend());
    const created = vi.fn();
    render(<NewFilm kind="idea" preset="vertical_micro_drama" onClose={() => {}} onCreated={created} />);
    fireEvent.change(screen.getByLabelText("Length to aim for"), { target: { value: "60" } });
    fireEvent.change(screen.getByLabelText("Episodes in the season"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Visual style"), { target: { value: "storybook_epic" } });
    fireEvent.change(screen.getByLabelText("Colour"), { target: { value: "warm_storybook_balanced" } });
    fireEvent.change(screen.getByPlaceholderText(/Write or paste the story/), { target: { value: "A girl waits." } });
    fireEvent.click(screen.getByRole("button", { name: "Create film" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect((sent("presets") as { data: unknown }[])[0].data).toEqual({ stack: ["vertical_micro_drama", "storybook_epic", "warm_storybook_balanced"], setup: { length: 60, episodes: 12 } });
  });

  it("asks for episodes only for a series preset, and sends no setup when nothing was changed", async () => {
    invoke.mockImplementation(backend());
    render(<NewFilm kind="idea" preset="documentary" onClose={() => {}} onCreated={() => {}} />);
    expect(screen.queryByLabelText("Episodes in the season")).toBeNull();
    expect(screen.getByLabelText("Length to aim for")).toHaveValue("");
    fireEvent.change(screen.getByPlaceholderText(/Write or paste the story/), { target: { value: "A river." } });
    fireEvent.click(screen.getByRole("button", { name: "Create film" }));
    await waitFor(() => expect(sent("presets")).toHaveLength(1));
    expect((sent("presets") as { data: unknown }[])[0].data).toEqual({ stack: ["documentary"], setup: {} });
  });
});
