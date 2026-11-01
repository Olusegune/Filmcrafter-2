/** Whether the first-launch question ("What would you like to create?") has been answered. Kept in this browser only, and everything works without it: if storage cannot be read, the question is not asked. */
const KEY = "pf-home-welcome";
export const welcomeSeen = (): boolean => { try { return localStorage.getItem(KEY) === "1"; } catch { return true; } };
export const markWelcomeSeen = (): void => { try { localStorage.setItem(KEY, "1"); } catch { /* optional */ } };

/** The first-launch question is asked once, to someone with no films yet who has not answered it. A person with films, or who has answered, is never asked again (they can ask for it from Home). */
export const shouldWelcome = (filmCount: number, loaded: boolean, seen: boolean): boolean => loaded && filmCount === 0 && !seen;
