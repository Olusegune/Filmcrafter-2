/** The arithmetic of the film strip: shots as blocks along a time ruler, a drag on a block's right edge changing its length, a drag of the block changing its place. No screen code. */
export const MIN_SECONDS = 1;
export const MAX_SECONDS = 30;
export const MIN_BLOCK_PX = 76;

export type Block = { id: string; left: number; width: number; seconds: number };

/** Where each block sits for this width: lengths in proportion to seconds, but never narrower than a block can be read. */
export function layout(seconds: number[], ids: string[], widthPx: number): { blocks: Block[]; scale: number; total: number } {
  const total = seconds.reduce((a, b) => a + b, 0);
  if (!(total > 0) || !(widthPx > 0)) return { blocks: [], scale: 0, total: 0 };
  const scale = widthPx / total;
  let left = 0;
  const blocks = ids.map((id, i) => {
    const width = Math.max(MIN_BLOCK_PX, seconds[i] * scale);
    const b = { id, left, width, seconds: seconds[i] };
    left += width + 2;
    return b;
  });
  return { blocks, scale, total };
}

/** The length a shot gets when its right edge is dragged `dx` pixels: in tenths of a second, between the shortest and longest a shot can be. */
export function durationFromDrag(start: number, dx: number, scale: number): number {
  if (!(scale > 0) || !Number.isFinite(dx)) return start;
  const v = start + dx / scale;
  return Math.round(Math.max(MIN_SECONDS, Math.min(MAX_SECONDS, v)) * 10) / 10;
}

/** The place a dragged block would take: the index it should end up at, from where its middle is now. */
export function insertIndex(blocks: Block[], movingId: string, x: number): number {
  const rest = blocks.filter((b) => b.id !== movingId);
  let at = 0;
  for (const b of rest) { if (x > b.left + b.width / 2) at += 1; }
  return at;
}

/** A clock for the ruler: 0:07 or 1:05. */
export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
