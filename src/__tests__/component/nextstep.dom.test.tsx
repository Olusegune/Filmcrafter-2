// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));

import { NextStep } from "../../NextStep";

const report = (over = {}) => ({ items: [{ id: "x", level: "note", go: "export", what: "Export it.", shot: null }], next: null, counts: { fix: 0, look: 0, note: 1 }, ready: true, shots: 3, unread: [], note: "", ...over });
afterEach(() => { cleanup(); invoke.mockReset(); });

describe("the next-step line", () => {
  it("offers Polish my film only once the film is ready, and the button starts it", async () => {
    invoke.mockResolvedValue(report());
    const polish = vi.fn();
    render(<NextStep dir="f" refresh="a" onGo={() => {}} onPolish={polish} />);
    fireEvent.click(await screen.findByRole("button", { name: "Polish my film" }));
    expect(polish).toHaveBeenCalledOnce();
  });

  it("does not offer it while something still needs doing, or where the Studio cannot be reached", async () => {
    invoke.mockResolvedValue(report({ ready: false, next: { id: "y", level: "fix", go: "make", what: "Make the pictures.", shot: null } }));
    const { unmount } = render(<NextStep dir="f" refresh="a" onGo={() => {}} onPolish={() => {}} />);
    await screen.findByText(/Make the pictures/);
    expect(screen.queryByRole("button", { name: "Polish my film" })).toBeNull();
    unmount();
    invoke.mockResolvedValue(report());
    render(<NextStep dir="f" refresh="b" onGo={() => {}} />);
    await screen.findByText(/ready to export/);
    expect(screen.queryByRole("button", { name: "Polish my film" })).toBeNull();
  });
});

describe("the polish walkthrough in the Studio", () => {
  it("goes cut, colour, titles, each closing into the next, and can be stopped", () => {
    const t = readFileSync("src/Studio.tsx", "utf8");
    expect(t).toContain('polishNext(["smart", "color", "motion"])');
    for (const s of ["setSmartOpen", "setColorOpen", "setMotionOpen"]) expect(t).toContain(`closeThen(${s})`);
    expect(t).toMatch(/Stop here/);
  });
});
