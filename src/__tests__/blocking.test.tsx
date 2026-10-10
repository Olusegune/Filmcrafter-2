import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve(null)), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { ROOM, along, bearing, clampRoom, coneEdges, initials, lineThrough, norm360, sideOf, toRoom } from "../blockingMath";
import { BlockingPlan } from "../BlockingPlan";
import type { BlockingPlanData } from "../api";

describe("the floor plan arithmetic", () => {
  it("keeps points inside the room", () => {
    expect(clampRoom({ x: -10, y: 500 })).toEqual({ x: 1.5, y: ROOM.h - 1.5 });
    expect(clampRoom({ x: 50, y: 30 })).toEqual({ x: 50, y: 30 });
  });

  it("uses compass angles: 0 right, 90 down the page, 180 left, 270 up", () => {
    expect(bearing({ x: 0, y: 0 }, { x: 10, y: 0 })).toBeCloseTo(0);
    expect(bearing({ x: 0, y: 0 }, { x: 0, y: 10 })).toBeCloseTo(90);
    expect(bearing({ x: 0, y: 0 }, { x: -10, y: 0 })).toBeCloseTo(180);
    expect(bearing({ x: 0, y: 0 }, { x: 0, y: -10 })).toBeCloseTo(270);
    expect(norm360(-90)).toBe(270);
    expect(norm360(725)).toBe(5);
    const p = along({ x: 10, y: 10 }, 90, 5);
    expect(p.x).toBeCloseTo(10);
    expect(p.y).toBeCloseTo(15);
  });

  it("draws a cone from the camera that opens by the lens's angle", () => {
    const [a, b] = coneEdges({ x: 50, y: 60 }, 270, 60, 40);
    expect(bearing({ x: 50, y: 60 }, a)).toBeCloseTo(240);
    expect(bearing({ x: 50, y: 60 }, b)).toBeCloseTo(300);
  });

  it("runs the line of action from wall to wall, and not for one point", () => {
    const l = lineThrough({ x: 30, y: 35 }, { x: 70, y: 35 })!;
    expect(l[0]).toEqual({ x: 0, y: 35 });
    expect(l[1]).toEqual({ x: ROOM.w, y: 35 });
    const d = lineThrough({ x: 10, y: 10 }, { x: 20, y: 20 })!;
    expect(d[0].x).toBeCloseTo(0);
    expect(d[1].y).toBeCloseTo(ROOM.h);
    expect(lineThrough({ x: 5, y: 5 }, { x: 5, y: 5 })).toBeNull();
  });

  it("tells which side of the line the camera is on, the same way the engine does", () => {
    const a = { x: 30, y: 36 }, b = { x: 70, y: 36 };
    expect(sideOf({ x: 50, y: 62 }, a, b)).toBe(1);
    expect(sideOf({ x: 50, y: 8 }, a, b)).toBe(-1);
    expect(sideOf({ x: 50, y: 36 }, a, b)).toBe(0);
  });

  it("turns a pointer position into a point in the room", () => {
    const box = { left: 100, top: 50, width: 500, height: 350 };
    expect(toRoom(350, 225, box)).toEqual({ x: 50, y: 35 });
    expect(toRoom(-999, 9999, box)).toEqual({ x: 0, y: ROOM.h });
  });

  it("makes initials for the dots", () => {
    expect(initials("Sarah")).toBe("S");
    expect(initials("Teacher Wen")).toBe("TW");
    expect(initials("  ")).toBe("?");
  });
});

const plan: BlockingPlanData = { people: [{ name: "Sarah", x: 30, y: 36, facing: 0 }, { name: "John", x: 70, y: 36, facing: 180 }], props: [{ name: "Tea", x: 20, y: 20 }], camera: { x: 50, y: 64, aim: 270, fov: 65 } };

describe("the blocking plan screen", () => {
  const html = (p: BlockingPlanData | null, locked = false) => renderToStaticMarkup(<BlockingPlan dir="f" shot="S01-02" locked={locked} plan={p} onSaved={async () => {}} />);

  it("draws each person, the prop, the camera, its cone and the dashed line between the first two people", () => {
    const h = html(plan);
    expect(h).toContain("Top-down blocking plan");
    expect(h).toContain(">Sarah<");
    expect(h).toContain(">John<");
    expect(h).toContain(">Tea<");
    expect(h).toContain("bp-cone");
    expect(h).toContain("bp-line");
    expect(h).toContain("Lens width of view: 65");
  });

  it("invites a suggestion when there is no plan, and offers no lens or line", () => {
    const h = html(null);
    expect(h).toContain("No plan yet");
    expect(h).toContain("Suggest a layout");
    expect(h).not.toContain("bp-cone");
    expect(h).not.toContain("bp-line");
  });

  it("is fixed while the storyboard is locked", () => {
    const h = html(plan, true);
    expect(h).toContain("storyboard is locked");
    expect(h).toContain('disabled=""');
  });
});
