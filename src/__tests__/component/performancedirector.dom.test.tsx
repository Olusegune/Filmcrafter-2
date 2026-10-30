// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));

import { ArcFlags, FieldRow, NudgeRow, PeopleProfiles, SceneNotes } from "../../PerformanceDirector";
import { BeatsView } from "../../ActingDepth";
import type { Breakdown, CastProfiles, NudgeState, PField } from "../../api";

const f = (value: string, source: "auto" | "you" = "auto", from = "the shots"): PField => ({ value, source, from });
const scene = (over = {}) => ({
  number: 1, heading: "INT. KITCHEN - MORNING", shots: ["S01-01", "S01-02"],
  fields: { purpose: f("She cannot ask him to stay."), start: f(""), end: f(""), tension: f("") },
  people: [{ name: "Sarah", wants: f("To keep him"), obstacle: f(""), outward: f(""), inner: f(""), hiding: f("") }],
  subtext: [{ id: "S01-02:0", shot: "S01-02", person: "Sarah", says: "I'm fine.", means: f("Sarah may be hiding how they really feel"), confidence: "medium" as const, why: "A reading, not a fact." }],
  turning_points: [], nonverbal: [{ shot: "S01-01", what: "Sarah pours tea." }], reactions: [{ shot: "S01-03", person: "John", what: "listens to Sarah" }], ...over,
});
const breakdown = (): Breakdown => ({ has_contracts: true, scenes: [scene(), { ...scene({ heading: "EXT. PLATFORM - NIGHT", subtext: [], people: [] }), number: 2 }] });
afterEach(() => { cleanup(); invoke.mockReset(); });

