/** Whether any finished video take of a shot was made in a different look than the one the shot has now. Reading only: it never starts a render. */
export const styleChangedSince = (jobs: { state: string; kind?: string; look?: string | null }[], lookId: string): boolean =>
  jobs.some((j) => j.state === "ready" && j.kind !== "image" && !!j.look && j.look !== lookId);

/** What to save when a look is picked for a shot: choosing the look it already inherits is not an own look, so it clears instead ("" clears). */
export const shotLookToSave = (picked: string, inherited: string): string => (picked === inherited ? "" : picked);

/** The look a shot is played in: its own, else its scene's, else the film's (the same order the engine uses, `resolve_look`). */
export const effectiveLook = (own: { shots?: Record<string, string>; scenes?: { scene: number; style: string | null }[] } | null, shotId: string, scene: number | undefined, filmLook: string): string =>
  own?.shots?.[shotId] || own?.scenes?.find((x) => x.scene === scene)?.style || filmLook;
