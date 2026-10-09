import { describe, expect, it } from "vitest";
import { laneAt, packLanes, restack, timeAtX } from "../laneMath";

const A = { id: "a", start: 0, end: 4 }, B = { id: "b", start: 2, end: 6 }, C = { id: "c", start: 8, end: 10 };
const spans = [A, B, C];

describe("lane = stacking order", () => {
  it("puts the layer in front in the top lane and what it overlaps below it", () => {
    expect(packLanes(spans, ["a", "b", "c"])).toEqual({ b: 0, a: 1, c: 0 });
    expect(packLanes(spans, ["b", "a", "c"])).toEqual({ a: 0, b: 1, c: 0 });
  });
  it("lets layers that never overlap share a lane", () => {
    const l = packLanes(spans, ["a", "b", "c"]);
    expect(l.c).toBe(l.b);
  });
  it("is stable for the same input", () => {
    expect(packLanes(spans, ["a", "b", "c"])).toEqual(packLanes(spans, ["a", "b", "c"]));
  });
});

describe("moving a layer to another lane", () => {
  const order = ["a", "b", "c"];
  const lanes = packLanes(spans, order);   // b 0, a 1, c 0
  it("brings the layer in front of what it crosses when it goes up", () => {
    expect(restack(order, spans, lanes, "a", 0)).toBe(1);        // b is the front-most overlap: a goes in after it (once a is taken out, b is at 0)
  });
  it("sends it behind what it crosses when it goes down", () => {
    expect(restack(order, spans, lanes, "b", 1)).toBe(0);
  });
  it("does nothing when nothing overlapping is crossed, or the lane is the same or odd", () => {
    expect(restack(order, spans, lanes, "c", 1)).toBeNull();
    expect(restack(order, spans, lanes, "a", 1)).toBeNull();
    expect(restack(order, spans, lanes, "a", -1)).toBeNull();
    expect(restack(order, spans, lanes, "a", NaN)).toBeNull();
    expect(restack(order, spans, lanes, "zzz", 0)).toBeNull();
  });
});

describe("positions on the lane row", () => {
  it("finds the lane under a height, kept inside the lanes that exist", () => {
    expect(laneAt(0, 22, 3)).toBe(0);
    expect(laneAt(30, 22, 3)).toBe(1);
    expect(laneAt(500, 22, 3)).toBe(2);
    expect(laneAt(-40, 22, 3)).toBe(0);
    expect(laneAt(10, 22, 0)).toBe(0);
  });
  it("finds the time under a position, inside the song, to a tenth", () => {
    expect(timeAtX(100, 50, 60)).toBe(2);
    expect(timeAtX(-5, 50, 60)).toBe(0);
    expect(timeAtX(99999, 50, 60)).toBe(59.5);
    expect(timeAtX(33, 50, 60)).toBe(0.7);
  });
});