describe("one part of the breakdown", () => {
  const row = (field: PField, over = {}) => { const h = { onSave: vi.fn(), onReset: vi.fn(), onKeep: vi.fn() }; render(<FieldRow id="1-purpose" label="Purpose" field={field} {...h} {...over} />); return h; };
  it("shows a draft as a draft and offers to keep it", () => {
    const h = row(f("A draft."));
    expect(screen.getByText("Draft")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep this" }));
    expect(h.onKeep).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });
  it("offers Save only after a change, and Undo puts the words back", () => {
    const h = row(f("A draft."));
    const box = screen.getByLabelText("Purpose");
    fireEvent.change(box, { target: { value: "My words" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(h.onSave).toHaveBeenCalledWith("My words");
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(box).toHaveValue("A draft.");
  });
  it("marks your own words, and goes back to the draft", () => {
    const h = row(f("Mine", "you", "your edit"));
    expect(screen.getByText("Yours")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to the draft" }));
    expect(h.onReset).toHaveBeenCalled();
  });
  it("says Empty, and has nothing to keep, when nothing is written", () => {
    row(f(""));
    expect(screen.getByText("Empty")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Keep this" })).not.toBeInTheDocument();
  });
});

describe("the scene breakdown", () => {
  it("lists the scenes, flags the lines to check, and quotes the dialogue exactly", async () => {
    invoke.mockResolvedValue(breakdown());
    render(<SceneNotes dir="p" />);
    expect(await screen.findByRole("heading", { name: /Scene 1: INT. KITCHEN - MORNING/ })).toBeInTheDocument();
    expect(screen.getByTitle("1 line that may mean more than they say")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sarah: I'm fine." })).toHaveTextContent("“I'm fine.”");
    expect(screen.getByText(/never changed/)).toBeInTheDocument();
    expect(screen.getByText("A reading")).toBeInTheDocument();
  });
  it("keeps a draft as yours with one call for that part of that scene only", async () => {
    invoke.mockResolvedValueOnce(breakdown()).mockResolvedValueOnce(scene({ fields: { purpose: f("She cannot ask him to stay.", "you", "your edit"), start: f(""), end: f(""), tension: f("") } }));
    render(<SceneNotes dir="p" />);
    const region = await screen.findByLabelText("What this scene is for");
    fireEvent.click(within(region.closest(".pd-field") as HTMLElement).getByRole("button", { name: "Keep this" }));
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "breakdown_accept", data: { scene: 1, path: "purpose" } }));
    expect(invoke).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getAllByText("Yours").length).toBeGreaterThan(0));
  });
  it("writes what a line means under that line's own path, and a person's part under theirs", async () => {
    invoke.mockResolvedValue(breakdown());
    render(<SceneNotes dir="p" />);
    const said = await screen.findByRole("region", { name: "Sarah: I'm fine." });
    fireEvent.change(within(said).getByLabelText("May mean"), { target: { value: "She is terrified he will leave." } });
    fireEvent.click(within(said).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("performance_director", { dir: "p", action: "breakdown_set", data: { scene: 1, path: "subtext.S01-02:0", value: "She is terrified he will leave." } }));
    const person = screen.getByRole("region", { name: "Sarah" });
    fireEvent.change(within(person).getByLabelText("Shows"), { target: { value: "calm and polite" } });
    fireEvent.click(within(person).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("performance_director", { dir: "p", action: "breakdown_set", data: { scene: 1, path: "people.Sarah.outward", value: "calm and polite" } }));
  });
  it("moves between scenes and says so when there are none", async () => {
    invoke.mockResolvedValue(breakdown());
    render(<SceneNotes dir="p" />);
    fireEvent.click(await screen.findByRole("button", { name: /EXT. PLATFORM - NIGHT/ }));
    expect(screen.getByRole("heading", { name: /Scene 2: EXT. PLATFORM - NIGHT/ })).toBeInTheDocument();
    cleanup();
    invoke.mockResolvedValue({ has_contracts: true, scenes: [] });
    render(<SceneNotes dir="p" />);
    expect(await screen.findByText(/no scenes to read yet/)).toBeInTheDocument();
  });
  it("says why when a call fails and changes nothing on screen", async () => {
    invoke.mockResolvedValueOnce(breakdown()).mockRejectedValueOnce("That is not a part of this scene's breakdown.");
    render(<SceneNotes dir="p" />);
    const box = await screen.findByLabelText("What this scene is for");
    fireEvent.change(box, { target: { value: "x" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a part of this scene/);
  });
});

const cast = (): CastProfiles => ({ fields: ["desire"], people: [
  { name: "Sarah", profile: { desire: "", fears: "" }, known: { role: "Lead" }, style: "restrained", gestures: [{ when: "flustered", do: "touches her collar" }] },
  { name: "John", profile: { desire: "to leave" }, known: {}, style: "", gestures: [] }] });

describe("what a person is like", () => {
  it("shows what the cast already says, read only, beside the fields", async () => {
    invoke.mockImplementation((_c: string, args: { action: string }) => Promise.resolve(args.action === "kind_options" ? { kinds: [] } : cast()));
    render(<PeopleProfiles dir="p" />);
    const known = await screen.findByRole("region", { name: /What the cast already says about Sarah/ });
    expect(known).toHaveTextContent(/roleLead/);
    expect(known).toHaveTextContent("restrained");
    expect(known).toHaveTextContent(/when flustered: touches her collar/);
    expect(screen.getByTitle("Fields you have filled in")).toHaveTextContent("1");
  });
  it("saves only the fields that changed, for that person", async () => {
    invoke.mockImplementation((_c: string, args: { action: string }) => Promise.resolve(args.action === "kind_options" ? { kinds: [] } : cast()));
    render(<PeopleProfiles dir="p" />);
    await screen.findByText("About Sarah");
    const save = screen.getByRole("button", { name: "Save Sarah" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Their longer goal."), { target: { value: "to be taken seriously" } });
    fireEvent.click(save);
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "character_set", data: { person: "Sarah", fields: { desire: "to be taken seriously" } } }));
  });
  it("clears everything for one person only, and only when something is filled in", async () => {
    invoke.mockImplementation((_c: string, args: { action: string }) => Promise.resolve(args.action === "kind_options" ? { kinds: [] } : cast()));
    render(<PeopleProfiles dir="p" />);
    await screen.findByText("About Sarah");
    expect(screen.queryByRole("button", { name: /Clear everything/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^John/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Clear everything for John" }));
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "character_clear", data: { person: "John" } }));
  });
});

const nudges = (level = 0): NudgeState => ({ shot: "S01-02", nudges: [{ id: "restrained", label: "More restrained", level, levels: 2 }, { id: "eyes", label: "Let the eyes tell the story", level: 0, levels: 1 }] });

describe("direction for a shot", () => {
  it("turns a choice on, steps a two-strength choice up, and back off", async () => {
    invoke.mockResolvedValueOnce(nudges(0)).mockResolvedValueOnce(nudges(1)).mockResolvedValueOnce(nudges(2)).mockResolvedValueOnce(nudges(0));
    render(<NudgeRow dir="p" shotId="S01-02" />);
    const btn = await screen.findByRole("button", { name: "More restrained" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "nudge_set", data: { shot: "S01-02", nudge: "restrained", level: 1 } }));
    fireEvent.click(await screen.findByRole("button", { name: /More restrained · ●/ }));
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "nudge_set", data: { shot: "S01-02", nudge: "restrained", level: 2 } }));
    fireEvent.click(await screen.findByRole("button", { name: /More restrained · ●●/ }));
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "nudge_set", data: { shot: "S01-02", nudge: "restrained", level: 0 } }));
  });
});

