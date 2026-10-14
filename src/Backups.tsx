import { useEffect, useState } from "react";
import { api, errorText } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

type Backup = { name: string; at: number; reason: string; files: string[] };
const REASON: Record<string, string> = { auto: "Automatic", saved: "Saved", "before restore": "Before a restore" };

/** Go back to an earlier state of the project. Only the decisions are restored (plan, choices, approvals, library);
 *  media is never deleted, and the current state is snapshotted first so a restore can be undone. */
export function BackupsSheet({ dir, filmDir = null, onClose, onRestored }: { dir: string | null; filmDir?: string | null; onClose: () => void; onRestored: () => void }) {
  const [list, setList] = useState<Backup[] | null>(null);
  const [records, setRecords] = useState<{ name: string; at: number; reason: string; files: number; damaged?: boolean }[] | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { if (dir) api.backups<{ backups: Backup[] }>(dir, "backups").then((r) => setList(r.backups)).catch((e) => setErr(errorText(e))); }, [dir]);
  useEffect(() => { if (filmDir) api.filmBackup<{ backups: NonNullable<typeof records> }>(filmDir, "list").then((r) => setRecords(r.backups)).catch((e) => setErr(errorText(e))); }, [filmDir]);
  const restoreRecords = async (b: { name: string; at: number }) => {
    if (!filmDir || !await ask(`Put the film's records back to how they were on ${new Date(b.at * 1000).toLocaleString()}? (script versions, cast, voices and notes.) The records as they are now are backed up first, so you can undo this. Pictures, video and audio are never touched, and the record of what voice generation has used is kept as it is.`)) return;
    setBusy(b.name); setErr("");
    try { await api.filmBackup(filmDir, "restore", b.name); onRestored(); } catch (e) { setErr(errorText(e)); setBusy(""); }
  };
  const restore = async (b: Backup) => {
    if (!await ask(`Go back to ${new Date(b.at * 1000).toLocaleString()}? The project as it is now is backed up first, so you can undo this.`)) return;
    setBusy(b.name); setErr("");
    try { if (dir) await api.backups(dir, "restore", b.name); onRestored(); } catch (e) { setErr(errorText(e)); setBusy(""); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass" role="dialog" aria-label="Restore from backup" onClick={(e) => e.stopPropagation()} style={{ width: "min(560px, calc(100vw - 48px))" }}>
        <div className="vs-head"><h2>Restore from backup</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">FilmCrafter keeps the last 20 versions of this timeline's decisions: when you open it, every 10 minutes if something changed,
          and each time you save. Your renders and media are never touched.</p>
        {filmDir && <>
          <h3 className="bk-h">The film's records</h3>
          <p className="dim">Script versions, cast, voices and notes. Made when the film opens and whenever they change.</p>
          {records === null && !err && <p className="dim"><span className="spin sm" /> Loading…</p>}
          {records?.length === 0 && <p className="dim">No backups of the film's records yet.</p>}
          <ul className="bk-list">
            {records?.map((b) => (
              <li key={b.name}>
                <span><b>{b.damaged ? "Damaged backup" : new Date(b.at * 1000).toLocaleString()}</b> <span className="dim">· {b.damaged ? "can't be used" : `${REASON[b.reason] ?? (b.reason === "open" ? "When opened" : b.reason)} · ${b.files} files`}</span></span>
                <button className="btn ghost sm" disabled={!!busy || b.damaged} onClick={() => restoreRecords(b)}>{busy === b.name ? "Restoring…" : "Restore"}</button>
              </li>))}
          </ul>
        </>}
        {dir && filmDir && <h3 className="bk-h">The timeline</h3>}
        {dir && list === null && !err && <p className="dim"><span className="spin sm" /> Loading…</p>}
        {list?.length === 0 && <p className="dim">No backups yet. One is made when the project opens and whenever it changes.</p>}
        <ul className="bk-list">
          {list?.map((b) => (
            <li key={b.name}>
              <span><b>{new Date(b.at * 1000).toLocaleString()}</b> <span className="dim">· {REASON[b.reason] ?? b.reason}</span></span>
              <button className="btn ghost sm" disabled={!!busy} onClick={() => restore(b)}>{busy === b.name ? "Restoring…" : "Restore"}</button>
            </li>))}
        </ul>
        {err && <div className="error-text" role="alert">{err}</div>}
      </div>
    </div>
  );
}
