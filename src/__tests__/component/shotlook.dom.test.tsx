// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { LookPicker } from "../../Looks";
import type { StyleBibleRead } from "../../api";
import { ShotLook } from "../../ShotLook";

const read: StyleBibleRead = { style: { id: "claymation", name: "Claymation", prompt: "" }, scenes: [], shots: {}, precedence: [],
  styles: [{ id: "claymation", name: "Claymation", group: "", description: "" }, { id: "anime", name: "Anime", group: "", description: "" }] };
afterEach(() => { cleanup(); invoke.mockReset(); });

describe("the look of one shot, clicked", () => {
  it("saves a pick for that shot only and reports the new state", async () => {
    invoke.mockResolvedValue({ ...read, shots: { "S01-01": "anime" } });
    const onChanged = vi.fn();
    render(<ShotLook dir="p" shotId="S01-01" own={read} filmLook="claymation" sceneLook="claymation" onChanged={onChanged} />);
    expect(screen.getByRole("option", { name: /Same as its film \(Claymation\)/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Look for this shot"), { target: { value: "anime" } });
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...read, shots: { "S01-01": "anime" } }));
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenCalledWith("stylebible", { dir: "p", action: "set_shot", data: { shot: "S01-01", style: "anime" } });
  });

  it("clears the shot's own look with the first option", async () => {
    invoke.mockResolvedValue(read);
    render(<ShotLook dir="p" shotId="S01-01" own={{ ...read, shots: { "S01-01": "anime" } }} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} />);
    expect(screen.getByLabelText("Look for this shot")).toHaveValue("anime");
    fireEvent.change(screen.getByLabelText("Look for this shot"), { target: { value: "" } });
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("stylebible", { dir: "p", action: "set_shot", data: { shot: "S01-01", style: null } }));
  });

  it("says why when the save fails, and reports no change", async () => {
    invoke.mockRejectedValue("That shot id is not valid.");
    const onChanged = vi.fn();
    render(<ShotLook dir="p" shotId="S01-01" own={read} filmLook="claymation" sceneLook="claymation" onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Look for this shot"), { target: { value: "anime" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/not valid/);
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("opens when the shot has its own look and stays folded when it has none", () => {
    const { container, rerender } = render(<ShotLook dir="p" shotId="S01-01" own={read} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} />);
    expect(container.querySelector("details")).not.toHaveAttribute("open");
    rerender(<ShotLook dir="p" shotId="S01-01" own={{ ...read, shots: { "S01-01": "anime" } }} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} />);
    expect(container.querySelector("details")).toHaveAttribute("open");
  });
});

describe("the picker opened from the shot's Look chip, clicked", () => {
  const library = [{ id: "claymation", name: "Claymation", group: "Crafts", description: "Hand-made clay.", prompt: "Claymation.", avoid: "", family: "craft" },
    { id: "anime", name: "Anime", group: "Drawn", description: "Cel animation.", prompt: "Anime.", avoid: "", family: "2d" }];
  const open = (shot: Parameters<typeof LookPicker>[0]["shot"], onSave = vi.fn()) => {
    invoke.mockImplementation((cmd: string) => Promise.resolve(cmd === "list_styles" ? library : undefined));
    render(<LookPicker value={{ style: "claymation", notes: "keep her red coat" }} director={true} onCancel={() => {}} onSave={onSave} shot={shot} />);
    return onSave;
  };
  it("saves the look picked, without the film's notes or wording", async () => {
    const onSave = open({ id: "S01-01", own: false, sameAs: "Same as its film (Claymation)", onClear: () => {} });
    fireEvent.click(await screen.findByRole("radio", { name: /Anime/ }));
    fireEvent.click(screen.getByRole("button", { name: "Use Anime" }));
    expect(onSave).toHaveBeenCalledWith({ style: "anime" });
    expect(screen.queryByLabelText(/Your notes/)).not.toBeInTheDocument();
  });
  it("goes back to what the shot inherits with its own button, and does not save a look", async () => {
    const onClear = vi.fn();
    const onSave = open({ id: "S01-01", own: true, sameAs: "Same as its film (Claymation)", onClear });
    fireEvent.click(await screen.findByRole("button", { name: "Same as its film (Claymation)" }));
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
  });
  it("offers no way back when the shot has no look of its own", async () => {
    open({ id: "S01-01", own: false, sameAs: "Same as its film (Claymation)", onClear: () => {} });
    await screen.findByRole("radio", { name: /Anime/ });
    expect(screen.queryByRole("button", { name: "Same as its film (Claymation)" })).not.toBeInTheDocument();
  });
});

describe("the panel", () => {
  it("stays open after the shot's own look is cleared, instead of folding under the pointer", () => {
    const { container, rerender } = render(<ShotLook dir="p" shotId="S01-01" own={{ ...read, shots: { "S01-01": "anime" } }} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} />);
    expect(container.querySelector("details")).toHaveAttribute("open");
    rerender(<ShotLook dir="p" shotId="S01-01" own={read} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} />);
    expect(container.querySelector("details")).toHaveAttribute("open");
  });
});
