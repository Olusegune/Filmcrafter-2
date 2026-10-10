import { readFileSync } from "node:fs";
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
    expect(STAGES.map((s) => s.label)).toEqual(["Story", "Cast & World", "Shots", "Studio", "Export"]);
    expect(STAGES.filter((s) => s.ready).map((s) => s.id)).toEqual(["story", "cast", "shots", "make", "export"]);
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

describe("the Home chase", () => {
  it("is a canvas behind the card, hidden from screen readers, that speeds up when a story is dragged over", async () => {
    const { FilmReel } = await import("../FilmReel");
    const calm = renderToStaticMarkup(<FilmReel active={false} />);
    const fast = renderToStaticMarkup(<FilmReel active />);
    expect(calm).toContain("<canvas");
    expect(calm).toContain("reel-vignette");
    expect(calm).toContain('aria-hidden="true"');
    expect(calm).not.toContain("reel fast");
    expect(fast).toContain("reel fast");
  });
  it("is still with reduced motion: the chase draws one frame and never starts the loop", () => {
    const src = readFileSync("src/FilmReel.tsx", "utf8");
    expect(src).toContain("prefers-reduced-motion: reduce");
    expect(src).toMatch(/if \(!reduce\) raf = requestAnimationFrame\(frame\)/);
    expect(readFileSync("src/film.css", "utf8")).toMatch(/prefers-reduced-motion: reduce\) \{ \.reel-scan, \.dropcard\.story \.btn\.hero/);
  });
});

describe("the chase arithmetic", () => {
  it("makes a closed road around the edge of the box and leaves the middle clear", async () => {
    const { makeTrack } = await import("../chase");
    const t = makeTrack(600, 400);
    expect(t.pts.length).toBe(480);
    expect(t.total).toBeGreaterThan(1400);
    for (const p of t.pts) { expect(p.x).toBeGreaterThanOrEqual(0); expect(p.x).toBeLessThanOrEqual(600); expect(p.y).toBeGreaterThanOrEqual(0); expect(p.y).toBeLessThanOrEqual(400); }
    for (const p of t.pts) expect(Math.hypot((p.x - 300) / 600, (p.y - 200) / 400)).toBeGreaterThan(0.3);        // nothing runs through the words in the middle
  });

  it("finds a point and heading anywhere along a looping road, behind the start too", async () => {
    const { makeTrack, at } = await import("../chase");
    const t = makeTrack(600, 400);
    const a = at(t, 0), b = at(t, t.total), c = at(t, -10);
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(0.01);
    expect(Math.hypot(c.x - at(t, t.total - 10).x, c.y - at(t, t.total - 10).y)).toBeLessThan(0.01);
    const p = at(t, 100), q = at(t, 101);
    expect(Math.hypot(q.x - p.x, q.y - p.y)).toBeGreaterThan(0.5);
    expect(Math.hypot(q.x - p.x, q.y - p.y)).toBeLessThan(1.6);
    expect(Number.isFinite(at(t, 1e9).x)).toBe(true);
  });

  it("puts a camera beside a car and lets it follow with a lag", async () => {
    const { beside, follow, turnBetween, turnToward } = await import("../chase");
    const up = { x: 10, y: 10, angle: 0 };                                          // heading right
    const left = beside(up, 5);
    expect(left.x).toBeCloseTo(10);
    expect(left.y).toBeCloseTo(15);                                                  // a positive side is to the left of the heading: down the page when heading right (y runs down)
    expect(beside(up, 0, 4)).toEqual({ x: 14, y: 10 });
    expect(follow({ x: 0, y: 0 }, { x: 10, y: 20 }, 0.5)).toEqual({ x: 5, y: 10 });
    expect(turnBetween(0.1, 2 * Math.PI - 0.1)).toBeCloseTo(-0.2);                   // the short way round
    expect(turnToward(0, Math.PI / 2, 0.5)).toBeCloseTo(Math.PI / 4);
  });

  it("makes the same city every time", async () => {
    const { seeded } = await import("../chase");
    const a = seeded(7), b = seeded(7);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
    expect(seeded(8)()).not.toBe(seeded(7)());
  });
});

import { neighbours, stageBadge, stageDone, stageLabel } from "../storyView";
import type { FilmProgress } from "../api";

describe("the script reader keeps its width", () => {
  it("is centred by padding, not by auto margins (an auto margin on a flex child shrank a long script to one word per line)", () => {
    const css = readFileSync("src/film.css", "utf8");
    const rules = css.split("}").filter((r) => /\.film-script/.test(r));
    expect(rules.length).toBeGreaterThan(0);
    for (const r of rules) expect(r).not.toMatch(/margin:\s*0 auto/);
    expect(css).toMatch(/\.film-script \{ width: 100%/);
  });
});

describe("progress along the top", () => {
  const p = (over: Partial<FilmProgress> = {}): FilmProgress => ({ story: { kind: "screenplay", locked: true, as_is: true }, cast: { characters: 11, places: 7, pictures: 0, style: true }, shots: { count: 48, edited: 0 },
    make: { shots: 48, storyboard: 12, keyframe: 0, video: 0 }, ...over });
  it("never throws on a reply with a part missing", () => {
    const partial = { story: { kind: "idea", locked: false, as_is: false } } as unknown as FilmProgress;
    for (const id of ["story", "cast", "shots", "make", "export"]) { expect(stageBadge(id, partial)).toBe(""); expect(stageDone(id, partial)).toBe(false); }
    expect(stageBadge("story", {} as FilmProgress)).toBe("");
  });
  it("says how far each step is, and nothing before there is something to say", () => {
    expect(stageBadge("story", p())).toBe("locked");
    expect(stageBadge("cast", p())).toBe("11 · 7");
    expect(stageBadge("make", p())).toBe("");
    expect(stageBadge("make", p({ make: { shots: 48, storyboard: 0, keyframe: 12, video: 0 } }))).toBe("12/48 frames");
    expect(stageBadge("make", p({ make: { shots: 48, storyboard: 0, keyframe: 48, video: 3 } }))).toBe("3/48 video");
    expect(stageBadge("export", p())).toBe("");
    expect(stageBadge("export", p({ make: { shots: 48, storyboard: 48, keyframe: 48, video: 3 } }))).toBe("ready");
    expect(stageBadge("story", null)).toBe("");
    expect(stageBadge("cast", p({ cast: { characters: 0, places: 0, pictures: 0, style: false } }))).toBe("");
  });
  it("marks a step done only when it really is", () => {
    expect(stageDone("story", p())).toBe(true);
    expect(stageDone("make", p())).toBe(false);
    expect(stageDone("make", p({ make: { shots: 48, storyboard: 0, keyframe: 48, video: 48 } }))).toBe(true);
    expect(stageDone("cast", p({ cast: { characters: 3, places: 1, pictures: 0, style: false } }))).toBe(false);
    expect(stageDone("export", p())).toBe(false);
  });
  it("knows the step before and after, skipping Shots in Simple mode, and what to do here", () => {
    expect(neighbours("story", false)).toMatchObject({ prev: null, next: "cast" });
    expect(neighbours("cast", false).next).toBe("make");
    expect(neighbours("cast", true).next).toBe("shots");
    expect(neighbours("make", true)).toMatchObject({ prev: "shots", next: "export" });
    expect(neighbours("export", true)).toMatchObject({ next: null, prev: "make" });
    expect(neighbours("story", true).hint).toMatch(/Lock the story/);
    expect(neighbours("nope", true)).toEqual({ prev: null, next: null, hint: "" });
    expect(stageLabel("make")).toBe("Studio");
  });
});

