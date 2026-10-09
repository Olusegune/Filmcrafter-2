/** How the Clean up grid is sized and browsed. Pure. */
export type TileSize = "small" | "medium" | "large";
export const TILE_MIN: Record<TileSize, number> = { small: 150, medium: 220, large: 300 };
const KEY = "pf-cleanup-size";
type Store = Pick<Storage, "getItem" | "setItem">;
const local = (): Store | null => { try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; } };

/** The remembered tile size; large unless the person chose otherwise (a missing or blocked store is fine). */
export function readTileSize(store: Store | null = local()): TileSize {
  try { const v = store?.getItem(KEY); return v === "small" || v === "medium" || v === "large" ? v : "large"; } catch { return "large"; }
}
export function writeTileSize(v: TileSize, store: Store | null = local()): void { try { store?.setItem(KEY, v); } catch { /* a convenience only */ } }

/** The next (dir 1) or previous (dir -1) position in a list of `n`, wrapping round; -1 when there is nothing to move to. */
export const stepIndex = (i: number, dir: 1 | -1, n: number): number => (n <= 0 ? -1 : (((i + dir) % n) + n) % n);

/** Bytes as the screen writes them. */
export const sizeText = (b: number): string => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${Math.round(b / 1e6)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
