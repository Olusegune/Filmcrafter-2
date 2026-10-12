import { useCallback, useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type VoiceImport, type VoiceMatch, type VoiceShot, type VoiceStatus } from "./api";
import * as I from "./icons";

const AUDIO = ["wav", "mp3", "m4a", "flac", "aac", "ogg"];
const FILTERS = [{ name: "Recordings", extensions: AUDIO }];

/** What a row of the match table will do, in words. */
export const MATCH_WORDS: Record<VoiceMatch["status"], string> = {
  ok: "Ready", replace: "Replaces the recording now there", ambiguous: "Who is this?", no_shot: "Which shot?", no_speaker: "Who is speaking?",
  not_in_shot: "Not in this shot", duplicate: "Already in this batch", bad_file: "Can't use this file",
};
/** A row the person can confirm as it stands. */
export const usable = (r: VoiceMatch) => (r.status === "ok" || r.status === "replace") && !!r.shot && !!r.speaker;

/** The people a recording can be for in a shot: those who speak, then those who are only there. */
export const peopleOf = (s: VoiceShot | undefined): string[] => (s ? [...(s.people ?? []).map((p) => p.name), ...(s.others ?? [])] : []);

export const summary = (st: VoiceStatus) => st.people === 0 ? "Nobody speaks in this film yet." : st.missing === 0 ? `Every voice is recorded (${st.recorded}).` : `${st.recorded} of ${st.people} voices recorded; ${st.missing} still to attach.`;

/**
 * Your own recorded voices. Name each file for the person and the shot (CHLOE_S01-04.wav); add them all at once, check the matches, confirm. The video model then makes the
 * mouth follow your recording, and the finished film plays your recording. Shows every shot, or only `only`.
 */
