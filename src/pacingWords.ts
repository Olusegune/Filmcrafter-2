/** The words and sizes the Pacing screen uses. Pure, so they can be tested. */
export const levelWords = (level: string): string => (level === "fix" ? "Fix" : level === "look" ? "Look" : "Note");

/** The height of a shot's bar in the rhythm chart, as a share of the tallest: proportional to its length, never so short that it cannot be clicked. */
export const rhythmHeight = (seconds: number, longest: number): number => Math.max(8, Math.round((seconds / Math.max(longest, 0.1)) * 100));
