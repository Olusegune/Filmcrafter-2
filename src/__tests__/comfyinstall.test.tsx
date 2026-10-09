import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

import type { ComfyInstallPlan } from "../api";
import { ComfyInstallCard, installFacts } from "../ComfyInstall";

const plan = (over: Partial<ComfyInstallPlan> = {}): ComfyInstallPlan => ({ dest: "C:\Users\me\FilmCrafter ComfyUI", source: "github.com/comfyanonymous/ComfyUI (releases)", ok: true, reason: "", warnings: [],
  gpu: "NVIDIA RTX 3060", vendor: "nvidia", tag: "v0.39.0", asset: { name: "a.7z", size: 2e9, url: "u", sha256: "x" }, download_gb: 2.0, need_gb: 12.8, free_gb: 640.9, ...over });

describe("what the install says before anyone presses the button", () => {
  it("states what, from where, how big, where, and how to remove it", () => {
    const f = Object.fromEntries(installFacts(plan()).map((x) => [x.label, x.value]));
    expect(f.What).toContain("official portable build for your NVIDIA RTX 3060 (v0.39.0)");
    expect(f.What).toContain("nothing else on your computer changes");
    expect(f.From).toContain("github.com/comfyanonymous/ComfyUI");
    expect(f.From).toContain("checksum");
    expect(f.Size).toContain("2 GB to download");
    expect(f.Size).toContain("12.8 GB");
    expect(f.Size).toContain("640.9 GB free");
    expect(f.Where).toBe("C:\Users\me\FilmCrafter ComfyUI");
    expect(f["To remove it"]).toBe("delete that folder");
  });
  it("says nothing when there is nothing to install, and copes with an unknown free space", () => {
    expect(installFacts(plan({ ok: false }))).toEqual([]);
    expect(installFacts(plan({ asset: undefined }))).toEqual([]);
    expect(installFacts(plan({ free_gb: null })).find((x) => x.label === "Size")!.value).not.toContain("free");
  });
});

describe("the card", () => {
  it("shows a looking-up line until the engine answers, never a button that does nothing", () => {
    const html = renderToStaticMarkup(<ComfyInstallCard onInstalled={() => {}} />);
    expect(html).toContain("Looking up the latest ComfyUI");
    expect(html).not.toContain("Install ComfyUI (");
  });
});
