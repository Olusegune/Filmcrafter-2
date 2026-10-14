import { useCallback, useEffect, useState } from "react";
import { api, type ModelWarnings, type OutdatedReport } from "./api";
import { VOICE_EVENT } from "./voiceHooks";
import { CUE_EVENT } from "./CueLanes";

/**
 * What may be out of date because a voice or the planned sound changed after it was made: video takes made to follow an earlier recording, planned sounds whose sound or shot changed, and a finished
 * film exported before the sound changed. Nothing here changes anything: each line says what to look at and what the options are (every one shows its price first). Shows nothing when all is current.
 */
export function OutdatedPanel({ dir }: { dir: string }) {
  const [r, setR] = useState<OutdatedReport | null>(null);
  const [m, setM] = useState<ModelWarnings | null>(null);
  const load = useCallback(() => { api.filmOutdated(dir).then(setR).catch(() => setR(null)); api.registry<ModelWarnings>("in_use", dir).then(setM).catch(() => setM(null)); }, [dir]);
  useEffect(() => { load(); window.addEventListener(VOICE_EVENT, load); window.addEventListener(CUE_EVENT, load); return () => { window.removeEventListener(VOICE_EVENT, load); window.removeEventListener(CUE_EVENT, load); }; }, [load]);
  const models = m?.warnings ?? [];
  if (!r || (r.clean && !models.length)) return null;
  return (
    <section className="od" aria-label="May be out of date" role="status">
      <h3>May be out of date <span className="dim">nothing was changed</span></h3>
      {r.takes.length > 0 && <>
        <p className="dim">These video takes were made to follow a voice that is not the one on the shot now. Open the shot in the Studio: <b>Lip-sync this take…</b> re-times the mouth to the new voice, or make a new take. Both show their price first, and an approved take is never replaced by itself.</p>
        <ul>{r.takes.map((t) => <li key={t.shot}><b>{t.shot}</b> {t.speakers.join(", ")}: {t.why}{t.kept ? <span className="dim"> {t.note}</span> : null}</li>)}</ul></>}
      {r.cues.length > 0 && <><p className="dim">Planned sounds to look at again (Sound & Music, Scene sound):</p>
        <ul>{r.cues.map((c) => <li key={c.id}><b>{c.name}</b>{c.shot ? ` (${c.shot})` : ` (scene ${c.scene})`}: {c.why}</li>)}</ul></>}
      {r.film && <p>{r.film.why}</p>}
      {models.length > 0 && <><p className="dim">Models behind this film that their provider no longer lists, or that FilmCrafter has no record of. Nothing was replaced, and nothing will be swapped for approved work:</p>
        <ul>{models.map((w) => <li key={`${w.provider}/${w.model}`}><b>{w.name}</b> ({w.provider}): {w.why} <span className="dim">Used for {w.used_for.slice(0, 2).join(", ")}{w.used_for.length > 2 ? "…" : ""}.</span></li>)}</ul></>}
    </section>
  );
}
