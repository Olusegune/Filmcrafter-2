import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { LookSuggest } from "../Camera";
import type { LookSuggestion } from "../api";

const s: LookSuggestion = { shot: "S01-04", emotion: "dread", intensity: 8, why: "Fear reads in deep shadow.", proposals: [
  { group: "lighting", term: "lowkey", label: "Low key / chiaroscuro", wording: "" }, { group: "movement", term: "push", label: "Slow push in", wording: "" }] };
const view = (over: Partial<Parameters<typeof LookSuggest>[0]> = {}) => renderToStaticMarkup(<LookSuggest s={s} more={0} busy={false} onUse={() => {}} onUseAll={() => {}} {...over} />);

describe("camera and lighting suggested by the feeling", () => {
  it("names the feeling, says why, and lists each suggestion by what it changes", () => {
    const html = view();
    expect(html).toContain("Suggested for “dread”");
    expect(html).toContain("Fear reads in deep shadow.");
    expect(html).toContain("Lighting");
    expect(html).toContain("Low key / chiaroscuro");
    expect(html).toContain("Movement");
    expect(html).toContain("Slow push in");
  });
  it("offers one button for this shot, and one for every shot only when others have a suggestion", () => {
    expect(view()).toContain("Use these");
    expect(view()).not.toContain("for all");
    expect(view({ more: 3 })).toContain("Use the suggestions for all 4 shots with a feeling");
  });
  it("disables both while saving", () => {
    expect((view({ more: 2, busy: true }).match(/<button[^>]*disabled/g) ?? []).length).toBe(2);
  });
});
