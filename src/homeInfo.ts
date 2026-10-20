/** What the Home screen says about when a film was last worked on, as a person says it. Pure, so the wording can be tested. */

/** "Today", "Yesterday", "3 days ago", then the date. `now` is a parameter so it can be tested. */
export function relativeDay(modifiedSeconds: number, now: Date = new Date()): string {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const then = new Date(modifiedSeconds * 1000);
  const n = Math.round((day(now) - day(then)) / 86_400_000);
  if (n <= 0) return "Today";
  if (n === 1) return "Yesterday";
  if (n < 7) return `${n} days ago`;
  return then.toLocaleDateString();
}

/** The film to offer under "Continue where you left off": the most recently changed one. */
export function lastFilm<T extends { kind?: string; modified: number }>(projects: T[]): T | null {
  const films = projects.filter((p) => p.kind === "film");
  return films.length ? films.reduce((a, b) => (b.modified > a.modified ? b : a)) : null;
}
