import { useCallback, useEffect, useState } from "react";
import { api, errorText, type ContinuityFinding, type ContinuityView } from "./api";

const WORD = { note: "Note", look: "Worth a look", likely: "Likely to show" } as const;

/**
 * The Continuity Director: where something may have changed between shots. Advice only: every finding says "may" and why. Set one aside when the change is meant;
 * nothing is blocked and nothing in the film is changed unless you press the button that applies a suggestion.
 */
export function FilmContinuity({ dir, onGo, onChanged }: { dir: string; onGo: (shot: string) => void; onChanged: () => void }) {
  const [v, setV] = useState<ContinuityView | null>(null);
  const [all, setAll] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.filmCheck("check", dir).then(setV).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { void load(); }, [load]);
  const run = async (fn: () => Promise<ContinuityView>, changed = false) => { setErr(""); try { setV(await fn()); if (changed) onChanged(); } catch (e) { setErr(errorText(e)); } };
  if (!v) return <div className="film-load dim">{err || "Checking the shots…"}</div>;
  const open = v.findings.filter((f) => f.status === "open");
  const aside = v.findings.filter((f) => f.status !== "open");
  const row = (f: ContinuityFinding) => (
    <li key={f.id} className={`ck-${f.severity}`}>
      <span className="topic">{WORD[f.severity]} · {f.shot}</span>
      <p>{f.text}</p>
      {f.suggestion && <p className="dim">{f.suggestion}</p>}
      <div className="row">
        <button className="link" onClick={() => onGo(f.shot)}>Go to {f.shot}</button>
        {f.apply && f.status === "open" && <button className="link" onClick={() => run(() => api.filmCheck("apply", dir, { id: f.id }), true)}>Use that</button>}
        {f.status === "open" ? <>
          <button className="link" onClick={() => run(() => api.filmCheck("decide", dir, { id: f.id, state: "noted" }))}>I'll fix it</button>
          <button className="link" onClick={() => run(() => api.filmCheck("decide", dir, { id: f.id, state: "dismissed" }))}>It's meant</button></>
          : <button className="link" onClick={() => run(() => api.filmCheck("decide", dir, { id: f.id, state: "open" }))}>Bring back</button>}
      </div>
    </li>);
  return (
    <div className="ck">
      <h2>Continuity <span className="dim">{open.length ? `${open.length} to look at` : "nothing to look at"}</span></h2>
      <p className="dim">Where something may have changed from one shot to the next. These are suggestions: you decide.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {open.length === 0 && <p className="cw-note">Nothing stands out. Check again after you change the shots.</p>}
      <ul>{open.map(row)}</ul>
      {aside.length > 0 && <><button className="link" onClick={() => setAll((x) => !x)}>{all ? "Hide" : "Show"} {aside.length} set aside</button>{all && <ul>{aside.map(row)}</ul>}</>}
      <button className="btn ghost sm" onClick={() => void load()}>Check again</button>
    </div>
  );
}
