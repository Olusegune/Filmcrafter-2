// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));

import { CutLane, useCut } from "../../CutLane";
import type { Cut } from "../../api";

const FT = 254_016_000_000 / 24;
const clip = (id: string, shot: string, a: number, b: number, inn = 0) => ({ id, shot, start: a * FT, source_in: inn * FT, duration: (b - a) * FT, take: null, start_s: a / 24, duration_s: (b - a) / 24, source_in_s: inn / 24, start_frame: a, frames: b - a });
const cut = (over: Partial<Cut> = {}): Cut => ({ stored: false, unplaced: [], orphans: [], can_undo: false, can_redo: false, history: [],
  sequence: { fps: [24, 1], frame_ticks: FT, ticks_per_second: 254_016_000_000, length: 240 * FT, length_s: 10, tracks: [{ id: "V1", kind: "video", locked: false, hidden: false, muted: false, clips: [clip("c1", "S1", 0, 96), clip("c2", "S2", 96, 240, 12)] }],
    markers: [{ id: "m1", at: 120 * FT, at_s: 5, name: "turn" }], ranges: [] }, ...over });

function Host({ time = 2, onSeek = () => {}, free = [] as { start: number }[] }) {
  const s = useCut("p", true, time);
  return <div><CutLane s={s} pps={40} top={0} time={time} width={600} onSeek={onSeek} free={free} /><span data-testid="sel">{s.selected ?? ""}</span></div>;
}
const answer = (c: Cut) => () => Promise.resolve(c);
afterEach(() => { cleanup(); invoke.mockReset(); });
const edits = () => invoke.mock.calls.filter(([, a]) => a.action === "edit").map(([, a]) => a.data);

describe("the cut lane", () => {
  it("shows each clip with its name and time, how far into its take a trimmed clip starts, and the marker", async () => {
    invoke.mockImplementation(answer(cut()));
    render(<Host />);
    expect(await screen.findByRole("button", { name: "S1 from 0:00.00 for 0:04.00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "S2 from 0:04.00 for 0:06.00" })).toBeInTheDocument();
    expect(screen.getByText("in 0:00.50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Marker turn at 0:05.00/ })).toBeInTheDocument();
    expect(screen.getByText(/As planned/)).toBeInTheDocument();
  });

  it("clicking a clip chooses it and takes the playhead to its start", async () => {
    const seek = vi.fn();
    invoke.mockImplementation(answer(cut()));
    render(<Host onSeek={seek} />);
    fireEvent.click(await screen.findByRole("button", { name: /^S2 from/ }));
    expect(seek).toHaveBeenCalledWith(4);
    expect(screen.getByTestId("sel")).toHaveTextContent("c2");
  });

  it("Split cuts the clip under the playhead and Delete the chosen one, each as one edit with the engine's own names", async () => {
    invoke.mockImplementation(answer(cut()));
    render(<Host time={2} />);
    fireEvent.click(await screen.findByRole("button", { name: "Split" }));
    await waitFor(() => expect(edits()).toContainEqual({ op: "split", at: 2, clip: "c1" }));
    fireEvent.click(screen.getByRole("button", { name: /^S2 from/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(edits()).toContainEqual({ op: "delete", clip: "c2", ripple: false }));
  });

  it("the keys the Studio sends do the same: trim to the playhead keeps the ripple choice, a marker goes at the playhead, undo and redo go to the engine", async () => {
    invoke.mockImplementation(answer(cut({ can_undo: true })));
    render(<Host time={3} />);
    await screen.findByRole("button", { name: /^S1 from/ });
    const press = (k: string) => act(() => { window.dispatchEvent(new CustomEvent("pf-cut-key", { detail: k })); });
    press("trim_out");
    await waitFor(() => expect(edits()).toContainEqual({ op: "trim", clip: "c1", edge: "out", to: 3, ripple: false }));
    fireEvent.click(screen.getByText("More"));
    fireEvent.click(screen.getByLabelText(/Ripple: what follows/));
    press("trim_in");
    await waitFor(() => expect(edits()).toContainEqual({ op: "trim", clip: "c1", edge: "in", to: 3, ripple: true }));
    press("marker");
    await waitFor(() => expect(edits()).toContainEqual({ op: "marker_set", at: 3 }));
    press("ripple_delete");
    await waitFor(() => expect(edits()).toContainEqual({ op: "delete", clip: "c1", ripple: true }));
    press("undo");
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("editing", { dir: "p", action: "undo", data: {} }));
    press("redo");
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("editing", { dir: "p", action: "redo", data: {} }));
  });

  it("says plainly what is not in the film, offers to place it, and says when a layer now starts after the end", async () => {
    invoke.mockImplementation(answer(cut({ unplaced: ["S3"], orphans: [] })));
    render(<Host free={[{ start: 12 }]} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Shot S3 is not in the cut");
    fireEvent.click(screen.getByRole("button", { name: "Place it" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("editing", { dir: "p", action: "place_missing", data: {} }));
    cleanup();
    invoke.mockImplementation(answer(cut()));
    render(<Host free={[{ start: 12 }]} />);
    expect(await screen.findByRole("status")).toHaveTextContent("1 layer starts after the end of the cut");
  });

  it("shows the engine's refusal as an alert and changes nothing on screen", async () => {
    invoke.mockImplementation((_n: string, a: { action: string }) => a.action === "edit" ? Promise.reject("There is no clip to cut there (a cut has to fall inside a clip, not on its edge).") : Promise.resolve(cut()));
    render(<Host time={4} />);
    fireEvent.click(await screen.findByRole("button", { name: "Split" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no clip to cut there/);
    expect(screen.getAllByRole("button", { name: /^S\d from/ })).toHaveLength(2);
  });

  it("asks which clip when there is none chosen and the playhead is on no clip, and disables the tools on a locked track", async () => {
    invoke.mockImplementation(answer(cut()));
    render(<Host time={20} />);
    await screen.findByRole("button", { name: /^S1 from/ });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Choose a clip first/);
    cleanup();
    const locked = cut();
    locked.sequence.tracks[0].locked = true;
    invoke.mockImplementation(answer(locked));
    render(<Host />);
    expect(await screen.findByRole("button", { name: "Split" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });

  it("Alt and an arrow key nudge a clip a frame, and Shift makes it a second", async () => {
    invoke.mockImplementation(answer(cut()));
    render(<Host />);
    const b = await screen.findByRole("button", { name: /^S2 from/ });
    fireEvent.keyDown(b, { key: "ArrowRight", altKey: true });
    await waitFor(() => expect(edits()).toContainEqual({ op: "move", clip: "c2", to: 4 + 1 / 24, ripple: false }));
    fireEvent.keyDown(b, { key: "ArrowLeft", altKey: true, shiftKey: true });
    await waitFor(() => expect(edits()).toContainEqual({ op: "move", clip: "c2", to: 3, ripple: false }));
  });
});
