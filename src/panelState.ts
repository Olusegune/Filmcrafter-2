/** A yes-or-no setting remembered between sessions (a panel shown or hidden). Storage can be missing or blocked, so every read and write is guarded and the default applies. */
type Store = Pick<Storage, "getItem" | "setItem">;
const local = (): Store | null => { try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; } };

export function readFlag(key: string, fallback: boolean, store: Store | null = local()): boolean {
  try {
    const v = store?.getItem(key);
    return v === "1" ? true : v === "0" ? false : fallback;
  } catch { return fallback; }
}

export function writeFlag(key: string, value: boolean, store: Store | null = local()): void {
  try { store?.setItem(key, value ? "1" : "0"); } catch { /* remembering is a convenience only */ }
}
