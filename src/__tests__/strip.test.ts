import { describe, expect, it } from "vitest";
import { clock, durationFromDrag, insertIndex, layout, MAX_SECONDS, MIN_BLOCK_PX, MIN_SECONDS } from "../stripMath";

describe("the film strip", () => {
  it("lays shots out in proportion to their length, never narrower than a block can be read", () => {
    const { blocks, scale, total } = layout([4, 4, 1], ["a", "b", "c"], 900);
    expect(total).toBe(9);
    expect(scale).toBe(100);
    expect(blocks[0].width).toBe(400);
    expect(blocks[2].width).toBe(100);
    expect(blocks[1].left).toBe(402);
    const tiny = layout([30, 1], ["a", "b"], 400);
    expect(tiny.blocks[1].width).toBe(MIN_BLOCK_PX);
  });
  it("copes with nothing", () => {
    expect(layout([], [], 900).blocks).toEqual([]);
    expect(layout([2], ["a"], 0).blocks).toEqual([]);
    expect(layout([0, 0], ["a", "b"], 500).blocks).toEqual([]);
  });
  it("turns a drag on the right edge into a length in tenths of a second, kept between the shortest and longest", () => {
    expect(durationFromDrag(4, 100, 100)).toBe(5);
    expect(durationFromDrag(4, -50, 100)).toBe(3.5);
    expect(durationFromDrag(4, 37, 100)).toBe(4.4);
    expect(durationFromDrag(4, -9999, 100)).toBe(MIN_SECONDS);
    expect(durationFromDrag(4, 99999, 100)).toBe(MAX_SECONDS);
    expect(durationFromDrag(4, NaN, 100)).toBe(4);
    expect(durationFromDrag(4, 10, 0)).toBe(4);
  });
  it("finds the place a dragged block would take", () => {
    const { blocks } = layout([4, 4, 4], ["a", "b", "c"], 1200);
    expect(insertIndex(blocks, "a", -50)).toBe(0);
    expect(insertIndex(blocks, "a", blocks[1].left + blocks[1].width / 2 + 5)).toBe(1);
    expect(insertIndex(blocks, "a", 99999)).toBe(2);
    expect(insertIndex(blocks, "c", 0)).toBe(0);
  });
  it("writes a clock for the ruler", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(65)).toBe("1:05");
    expect(clock(7.9)).toBe("0:07");
  });
});
