import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { ArcStrip, ArcView, BeatsView, GesturesView, priceText, type ArcData, type Beat } from "../ActingDepth";

const noop = () => {};
const beatsView = (over: Partial<Parameters<typeof BeatsView>[0]> = {}) =>
  renderToStaticMarkup(<BeatsView seconds={6.2} source={null} beats={[]} dirty={false} busy="" err="" onChange={noop} onSave={noop} onClear={noop} onWrite={noop} {...over} />);
const beat = (over: Partial<Beat> = {}): Beat => ({ t0: 0, t1: 2, what: "She lifts her hand to the glasses", ...over });

describe("what an AI step says it costs", () => {
  it("is free for a local model and a rough dollar figure otherwise, never zero dollars for an online one", () => {
    expect(priceText({ calls: 1, usd: 0, local: true, note: "" })).toBe("free (your local model)");
    expect(priceText({ calls: 1, usd: 0.0063, local: false, note: "" })).toBe("about $0.01");
    expect(priceText({ calls: 3, usd: 0.0412, local: false, note: "" })).toBe("about $0.04");
  });
});

describe("the acting beats of a shot", () => {
  it("explains what beats are when there are none, and says the model decides without them", () => {
    const html = beatsView();
    expect(html).toContain("Acting beats");
    expect(html).toContain("none yet");
    expect(html).toContain("this shot is 6.2 s");
    expect(html).toContain("No beats: the video model decides the timing");
    expect(html).toContain("Write with the Director…");
    expect(html).not.toContain(">Clear<");                                                  // nothing to clear
  });

  it("lists each beat with its times, what happens and its details, all labelled", () => {
    const html = beatsView({ beats: [beat({ eyes: "toward Emmanuel" }), beat({ t0: 2, t1: 5, what: "A tight smile" })], source: "director" });
    expect(html).toContain("written by the Director");
    expect((html.match(/class="beat"/g) ?? []).length).toBe(2);
    expect(html).toContain('aria-label="Beat 1 starts at (seconds)"');
    expect(html).toContain('aria-label="Beat 2: what happens"');
    expect(html).toContain('value="She lifts her hand to the glasses"');
    expect(html).toContain('value="toward Emmanuel"');
    expect(html).toContain('aria-label="Remove beat 2"');
    expect(html).toContain(">Clear<");
  });

  it("only offers Save when something changed and a beat says something, and stops at six beats", () => {
    expect(beatsView({ beats: [beat()], dirty: false })).toMatch(/<button[^>]*disabled[^>]*>Save beats/);
    expect(beatsView({ beats: [beat()], dirty: true })).not.toMatch(/<button[^>]*disabled[^>]*>Save beats/);
    expect(beatsView({ beats: [beat({ what: "  " })], dirty: true })).toMatch(/<button[^>]*disabled[^>]*>Save beats/);
    expect(beatsView({ beats: [beat()] })).toContain("+ Add a beat");
    expect(beatsView({ beats: Array.from({ length: 6 }, () => beat()) })).not.toContain("+ Add a beat");
  });

  it("disables every action while one is running, and shows an error", () => {
    const html = beatsView({ beats: [beat()], dirty: true, busy: "write", err: "The provider is busy." });
    expect(html).toContain("Writing…");
    expect((html.match(/<button[^>]*disabled/g) ?? []).length).toBeGreaterThanOrEqual(3);
    expect(html).toContain('role="alert"');
    expect(html).toContain("The provider is busy.");
  });
});

const arc: ArcData = { sections: ["Verse 1", "Chorus 1", "Outro 1"], characters: ["Beatrice", "Zara"],
  arcs: { Beatrice: { points: [{ section: "Verse 1", emotion: "stern", intensity: 4, note: "" }, { section: "Chorus 1", emotion: "flustered", intensity: 8, note: "" }], source: "director" }, Zara: { points: [], source: null } } };
const arcView = (data = arc, over: Partial<Parameters<typeof ArcView>[0]> = {}) =>
  renderToStaticMarkup(<ArcView data={data} drafts={{}} dirty={{}} busy="" err="" onEdit={noop} onSave={noop} onWrite={noop} {...over} />);

describe("the emotional arc", () => {
  it("says there is nothing to put a feeling on before the song has been listened to", () => {
    expect(arcView({ sections: [], characters: ["Beatrice"], arcs: {} })).toContain("has not been listened to yet");
  });

  it("shows each character with a strip across the song, their points, and who wrote them", () => {
    const html = arcView();
    expect(html).toContain("Beatrice");
    expect(html).toContain("2 points · written by the Director");
    expect(html).toContain("no arc");                                                          // Zara
    expect(html).toContain('aria-label="Verse 1: stern, 4 of 10; Chorus 1: flustered, 8 of 10"');
    expect(html).toContain('value="stern"');
    expect(html).toContain('aria-label="Beatrice, Chorus 1: how strong, 1 to 10"');
  });

  it("offers only the sections a character does not have yet", () => {
    const html = arcView();
    const beatrice = html.slice(html.indexOf("Add a section to Beatrice"), html.indexOf("Save Beatrice"));
    expect(beatrice).toContain('<option value="Outro 1">');
    expect(beatrice).not.toContain('<option value="Verse 1">');
    const zara = html.slice(html.indexOf("Add a section to Zara"));
    expect(zara).toContain('<option value="Verse 1">');
  });

  it("only saves a character whose arc changed", () => {
    expect(arcView(arc, { dirty: {} })).toMatch(/<button[^>]*disabled[^>]*>Save Beatrice&#x27;s arc/);
    expect(arcView(arc, { dirty: { Beatrice: true } })).not.toMatch(/<button[^>]*disabled[^>]*>Save Beatrice&#x27;s arc/);
  });

  it("brightens a strip cell with the strength of the feeling and dims a section with none", () => {
    const html = renderToStaticMarkup(<ArcStrip sections={["A", "B", "C"]} points={[{ section: "A", emotion: "calm", intensity: 1, note: "" }, { section: "B", emotion: "rage", intensity: 10, note: "" }]} />);
    expect(html).toContain("opacity:0.325");
    expect(html).toContain("opacity:1");
    expect(html).toContain("opacity:0.08");
    expect(html).toContain('title="C: nothing set"');
  });
});

describe("signature gestures", () => {
  const view = (items: Record<string, { when: string; do: string }[]>, dirty = {}) =>
    renderToStaticMarkup(<GesturesView names={["Beatrice", "Zara"]} items={items} dirty={dirty} busy="" err="" onEdit={noop} onSave={noop} />);

  it("lists each character's gestures as 'when … she …' rows, labelled, and counts them", () => {
    const html = view({ Beatrice: [{ when: "flustered", do: "touches the front of her gele" }] });
    expect(html).toContain("1 gesture");
    expect(html).toContain('value="flustered"');
    expect(html).toContain('value="touches the front of her gele"');
    expect(html).toContain('aria-label="Beatrice, gesture 1: when"');
    expect(html).toContain("none");                                                            // Zara
  });

  it("stops offering to add at eight, and only saves a changed character", () => {
    const eight = Array.from({ length: 8 }, (_, i) => ({ when: `w${i}`, do: `d${i}` }));
    expect((view({ Beatrice: eight }).match(/\+ Add a gesture/g) ?? []).length).toBe(1);        // only Zara's
    expect(view({}, {})).toMatch(/<button[^>]*disabled[^>]*>Save Beatrice&#x27;s gestures/);
    expect(view({}, { Beatrice: true })).not.toMatch(/<button[^>]*disabled[^>]*>Save Beatrice&#x27;s gestures/);
  });
});
