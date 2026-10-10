/** The small, testable parts of the story screens: what a start is called, how a file is read as a story, how a count is said. No screen code. */
import type { FilmAdvice, FilmScene, StoryKind, StoryPreview } from "./api";

export const STORY_KINDS: { id: StoryKind; label: string; blurb: string }[] = [
  { id: "screenplay", label: "A screenplay", blurb: "A script with scenes and dialogue. It is kept exactly as written." },
  { id: "idea", label: "An idea or logline", blurb: "A spark: a sentence or two about who wants what." },
  { id: "synopsis", label: "A synopsis", blurb: "The story in a paragraph or a page." },
  { id: "treatment", label: "A treatment", blurb: "The story told in prose, scene by scene." },
  { id: "outline", label: "A scene outline", blurb: "A numbered list of the scenes." },
];

export const STORY_EXT = ["txt", "md", "fountain", "text", "pdf", "docx"];
export const isStoryFile = (path: string) => STORY_EXT.includes(String(path).split(".").pop()!.toLowerCase());

/** The film's stages in the order a film is made. Only the first is built so far; the others are shown so the road ahead is visible. */
export const STAGES: { id: string; label: string; ready: boolean }[] = [
  { id: "story", label: "Story", ready: true },
  { id: "cast", label: "Cast & World", ready: true },
  { id: "storyboard", label: "Storyboard", ready: false },
  { id: "make", label: "Make film", ready: false },
  { id: "review", label: "Review", ready: false },
  { id: "export", label: "Export", ready: false },
];

const SLUG = /^\s*(?:\.[A-Za-z0-9]|(?:INT|EXT|EST|INT\.?\/EXT|EXT\.?\/INT|I\/E)[. ])/im;

/** Which kind of story a piece of text most likely is, so the person is not asked twice. Only a guess: they can change it. */
export function guessKind(fileName: string, text: string): StoryKind {
  if (/\.fountain$/i.test(fileName) || SLUG.test(text)) return "screenplay";
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  if (/^\s*(?:\d+[.)]|[-*•])\s+\S/m.test(text) && text.split("\n").filter((l) => /^\s*(?:\d+[.)]|[-*•])\s+\S/.test(l)).length >= 3) return "outline";
  if (words <= 60) return "idea";
  if (words <= 600) return "synopsis";
  return /\.(pdf|docx)$/i.test(fileName) ? "screenplay" : "treatment";
}

export function titleFromFile(name: string): string {
  const base = String(name || "").replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return base ? base.replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 80) : "";
}

export function minutes(seconds: number): string {
  if (!(seconds > 0)) return "";
  if (seconds < 90) return `about ${Math.max(10, Math.round(seconds / 10) * 10)} seconds`;
  const m = seconds / 60;
  return `about ${m < 10 ? m.toFixed(1).replace(/\.0$/, "") : Math.round(m)} minutes`;
}

const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/** The one line under the story box: what was found in it. */
export function previewLine(p: StoryPreview | null): string {
  if (!p) return "";
  if (p.kind === "screenplay") {
    if (!p.scenes) return `${plural(p.words, "word")}`;
    const parts = [plural(p.scenes, "scene"), plural(p.characters, "speaking character"), plural(p.locations, "place")];
    const len = minutes(p.seconds);
    return len ? `${parts.join(" · ")} · ${len}` : parts.join(" · ");
  }
  if (p.kind === "outline") return p.scenes ? `${plural(p.scenes, "scene")} listed` : `${plural(p.words, "word")}`;
  return plural(p.words, "word");
}

/** The development ladder, from a spark to a script, with where this story is on it. */
export const LADDER = ["Logline", "Synopsis", "Treatment", "Beats", "Outline", "Screenplay"];
export function ladderAt(rung: string): number {
  const i = LADDER.findIndex((r) => r.toLowerCase() === rung.toLowerCase());
  return i < 0 ? 0 : i;
}

/** Advice not yet set aside, most useful first: structure, then pacing, then the rest. */
export function openAdvice(a: FilmAdvice[]): FilmAdvice[] {
  const order = ["structure", "pacing", "visual storytelling", "production"];
  return a.filter((x) => x.status === "open").sort((x, y) => (order.indexOf(x.topic) + 1 || 9) - (order.indexOf(y.topic) + 1 || 9));
}

/** Where a scene starts in the text, for scrolling the reader to it. */
export const sceneLine = (s: FilmScene): number => (typeof s.line === "number" ? s.line : 0);

/** A short plain description of where the story stands, for the Home card and the status line. */
export function storyState(s: { kind: StoryKind; locked: number | null; as_is: number | null; current: number }): string {
  if (s.locked !== null) return s.locked === s.current ? `Story locked (version ${s.locked})` : `Version ${s.locked} is locked; version ${s.current} is a draft`;
  if (s.as_is === s.current && s.kind === "screenplay") return "Using the story as it is";
  return s.kind === "screenplay" ? "Screenplay, not locked yet" : `Still a ${s.kind === "idea" ? "logline or idea" : s.kind}`;
}
