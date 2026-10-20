import { describe, expect, it } from "vitest";
import { lastFilm, relativeDay } from "../homeInfo";

const now = new Date(2026, 9, 20, 15, 0, 0);
const at = (y: number, m: number, d: number, h = 9) => new Date(y, m, d, h).getTime() / 1000;

describe("when a film was last worked on", () => {
  it("says today, yesterday and days ago, by calendar day", () => {
    expect(relativeDay(at(2026, 9, 20, 1), now)).toBe("Today");
    expect(relativeDay(at(2026, 9, 19, 23), now)).toBe("Yesterday");
    expect(relativeDay(at(2026, 9, 17), now)).toBe("3 days ago");
    expect(relativeDay(at(2026, 8, 1), now)).toBe(new Date(2026, 8, 1, 9).toLocaleDateString());
  });
  it("offers the newest film, not a show or an older one", () => {
    const list = [{ kind: "film", modified: 5, t: "a" }, { kind: "show", modified: 99, t: "s" }, { kind: "film", modified: 9, t: "b" }];
    expect(lastFilm(list)?.t).toBe("b");
    expect(lastFilm([{ kind: "show", modified: 1 }])).toBeNull();
    expect(lastFilm([])).toBeNull();
  });
});
