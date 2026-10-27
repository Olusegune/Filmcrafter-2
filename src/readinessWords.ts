import type { ReadinessGo, ReadinessItem } from "./api";

/** What the button says, by where it goes. */
export const goLabel = (go: ReadinessGo): string => ({
  story: "Open the story", cast: "Open Cast & World", shots: "Open the shots", voice: "Open the voices", soundplan: "Open the Sound plan", make: "Open Make", export: "Open Export",
} as Record<ReadinessGo, string>)[go] ?? "Take me there";

export const levelWords = (l: ReadinessItem["level"]): string => ({ fix: "Fix", look: "Look", note: "Note" } as Record<string, string>)[l] ?? l;

/** The bar's sentence: the one next thing, or that the film is ready. */
export const nextSentence = (n: ReadinessItem | null, ready: boolean): string =>
  ready ? "Everything is in place. The film is ready to export." : n ? n.what : "Nothing to do yet.";

/** "All 3 things" for the button beside it; nothing when there is only the next step itself. */
export const moreWords = (total: number): string => (total <= 1 ? "" : `All ${total} things`);
