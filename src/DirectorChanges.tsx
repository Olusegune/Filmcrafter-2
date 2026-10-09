import { useCallback, useEffect, useState } from "react";
import { api, errorText, type DirectorAudit } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** What the Director changed from your plan: merged beats (with the reasons to look twice, and a way to undo one), dropped beats, gaps. */
export function DirectorChanges({ dir, onChanged, picture }: { dir: string; onChanged: () => void; picture?: (shot: string) => string | null }) {
  const [a, setA] = useState<DirectorAudit | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [all, setAll] = useState(false);
  const load = useCallback(async () => { setA(await api.directorAudit<DirectorAudit>(dir, "audit")); }, [dir]);
  useEffect(() => { load().catch(() => setA(null)); }, [load]);        // no directed plan yet: nothing to show

  if (!a) return null;
  const split = async (shot: string) => {
    if (!await ask(`Split ${shot} back into its separate beats?\n\n${shot} keeps the keyframe or take already made for it (made for the merged action), and the new shot starts without one. `
      + "No other shot is renumbered, and the old plan is kept as a backup.")) return;
    setBusy(shot); setErr(""); setNote("");
    try { const r = await api.directorAudit<{ split: string[]; note: string }>(dir, "split", { shot }); setNote(r.note); await load(); onChanged(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const check = a.merges.filter((m) => m.check).length;
  const shownMerges = all ? a.merges : a.merges.slice(0, 3);
  return (
    <details className="dir-changes" open={check > 0 || a.drops.length > 0 || a.uncovered.length > 0}>
      <summary>
        <b>Director changes</b>{" "}
        <span className="dim">{a.planned} planned → {a.directed} directed · {a.merges.length} merged{check ? ` (${check} to check)` : ""} · {a.drops.length} dropped · {a.uncovered.length} not covered</span>
      </summary>
      {a.ok && <p className="dim"><I.Check size={14} /> The Director kept every beat as its own shot.</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
      {note && <p className="dim" role="status">{note}</p>}
      {a.merges.length > 0 && <p className="dc-lead">The Director joined these beats into one shot each. Look at the picture, and split one back if it should stay separate.</p>}
      <div className="dc-grid">
      {shownMerges.map((m) => {
        const pic = picture?.(m.shot) ?? null;
        return (
        <div key={m.shot} className={`dc-merge ${m.check ? "check" : ""}`}>
          <div className="dc-pic">{pic ? <img src={pic} alt={`${m.shot}`} /> : <span className="dim">No picture yet</span>}</div>
          <div className="dc-body">
            <div className="dc-head"><b>{m.shot}</b> <span className="dim num">{clock(m.start)}–{clock(m.end)} · {m.duration.toFixed(1)}s</span>
              <span className="dc-joined dim">{m.sources.length} beats joined</span></div>
            <ul className="dc-sources">
              {m.sources.map((s) => <li key={s.id}><span className="dim"><b>{s.id}</b> · {s.people.join(", ") || "no one named"}</span> {s.description}</li>)}
            </ul>
            {m.risks.length > 0 && <div className="dc-risks">{m.risks.map((r) => <span key={r} className="dc-risk">{r}</span>)}</div>}
            <div className="dc-foot">
              {m.note && <details className="dc-note"><summary>Why</summary><p className="dim">{m.note}</p></details>}
              <div style={{ flex: 1 }} />
              <button className="btn small ghost" disabled={!!busy} onClick={() => split(m.shot)}>{busy === m.shot ? "Splitting…" : "Split back"}</button></div>
          </div>
        </div>);
      })}
      </div>
      {a.merges.length > 3 && <button className="link" onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${a.merges.length} joined shots`}</button>}
      {a.drops.map((x) => <p key={x.shot} className="si-problems"><span>{x.shot} dropped: {x.beats.join("; ")}</span></p>)}
      {a.uncovered.map((x) => <p key={x.id} className="si-problems"><span>{x.id} is not in any directed shot: {x.description}</span></p>)}
    </details>
  );
}
