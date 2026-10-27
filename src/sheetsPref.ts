import { useCallback, useEffect, useState } from "react";

/**
 * Whether the picture thumbnails of the references (the character sheets and the rest) are shown in the shot panels. They take a lot of room, so a person can hide them; the choice is
 * remembered on this computer and every panel that lists them follows it at once. Hiding them changes nothing about what the model is given: it only changes what is drawn.
 */
const KEY = "pf-hide-sheets";
const EVENT = "pf-sheets-pref";

export const readHidden = (): boolean => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };

export function useSheetsShown(): [boolean, () => void] {
  const [shown, setShown] = useState(() => !readHidden());
  useEffect(() => {
    const on = () => setShown(!readHidden());
    window.addEventListener(EVENT, on);
    window.addEventListener("storage", on);
    return () => { window.removeEventListener(EVENT, on); window.removeEventListener("storage", on); };
  }, []);
  const toggle = useCallback(() => {
    try { localStorage.setItem(KEY, readHidden() ? "0" : "1"); } catch { /* a convenience only */ }
    window.dispatchEvent(new Event(EVENT));
    setShown(!readHidden());
  }, []);
  return [shown, toggle];
}
