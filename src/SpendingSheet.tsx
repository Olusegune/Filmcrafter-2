import { useEffect, useState } from "react";
import { api, errorText, type SpendingSummary } from "./api";
import * as I from "./icons";
import { limitWords, lineWords, opsWords, providerName } from "./spendWords";

/** "What this film has cost": read from FilmCrafter's own records of paid work. It only reads; it can never start, repeat or pay for anything. */
export function SpendingSheet({ dir, onClose }: { dir: string; onClose: () => void }) {
  const [s, setS] = useState<SpendingSummary | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.filmSpending(dir).then(setS).catch((e) => setErr(errorText(e))); }, [dir]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); onClose(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  });                                                                  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass spend" role="dialog" aria-label="What this film has cost" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>What this film has cost</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        {err && <p className="why" role="alert">{err}</p>}
        {!s && !err && <p className="why">Reading the records…</p>}
        {s && <>
          {s.operations === 0 && !s.uncertain.length ? <p className="spend-lead">Nothing has been bought for this film yet. Everything you have done so far was free.</p>
            : <p className="spend-lead">{opsWords(s.operations)} of paid work so far. Each provider counts in its own units, so they are listed apart and never added together.</p>}
          {s.problems.map((p) => <p key={p} className="why spend-warn" role="alert">{p}</p>)}
          {s.lines.length > 0 && <table className="spend-table"><caption className="sr-only">Paid work by step and provider</caption>
            <thead><tr><th scope="col">Step</th><th scope="col">Provider</th><th scope="col">Done</th><th scope="col">Cost</th></tr></thead>
            <tbody>{s.lines.map((l) => <tr key={`${l.step}-${l.provider}-${l.unit}`}><th scope="row">{l.label}</th><td>{providerName(l.provider)}</td><td>{l.operations}</td><td>{lineWords(l)}</td></tr>)}</tbody></table>}
          {s.totals.length > 0 && <div className="spend-totals"><b>Totals, by unit</b>
            <ul>{s.totals.map((t) => <li key={t.unit}>{lineWords({ ...t, reported_operations: t.reported > 0 ? 1 : 0, estimated_operations: t.estimated > 0 ? 1 : 0 })}</li>)}</ul></div>}
          {s.uncertain.length > 0 && <p className="why spend-warn" role="alert"><b>{opsWords(s.uncertain.length)} with an unknown outcome</b> (they may have been charged). They are not counted above. Check the provider's own usage page, then mark each one in the voice usage list.</p>}
          {Object.keys(s.limits).length > 0 && <p className="why">Spending limit{Object.keys(s.limits).length > 1 ? "s" : ""} set for this film: {limitWords(s.limits)}.</p>}
          <p className="why">{s.note}</p>
        </>}
        <div className="cv-actions"><button className="btn" onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}
