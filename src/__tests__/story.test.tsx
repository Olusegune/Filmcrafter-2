import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));

import { guessKind, isStoryFile, ladderAt, LADDER, minutes, openAdvice, previewLine, STAGES, STORY_KINDS, storyState, titleFromFile } from "../storyView";
import { NewFilm } from "../NewFilm";
import type { FilmAdvice } from "../api";

const SCRIPT = "INT. KITCHEN - MORNING\n\nSarah pours tea.\n";

describe("how a story is recognised", () => {
  it("calls text with scene headings a screenplay, wherever it came from", () => {
    expect(guessKind("a.txt", SCRIPT)).toBe("screenplay");
    expect(guessKind("a.fountain", "no headings at all")).toBe("screenplay");
    expect(guessKind("a.txt", "EXT. ROAD - DAY\nA car.")).toBe("screenplay");
  });
  it("tells an idea, a synopsis, an outline and a treatment apart by length and shape", () => {
    expect(guessKind("n.txt", "A widow finds her husband's second phone.")).toBe("idea");
    expect(guessKind("n.txt", Array(200).fill("word").join(" "))).toBe("synopsis");
    expect(guessKind("n.txt", "1. Opening\n2. Middle\n3. End")).toBe("outline");
    expect(guessKind("n.txt", Array(900).fill("word").join(" "))).toBe("treatment");
    expect(guessKind("n.pdf", Array(900).fill("word").join(" "))).toBe("screenplay");
  });
  it("never throws on odd text", () => { for (const t of ["", "   ", "\n", "x".repeat(10000)]) expect(() => guessKind("", t)).not.toThrow(); });
  it("accepts the story files the engine can read, and nothing else", () => {
    for (const f of ["a.txt", "b.MD", "c.fountain", "d.pdf", "e.docx"]) expect(isStoryFile(f)).toBe(true);
    for (const f of ["a.exe", "b.mp3", "c", "d.png"]) expect(isStoryFile(f)).toBe(false);
  });
  it("makes a title from a file name", () => {
    expect(titleFromFile("C:\\scripts\\last_train-final.fountain")).toBe("Last Train Final");
    expect(titleFromFile("")).toBe("");
  });
});

describe("saying what was found", () => {
  it("says lengths in plain words", () => {
    expect(minutes(0)).toBe("");
    expect(minutes(45)).toBe("about 50 seconds");
    expect(minutes(144)).toBe("about 2.4 minutes");
    expect(minutes(1200)).toBe("about 20 minutes");
  });
  it("describes a screenplay by its scenes, speaking characters and places", () => {
    expect(previewLine({ kind: "screenplay", words: 61, scenes: 3, characters: 2, locations: 3, seconds: 144, has_headings: true })).toBe("3 scenes · 2 speaking characters · 3 places · about 2.4 minutes");
    expect(previewLine({ kind: "screenplay", words: 5, scenes: 1, characters: 1, locations: 1, seconds: 0, has_headings: true })).toBe("1 scene · 1 speaking character · 1 place");
    expect(previewLine({ kind: "idea", words: 12, scenes: 0, characters: 0, locations: 0, seconds: 0, has_headings: false })).toBe("12 words");
    expect(previewLine(null)).toBe("");
  });
  it("puts structure advice first and leaves out what was set aside", () => {
    const a = (id: string, topic: string, status: FilmAdvice["status"] = "open"): FilmAdvice => ({ id, topic, text: id, scene: null, status });
    expect(openAdvice([a("p", "production"), a("s", "structure"), a("v", "visual storytelling"), a("d", "pacing", "dismissed")]).map((x) => x.id)).toEqual(["s", "v", "p"]);
  });
  it("says where the story stands", () => {
    expect(storyState({ kind: "screenplay", locked: 2, as_is: 2, current: 2 })).toBe("Story locked (version 2)");
    expect(storyState({ kind: "screenplay", locked: 2, as_is: null, current: 3 })).toContain("draft");
    expect(storyState({ kind: "screenplay", locked: null, as_is: 1, current: 1 })).toBe("Using the story as it is");
    expect(storyState({ kind: "idea", locked: null, as_is: null, current: 1 })).toContain("idea");
  });
});

describe("the way from a spark to a film", () => {
  it("has the ladder and the stages in order, and every stage is built", () => {
    expect(LADDER[0]).toBe("Logline"); expect(LADDER[LADDER.length - 1]).toBe("Screenplay");
    expect(ladderAt("logline")).toBe(0); expect(ladderAt("Screenplay")).toBe(5); expect(ladderAt("nonsense")).toBe(0);
    expect(STAGES.map((s) => s.label)).toEqual(["Story", "Cast & World", "Shots", "Storyboard", "Make film", "Review", "Export"]);
    expect(STAGES.filter((s) => s.ready).map((s) => s.id)).toEqual(["story", "cast", "shots", "storyboard", "make", "review", "export"]);
  });
});

describe("the New film sheet", () => {
  it("opens by asking how the story begins, with every kind on offer and the promise that it is kept as given", () => {
    const html = renderToStaticMarkup(<NewFilm onClose={() => {}} onCreated={() => {}} />);
    for (const k of STORY_KINDS) expect(html).toContain(k.label);
    expect(html).toContain("kept exactly as it is");
    expect(html).toContain("choose a story file");
    expect(html).not.toContain("Create film");                         // nothing to create until a story is brought
  });
  it("goes straight to the story box when started from an idea", () => {
    const html = renderToStaticMarkup(<NewFilm kind="idea" onClose={() => {}} onCreated={() => {}} />);
    expect(html).toContain("Create film");
    expect(html).toContain("never rewrites your story");
    expect(html).toContain("an idea or logline");
  });
});