describe("beats, version 2", () => {
  const beat = { t0: 0, t1: 2, what: "She looks up", eyes: "toward John", change: "dread to relief", source: "auto" as const, confidence: "low" as const };
  const view = (over = {}) => { const h = { onChange: vi.fn(), onSave: vi.fn(), onClear: vi.fn(), onWrite: vi.fn(), onSuggest: vi.fn() }; render(<BeatsView seconds={4} source={null} beats={[beat]} dirty={false} busy="" err="" {...h} {...over} />); return h; };
  it("offers the free suggestion apart from the priced Director, and says a suggestion is automatic", () => {
    const h = view({ note: "A rule-based starting point." });
    fireEvent.click(screen.getByRole("button", { name: "Suggest beats (free)" }));
    expect(h.onSuggest).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Write with the Director/ })).toBeInTheDocument();
    expect(screen.getByText(/Suggested automatically \(low confidence\)/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("A rule-based starting point.");
    expect(screen.getByText(/eyes: toward John · what changes: dread to relief/)).toBeInTheDocument();
  });
  it("lets a beat carry on into the next shot", () => {
    const h = view();
    fireEvent.click(screen.getByLabelText(/Carries on into the next shot/));
    expect(h.onChange).toHaveBeenCalledWith([{ ...beat, continues: true }]);
  });
  it("has no suggest button when none is wired", () => {
    view({ onSuggest: undefined });
    expect(screen.queryByRole("button", { name: /Suggest beats/ })).not.toBeInTheDocument();
  });
});

describe("what kind of character", () => {
  const answer = (a: string) => a === "kind_options" ? { kinds: [{ id: "human", label: "A person" }, { id: "robot", label: "A robot or machine" }] } : cast();
  it("saves the kind chosen for that person only", async () => {
    invoke.mockImplementation((_c: string, args: { action: string }) => Promise.resolve(answer(args.action)));
    render(<PeopleProfiles dir="p" />);
    const pick = await screen.findByRole("combobox", { name: "What kind of character" });
    await screen.findByRole("option", { name: "A robot or machine" });
    fireEvent.change(pick, { target: { value: "robot" } });
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("performance_director", { dir: "p", action: "character_set", data: { person: "Sarah", fields: { kind: "robot" } } }));
  });
});

describe("the emotional arc check", () => {
  const arc = (dismissed: string[] = []) => ({ sections: ["A", "B"], dismissed, people: [{ name: "Sarah", source: "you", dismissed: dismissed.length,
    track: [{ section: "A", emotion: "calm", intensity: 2 }, { section: "B", emotion: "furious", intensity: 8 }],
    flags: dismissed.length ? [] : [{ id: "Sarah|abrupt|A>B", kind: "abrupt", scenes: ["A", "B"], message: "Sarah goes from calm to furious." }] }] });
  it("points at a place worth a look and lets it be dismissed", async () => {
    invoke.mockImplementation((_c: string, args: { action: string }) => Promise.resolve(args.action === "continuity_dismiss" ? arc(["Sarah|abrupt|A>B"]) : arc()));
    render(<ArcFlags dir="p" />);
    expect(await screen.findByText(/Sarah goes from calm to furious/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Dismiss: Sarah goes from calm/ }));
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("performance_director", { dir: "p", action: "continuity_dismiss", data: { flag: "Sarah|abrupt|A>B", undo: false } }));
    expect(await screen.findByText(/Nothing stands out/)).toBeInTheDocument();
    expect(screen.getByText(/1 dismissed/)).toBeInTheDocument();
  });
  it("explains what to do when no arcs are written", async () => {
    invoke.mockResolvedValue({ sections: [], dismissed: [], people: [{ name: "Sarah", track: [], flags: [], dismissed: 0 }] });
    render(<ArcFlags dir="p" />);
    expect(await screen.findByText(/at least two scenes/)).toBeInTheDocument();
  });
});
