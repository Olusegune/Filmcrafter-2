import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ChangesSince } from "../ChangesSince";
import { TrackRecord, trackLine } from "../TrackRecord";
import type { ChangesSince as Changes, ModelTrack, TrackStats } from "../api";

const take = { id: "j1", model: "m", created: 1 };
const view = (c: Changes | null, busy = false) => renderToStaticMarkup(<ChangesSince changes={c} busy={busy} />);

describe("what changed since the last take", () => {
  it("shows nothing before there is a take", () => {
    expect(view(null)).toBe("");
    expect(view({ has_take: false, same: false, changes: [], note: "no take" })).toBe("");
  });
  it("says in words when nothing the model is told or shown has changed", () => {
    const html = view({ has_take: true, same: true, changes: [], note: "Nothing the model is told or shown has changed since this take, so a new render would look much the same.", take });
    expect(html).toContain("Since the last take:");
    expect(html).toContain("would look much the same");
    expect(view({ has_take: true, same: true, changes: [], note: "x", take }, true)).toContain("checking…");
  });
  it("lists each change with what kind it is, added and removed sentences marked, and the count", () => {
    const html = view({ has_take: true, same: false, take, note: "", changes: [
      { kind: "keyframe", text: "A different keyframe." }, { kind: "prompt_removed", text: "The light is low." }, { kind: "prompt_added", text: "A low-key light." }, { kind: "prompt_more", text: "…and 3 more prompt changes." }] });
    expect(html).toContain("3 changes to what the model is told or shown");
    expect(html).toContain("Keyframe");
    expect(html).toContain("Removed from the prompt");
    expect(html).toContain("− The light is low.");
    expect(html).toContain("+ A low-key light.");
    expect(html).toContain("…and 3 more prompt changes.");
  });
  it("opens a short list and leaves a long one folded", () => {
    const rows = (n: number) => Array.from({ length: n }, (_, i) => ({ kind: "prompt_added", text: `Sentence ${i}.` }));
    expect(view({ has_take: true, same: false, take, note: "", changes: rows(3) })).toMatch(/<details[^>]* open/);
    expect(view({ has_take: true, same: false, take, note: "", changes: rows(9) })).not.toMatch(/<details[^>]* open/);
    expect(view({ has_take: true, same: false, take, note: "", changes: rows(1) })).toContain("1 change to");
  });
});

const m = (over: Partial<ModelTrack> = {}): ModelTrack => ({ provider: "kie", model: "seedance", takes: 7, failed: 0, failures: {}, cost: 0, reviews: {}, sound: {}, sung: 0, ...over });

describe("how the model has done in this project", () => {
  it("says there is nothing yet for a model with no takes", () => {
    expect(trackLine(undefined, "Seedance 2")).toBe("No takes with Seedance 2 in this project yet.");
  });
  it("counts takes, failures with their reasons, reviews, sound and spend, in plain words", () => {
    const line = trackLine(m({ takes: 7, failed: 3, failures: { service: 2, credits: 1 }, reviews: { good: 4, needs_attention: 2 }, sung: 5, sound: { in_time: 3, own_audio: 2 }, cost: 4.5 }), "Seedance 2");
    expect(line).toBe("Seedance 2 in this project: 7 takes; 3 failed (2 provider busy or down, 1 out of credits); 4 of 6 reviewed took as good; sound in time with the song on 3 of 5 sung takes, made its own sound on 2; $4.50 spent.");
    expect(trackLine(m({ takes: 1 }), "X")).toBe("X in this project: 1 take.");
  });
  it("shows nothing when no model has been used, and lists the other models folded away", () => {
    expect(renderToStaticMarkup(<TrackRecord stats={null} model="a" />)).toBe("");
    expect(renderToStaticMarkup(<TrackRecord stats={{ models: [], checked_now: 0 }} model="a" />)).toBe("");
    const stats: TrackStats = { models: [m({ model: "a" }), m({ model: "b", takes: 2 })], checked_now: 0 };
    const html = renderToStaticMarkup(<TrackRecord stats={stats} model="a" title="Model A" />);
    expect(html).toContain("Model A in this project: 7 takes.");
    expect(html).toContain("b in this project: 2 takes.");
    expect(html).toContain("only says something once there are a few");
  });
});
