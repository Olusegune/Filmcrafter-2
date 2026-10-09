import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { ExtendCard, extendSentence, type ExtendInfo } from "../Extend";

const info = (over: Partial<ExtendInfo> = {}): ExtendInfo => ({ shot: "S01-04", can_extend: true, advice: [], shot_seconds: 12, take_seconds: 8, short_seconds: 4, suggest_seconds: 4, ...over });

describe("what Extend says it will do", () => {
  it("says how long the shot and the take are, what is rendered, and that it covers the shot", () => {
    const t = extendSentence(info());
    expect(t).toContain("This shot is 12 s but its take is 8 s");
    expect(t).toContain("the last 4 s just hold the final frame");
    expect(t).toContain("renders 4 s more");
    expect(t).toContain("which covers the shot");
  });
  it("is honest when one continuation still leaves it short", () => {
    expect(extendSentence(info({ shot_seconds: 20, short_seconds: 12, suggest_seconds: 8 }))).toContain("4 s would still be short");
  });
  it("says nothing when it cannot extend", () => {
    expect(extendSentence(info({ can_extend: false }))).toBe("");
    expect(extendSentence(info({ suggest_seconds: null }))).toBe("");
  });
  it("renders nothing until the engine has answered (no flash of a wrong card)", () => {
    expect(renderToStaticMarkup(<ExtendCard dir="d" shot={{ id: "S01-04" } as never} jobs={[]} onQueued={() => {}} />)).toBe("");
  });
});
