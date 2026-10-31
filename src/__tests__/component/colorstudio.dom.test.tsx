// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));
const pick = vi.fn();
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: (o: unknown) => pick(o) }));

import { ColorStudioSheet } from "../../ColorStudio";
import type { GradingState } from "../../api";

const RANGES = Object.fromEntries(["exposure", "brightness", "contrast", "highlights", "shadows", "whites", "blacks", "saturation", "vibrance", "hue", "temperature", "tint", "gamma", "lift", "gain"].map((k) => [k, k === "hue" ? [-180, 180, 0] : k === "exposure" ? [-3, 3, 0] : [-1, 1, 0]]));
const state = (over: Partial<GradingState> = {}): GradingState => ({
  revision: 0, grades: { film: {}, scenes: {}, shots: {} }, presets: [], ranges: RANGES as GradingState["ranges"], swing: {}, history: [], spaces: [], picture_space: "rec709",
  luts: [{ id: "a1b2c3d4e5f60718", name: "Warm", kind: "creative", space_in: "rec709", space_out: "rec709", dims: 3, size: 33, favorite: false },
         { id: "0f1e2d3c4b5a6978", name: "Log look", kind: "technical", space_in: "log", space_out: "rec709", dims: 3, size: 33, favorite: false }],
  shots: [{ id: "S01-01", scene: 1, heading: "INT. KITCHEN" }, { id: "S02-01", scene: 2, heading: "EXT. PLATFORM" }], ...over });
const answer = (s: GradingState) => (_c: string, a: { action: string }) => Promise.resolve(a.action === "preview" ? { before: "b.png", after: "a.png" } : s);
afterEach(() => { cleanup(); invoke.mockReset(); pick.mockReset(); });

describe("Color Studio", () => {
  it("saves a changed slider as the grade of the film and says which scope it is for", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    const save = await screen.findByRole("button", { name: "Save grade for the whole film" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Exposure"), { target: { value: "0.5" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("grading", { dir: "p", action: "set_grade", data: { scope: "film", key: null, grade: { exposure: 0.5 } } }));
  });

  it("a double click puts a slider back to zero, and a slider at zero is not part of the grade", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    const c = await screen.findByLabelText("Contrast");
    fireEvent.change(c, { target: { value: "0.3" } });
    expect(c).toHaveValue("0.3");
    fireEvent.doubleClick(c);
    expect(c).toHaveValue("0");
    expect(screen.getByRole("button", { name: /^Save grade for/ })).toBeDisabled();
  });

  it("puts a grade on a scene by its number and on a single shot by its id", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /INT\. KITCHEN/ }));
    fireEvent.change(screen.getByLabelText("Saturation"), { target: { value: "-0.4" } });
    fireEvent.click(screen.getByRole("button", { name: "Save grade for scene 1" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("grading", { dir: "p", action: "set_grade", data: { scope: "scene", key: "1", grade: { saturation: -0.4 } } }));
    fireEvent.click(screen.getByText(/Single shots/));
    fireEvent.click(screen.getByRole("button", { name: "S02-01" }));
    expect(screen.getByRole("heading", { name: "Grade for shot S02-01" })).toBeInTheDocument();
  });

  it("asks the engine for a before and after frame of the grade as it stands on screen, not only the saved one", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    await screen.findByRole("button", { name: /^Save grade for/ });
    fireEvent.change(screen.getByLabelText("Tint"), { target: { value: "0.2" } });
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("grading", { dir: "p", action: "preview", data: { shot: "S01-01", grade: { tint: 0.2 } } }), { timeout: 3000 });
    expect(await screen.findByAltText("With the grade")).toHaveAttribute("src", "p/a.png");
    expect(screen.getByText("After (not saved)")).toBeInTheDocument();
  });

  it("says plainly when a LUT is not for Rec.709 pictures, and shows what it expects", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    const sel = await screen.findByRole("combobox", { name: "Look" });
    expect(screen.getByRole("option", { name: "Log look (not for Rec.709)" })).toBeInTheDocument();
    fireEvent.change(sel, { target: { value: "0f1e2d3c4b5a6978" } });
    expect(screen.getByText(/expects Log pictures/)).toBeInTheDocument();
    expect(screen.getByText(/is not applied/)).toBeInTheDocument();
  });

  it("imports a LUT from the file the person picked, and does nothing when they cancel", async () => {
    invoke.mockImplementation(answer(state()));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    const btn = await screen.findByRole("button", { name: "Import a LUT…" });
    pick.mockResolvedValueOnce(null);
    fireEvent.click(btn);
    await waitFor(() => expect(pick).toHaveBeenCalledTimes(1));
    expect(invoke).not.toHaveBeenCalledWith("grading", expect.objectContaining({ action: "lut_import" }));
    pick.mockResolvedValueOnce("C:\luts\warm.cube");
    fireEvent.click(btn);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("grading", { dir: "p", action: "lut_import", data: { path: "C:\luts\warm.cube" } }));
    expect(pick).toHaveBeenLastCalledWith({ multiple: false, filters: [{ name: "LUT", extensions: ["cube"] }] });
  });

  it("warns when a grade pushes the picture out of range, and shows an engine error as an alert", async () => {
    invoke.mockImplementation(answer(state({ grades: { film: { exposure: 2 }, scenes: {}, shots: {} }, swing: { film: { clipped_whites: true, crushed_blacks: false } } })));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    expect(await screen.findByText(/pushed past white/)).toBeInTheDocument();
    cleanup();
    invoke.mockImplementation((_c: string, a: { action: string }) => a.action === "state" ? Promise.resolve(state()) : a.action === "preview" ? Promise.resolve({ before: "b.png", after: "a.png" }) : Promise.reject("That LUT is not in the library."));
    render(<ColorStudioSheet dir="p" onClose={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Gain"), { target: { value: "0.2" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save grade for/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not in the library");
  });
});