export function VoiceoverPanel({ dir, only, onChanged }: { dir: string; only?: string; onChanged?: () => void }) {
  const [st, setSt] = useState<VoiceStatus | null>(null);
  const [rows, setRows] = useState<VoiceMatch[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState<VoiceImport | null>(null);
  const load = useCallback(() => api.voice("status", dir).then(setSt).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { void load(); }, [load]);
  const shots = useMemo(() => (st?.shots ?? []).filter((s) => !only || s.id === only), [st, only]);
  const byId = useMemo(() => Object.fromEntries((st?.shots ?? []).map((s) => [s.id, s])), [st]);

  const pick = async (): Promise<string[]> => {
    const r = await open({ multiple: true, filters: FILTERS });
    return r == null ? [] : Array.isArray(r) ? r : [r];
  };
  const add = async () => {
    setErr(""); setDone(null);
    try { const files = await pick(); if (files.length) setRows((await api.voice<{ rows: VoiceMatch[] }>("match", dir, { files })).rows); } catch (e) { setErr(errorText(e)); }
  };
  const importRows = async (items: { file: string; shot: string; speaker: string }[]) => {
    setBusy(true); setErr("");
    try { const r = await api.voice<VoiceImport>("import", dir, { items }); setDone(r); setSt(r.status); setRows(null); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const attachOne = async (shot: string, speaker: string) => {
    setErr(""); setDone(null);
    try { const r = await open({ multiple: false, filters: FILTERS }); const f = Array.isArray(r) ? r[0] : r; if (f) await importRows([{ file: f, shot, speaker }]); } catch (e) { setErr(errorText(e)); }
  };
  const remove = async (shot: string, speaker: string) => {
    setBusy(true); setErr(""); setDone(null);
    try { setSt(await api.voice("remove", dir, { shot, speaker })); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const setRow = (i: number, patch: Partial<VoiceMatch>) => setRows((cur) => cur && cur.map((r, j) => {
    if (j !== i) return r;
    const n = { ...r, ...patch };
    const s = n.shot ? byId[n.shot] : undefined;
    if (patch.shot !== undefined && n.speaker && !peopleOf(s).includes(n.speaker)) n.speaker = null;          // the person must be one of this shot's
    n.status = !n.shot ? "no_shot" : !n.speaker ? "no_speaker" : n.status === "bad_file" ? "bad_file" : "ok";
    n.note = n.status === "ok" ? "" : n.note;
    return n;
  }));

  if (!st) return <p className="dim" aria-live="polite">{err || "Loading the voices…"}</p>;
  const ready = rows?.filter(usable) ?? [];
  return (
    <section className="vo" aria-label="Voiceover">
      <div className="vo-head">
        <p className="vo-sum" aria-live="polite">{summary(st)}</p>
        <button className="btn primary sm" disabled={busy} onClick={add}><I.Upload size={14} /> Add recordings…</button>
      </div>
      <p className="dim vo-how">Name each file for the person and the shot, like <b className="num">CHLOE_S01-04.wav</b>. Your recording is what the mouth follows, and what the finished film plays. Your files are copied in, never changed.</p>
      {err && <p className="error-text" role="alert">{err}</p>}

      {rows && <div className="vo-match">
        <h3>Check the matches</h3>
        <table><thead><tr><th>File</th><th>Shot</th><th>Person</th><th>Length</th><th></th></tr></thead><tbody>
          {rows.map((r, i) => {
            const s = r.shot ? byId[r.shot] : undefined;
            return (
              <tr key={r.file + i} className={`vo-r ${usable(r) ? "ok" : "no"}`}>
                <td className="vo-file" title={r.file}>{r.name}</td>
                <td>{r.status === "bad_file" ? "—" : <select aria-label={`Shot for ${r.name}`} value={r.shot ?? ""} onChange={(e) => setRow(i, { shot: e.target.value || null })}>
                  <option value="">Choose…</option>{(st.shots).map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</select>}</td>
                <td>{r.status === "bad_file" ? "—" : <select aria-label={`Person for ${r.name}`} value={r.speaker ?? ""} disabled={!r.shot} onChange={(e) => setRow(i, { speaker: e.target.value || null })}>
                  <option value="">Choose…</option>{peopleOf(s).map((n) => <option key={n} value={n}>{n}</option>)}</select>}</td>
                <td className="num">{r.seconds != null ? `${r.seconds.toFixed(1)}s` : ""}</td>
                <td className="vo-state"><b>{MATCH_WORDS[r.status]}</b>{r.note && <span className="dim"> {r.note}</span>}</td>
              </tr>);
          })}
        </tbody></table>
        <div className="film-actions">
          <button className="btn primary" disabled={busy || !ready.length} onClick={() => importRows(ready.map((r) => ({ file: r.file, shot: r.shot!, speaker: r.speaker! })))}>
            {busy ? "Attaching…" : `Attach ${ready.length} recording${ready.length === 1 ? "" : "s"}`}</button>
          <button className="btn ghost" disabled={busy} onClick={() => setRows(null)}>Cancel</button>
          <span className="dim">Nothing is attached until you press the button. A shot shorter than its recording is lengthened to hold it.</span>
        </div>
      </div>}

      {done && <div className="vo-done" role="status">
        <b>{done.attached.length} attached.</b>{done.attached.filter((a) => a.lengthened_to).map((a) => <span key={a.shot + a.speaker}> {a.shot} is now {a.lengthened_to}s.</span>)}
        {done.failed.map((f, i) => <div key={i} className="error-text">{f.file}: {f.why}</div>)}
      </div>}

      {shots.length === 0 && <p className="dim">No shot has anyone speaking yet.</p>}
      {shots.map((s) => (
        <article key={s.id} className="vo-shot">
          <h3><span className="num">{s.id}</span> <span className="dim">Scene {s.scene} · {s.seconds}s</span></h3>
          {(s.notes ?? []).map((n) => <p key={n} className="vo-note"><I.Alert size={12} /> {n}</p>)}
          {(s.people ?? []).map((p) => (
            <div key={p.key} className="vo-person">
              <div className="vo-who"><b>{p.name}</b>{(p.lines ?? []).length > 0 && <q className="vo-line">{(p.lines ?? []).join(" ")}</q>}</div>
              {p.recording
                ? <div className="vo-rec"><audio controls preload="none" src={api.mediaUrl(`${dir}/${p.recording.file}`)} aria-label={`${p.name} in ${s.id}`} />
                    <span className="dim num">{p.recording.seconds.toFixed(1)}s · {p.recording.name}</span>
                    <button className="link" disabled={busy} onClick={() => attachOne(s.id, p.name)}>Replace…</button>
                    <button className="link" disabled={busy} onClick={() => remove(s.id, p.name)}>Remove</button></div>
                : <div className="vo-rec"><span className="vo-none">No recording</span>
                    <button className="btn sm" disabled={busy} onClick={() => attachOne(s.id, p.name)}>Attach…</button></div>}
            </div>))}
          {(s.others ?? []).length > 0 && <p className="dim vo-others">Also in the shot, with nothing to say: {(s.others ?? []).join(", ")}.</p>}
        </article>))}
    </section>
  );
}
