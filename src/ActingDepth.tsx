import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "./api";
import { ask } from "./ask";
import * as I from "./icons";
import "./acting.css";

export type Beat = { t0: number; t1: number; what: string; face?: string; eyes?: string; gaze?: string; head?: string; posture?: string; hands?: string; breath?: string;
  change?: string; link?: string; continues?: boolean; source?: "you" | "auto"; confidence?: "low" | "medium" | "high" };
export type BeatsData = { shot: string; seconds: number; beats: Beat[]; source: "you" | "director" | null };
export type AiPrice = { calls: number; usd: number; local: boolean; note: string; shots?: string[]; characters?: string[] };
export type ArcPoint = { section: string; emotion: string; intensity: number; note: string };
export type ArcData = { sections: string[]; characters: string[]; arcs: Record<string, { points: ArcPoint[]; source: string | null }> };
export type Gesture = { when: string; do: string };

/** "free (your local model)" or "about $0.01", the way every AI step here says what it costs before it does anything. */
export const priceText = (e: AiPrice): string => e.local ? "free (your local model)" : `about $${e.usd < 0.01 ? "0.01" : e.usd.toFixed(2)}`;
const confirmText = (what: string, e: AiPrice) => `${what}\n\nPrice: ${priceText(e)}${e.local ? "" : ` (a rough estimate: ${e.note})`}.\nNothing is sent until you press the button below.`;

// ---------------------------------------------------------------- beats

const DETAILS: [keyof Beat, string][] = [["face", "Face"], ["eyes", "Eyes"], ["gaze", "Looks at"], ["head", "Head"], ["posture", "Posture"], ["hands", "Hands"], ["breath", "Breath"], ["change", "What changes"]];

export function BeatsView({ seconds, source, beats, dirty, busy, err, note, onChange, onSave, onClear, onWrite, onSuggest }: {
  seconds: number; source: BeatsData["source"]; beats: Beat[]; dirty: boolean; busy: string; err: string; note?: string;
  onChange: (b: Beat[]) => void; onSave: () => void; onClear: () => void; onWrite: () => void; onSuggest?: () => void;
}) {
  const set = (i: number, patch: Partial<Beat>) => onChange(beats.map((b, k) => (k === i ? { ...b, ...patch } : b)));
  const add = () => { const last = beats[beats.length - 1]; const t0 = last ? Math.min(seconds, last.t1) : 0; onChange([...beats, { t0, t1: Math.min(seconds, t0 + Math.max(0.5, seconds / 3)), what: "" }]); };
  return (
    <section className="panel beats-panel" aria-label="Acting beats">
      <div className="beats-head"><I.Mask size={16} /> <b>Acting beats</b>
        <span className="dim">{source === "director" ? "written by the Director" : source === "you" ? "written by you" : "none yet"} · this shot is {seconds} s</span></div>
      <p className="dim">What the person does, moment by moment. They go into the video prompt as a timed sequence, and the first one into the keyframe.</p>
      {beats.length === 0 && <p className="dim">No beats: the video model decides the timing of the acting on its own.</p>}
      <ol className="beats-list">
        {beats.map((b, i) => (
          <li key={i} className="beat">
            <div className="beat-row">
              <input type="number" className="beat-t" min={0} max={seconds} step={0.1} value={b.t0} aria-label={`Beat ${i + 1} starts at (seconds)`} onChange={(e) => set(i, { t0: Number(e.target.value) })} />
              <span className="dim">to</span>
              <input type="number" className="beat-t" min={0} max={seconds} step={0.1} value={b.t1} aria-label={`Beat ${i + 1} ends at (seconds)`} onChange={(e) => set(i, { t1: Number(e.target.value) })} />
              <span className="dim">s</span>
              <button className="icon-btn" onClick={() => onChange(beats.filter((_, k) => k !== i))} aria-label={`Remove beat ${i + 1}`} title="Remove this beat"><I.Close size={14} /></button>
            </div>
            <input className="text-input beat-what" value={b.what} maxLength={240} placeholder="What she does, for example: lifts her hand slowly to the glasses" aria-label={`Beat ${i + 1}: what happens`} onChange={(e) => set(i, { what: e.target.value })} />
            <details className="beat-more" open={DETAILS.some(([k]) => !!b[k]) || undefined}><summary>Face, eyes, gaze, hands, breath, what changes</summary>
              <div className="beat-details">{DETAILS.map(([k, label]) => (
                <label key={k}>{label}<input className="text-input" value={(b[k] as string) ?? ""} maxLength={k === "change" ? 160 : 120} aria-label={`Beat ${i + 1}: ${label.toLowerCase()}`} onChange={(e) => set(i, { [k]: e.target.value })} /></label>))}</div>
              <label className="beat-carry"><input type="checkbox" checked={!!b.continues} onChange={(e) => set(i, { continues: e.target.checked })} /> Carries on into the next shot <span className="dim">(the feeling does not reset at the cut)</span></label>
              {b.source === "auto" && <p className="dim beat-auto">Suggested automatically{b.confidence ? ` (${b.confidence} confidence)` : ""}: change it freely.</p>}
            </details>
          </li>))}
      </ol>
      <div className="beats-actions">
        {beats.length < 6 && <button className="btn small" onClick={add} disabled={!!busy}>+ Add a beat</button>}
        <button className="btn small primary" onClick={onSave} disabled={!!busy || !dirty || beats.every((b) => !b.what.trim())}>Save beats</button>
        {onSuggest && <button className="btn small" onClick={onSuggest} disabled={!!busy} title="A free starting point made on this computer from the feeling of the shot. Nothing is saved until you press Save beats.">Suggest beats (free)</button>}
        <button className="btn small ghost" onClick={onWrite} disabled={!!busy} title="The Director writes beats for this shot. The price is shown first.">{busy === "write" ? "Writing…" : "Write with the Director…"}</button>
        {(source || beats.length > 0) && <button className="btn small ghost" onClick={onClear} disabled={!!busy}>Clear</button>}
      </div>
      {note && <p className="dim beat-note" role="status">{note}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </section>
  );
}

export function BeatsPanel({ dir, shotId, onChanged }: { dir: string; shotId: string; onChanged?: () => void }) {
  const [data, setData] = useState<BeatsData | null>(null);
  const [draft, setDraft] = useState<Beat[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(() => api.acting<BeatsData>(dir, "beats_get", { shot: shotId }).then((r) => { setData(r); setDraft(r.beats ?? []); setDirty(false); }).catch((e) => setErr(errorText(e))), [dir, shotId]);
  const suggest = async () => {      // free, local; fills the editor and saves nothing
    setErr(""); setNote("");
    try { const r = await api.performanceDirector<{ beats: Beat[]; basis: string }>(dir, "beats_suggest", { shot: shotId }); if (r.beats.length) { setDraft(r.beats); setDirty(true); } setNote(r.basis); } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { setData(null); setErr(""); load(); }, [load]);
  const run = async (what: string, fn: () => Promise<unknown>) => { setBusy(what); setErr(""); try { await fn(); await load(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };
  const write = async () => {
    setErr("");
    try {
      const est = await api.acting<AiPrice>(dir, "beats_estimate", { shots: [shotId], overwrite: true });
      if (!await ask(confirmText(`The Director will write acting beats for ${shotId}.${draft.some((b) => b.what.trim()) ? " Your current beats will be replaced." : ""}`, est), { ok: "Write beats" })) return;
      await run("write", () => api.acting(dir, "beats_write", { shots: [shotId], overwrite: true, confirmed: true }).then((r) => {
        const f = (r as { failed?: Record<string, string> }).failed?.[shotId]; if (f) throw new Error(f); }));
    } catch (e) { setErr(errorText(e)); }
  };
  if (!data) return err ? <p className="error-text" role="alert">{err}</p> : null;
  return <BeatsView seconds={data.seconds} source={data.source} beats={draft} dirty={dirty} busy={busy} err={err} note={note} onSuggest={suggest}
                    onChange={(b) => { setDraft(b); setDirty(true); }}
                    onSave={() => run("save", () => api.acting(dir, "beats_set", { shot: shotId, beats: draft }))}
                    onClear={() => run("clear", () => api.acting(dir, "beats_clear", { shot: shotId }))} onWrite={write} />;
}

// ---------------------------------------------------------------- the emotional arc

/** One thin strip across the film for a character: a cell per scene, brighter where the feeling is stronger; hover for the feeling. */
export function ArcStrip({ sections, points }: { sections: string[]; points: ArcPoint[] }) {
  const by = new Map(points.map((p) => [p.section, p]));
  return (
    <div className="arc-strip" role="img" aria-label={points.length ? points.map((p) => `${p.section}: ${p.emotion}, ${p.intensity} of 10`).join("; ") : "No arc yet"}>
      {sections.map((s) => { const p = by.get(s); return <i key={s} title={p ? `${s}: ${p.emotion} (${p.intensity}/10)` : `${s}: nothing set`} style={{ opacity: p ? 0.25 + p.intensity * 0.075 : 0.08 }} />; })}
    </div>
  );
}

export function ArcView({ data, drafts, dirty, busy, err, onEdit, onSave, onWrite }: {
  data: ArcData; drafts: Record<string, ArcPoint[]>; dirty: Record<string, boolean>; busy: string; err: string;
  onEdit: (name: string, pts: ArcPoint[]) => void; onSave: (name: string) => void; onWrite: () => void;
}) {
  if (!data.sections.length) return <p className="dim">The film has no scenes to put a feeling on yet. Make the shots first.</p>;
  return (
    <div className="arc-view">
      <p className="dim">How each character's feeling travels through the film, scene by scene. Each shot's prompt says where its people are, and the Director follows it, so the feeling progresses instead of starting over in every shot.</p>
      {data.characters.map((name) => {
        const pts = drafts[name] ?? data.arcs[name]?.points ?? [];
        const used = new Set(pts.map((p) => p.section));
        const free = data.sections.filter((s) => !used.has(s));
        const set = (i: number, patch: Partial<ArcPoint>) => onEdit(name, pts.map((p, k) => (k === i ? { ...p, ...patch } : p)));
        return (
          <details key={name} className="arc-char" open={pts.length > 0 || undefined}>
            <summary><b>{name}</b> <span className="dim">{pts.length ? `${pts.length} point${pts.length === 1 ? "" : "s"}${data.arcs[name]?.source === "director" ? " · written by the Director" : ""}` : "no arc"}</span>
              <ArcStrip sections={data.sections} points={pts} /></summary>
            <ul className="arc-points">
              {pts.map((p, i) => (
                <li key={p.section}>
                  <span className="arc-sec">{p.section}</span>
                  <input className="text-input" value={p.emotion} maxLength={80} placeholder="the feeling, in a few words" aria-label={`${name}, ${p.section}: the feeling`} onChange={(e) => set(i, { emotion: e.target.value })} />
                  <input type="range" min={1} max={10} value={p.intensity} aria-label={`${name}, ${p.section}: how strong, 1 to 10`} aria-valuetext={`${p.intensity} of 10`} onChange={(e) => set(i, { intensity: Number(e.target.value) })} />
                  <span className="num arc-n">{p.intensity}</span>
                  <button className="icon-btn" onClick={() => onEdit(name, pts.filter((_, k) => k !== i))} aria-label={`Remove ${p.section} from ${name}'s arc`}><I.Close size={14} /></button>
                </li>))}
            </ul>
            <div className="arc-actions">
              {free.length > 0 && <select className="perf-shot" value="" aria-label={`Add a section to ${name}'s arc`}
                                            onChange={(e) => e.target.value && onEdit(name, [...pts, { section: e.target.value, emotion: "", intensity: 5, note: "" }].sort((a, b) => data.sections.indexOf(a.section) - data.sections.indexOf(b.section)))}>
                <option value="">+ Add a section…</option>{free.map((s) => <option key={s} value={s}>{s}</option>)}</select>}
              <button className="btn small primary" onClick={() => onSave(name)} disabled={!!busy || !dirty[name]}>Save {name}'s arc</button>
            </div>
          </details>);
      })}
      <div className="arc-actions"><button className="btn small" onClick={onWrite} disabled={!!busy || !data.characters.length}>{busy === "write" ? "Writing…" : "Write the arcs with the Director…"}</button></div>
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

export function ArcSection({ dir, onChanged }: { dir: string; onChanged?: () => void }) {
  const [data, setData] = useState<ArcData | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ArcPoint[]>>({});
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.acting<{ arc: ArcData }>(dir, "get").then((r) => { setData(r.arc); setDrafts({}); setDirty({}); }).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); }, [load]);
  const run = async (what: string, fn: () => Promise<unknown>) => { setBusy(what); setErr(""); try { await fn(); await load(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };
  const write = async () => {
    if (!data) return;
    setErr("");
    try {
      const est = await api.acting<AiPrice>(dir, "arc_estimate", {});
      const replacing = data.characters.some((c) => (data.arcs[c]?.points.length ?? 0) > 0);
      if (!await ask(confirmText(`The Director will write an emotional arc for ${data.characters.length} character${data.characters.length === 1 ? "" : "s"} across the film's scenes.${replacing ? " Arcs that exist will be replaced." : ""}`, est), { ok: "Write the arcs" })) return;
      await run("write", () => api.acting(dir, "arc_write", { confirmed: true }));
    } catch (e) { setErr(errorText(e)); }
  };
  if (!data) return err ? <p className="error-text" role="alert">{err}</p> : <p className="dim">Loading…</p>;
  return <ArcView data={data} drafts={drafts} dirty={dirty} busy={busy} err={err}
                  onEdit={(n, pts) => { setDrafts({ ...drafts, [n]: pts }); setDirty({ ...dirty, [n]: true }); }}
                  onSave={(n) => run("save", () => api.acting(dir, "arc_set", { character: n, points: drafts[n] ?? [] }))} onWrite={write} />;
}

// ---------------------------------------------------------------- signature gestures

export function GesturesView({ names, items, dirty, busy, err, onEdit, onSave }: {
  names: string[]; items: Record<string, Gesture[]>; dirty: Record<string, boolean>; busy: string; err: string; onEdit: (n: string, g: Gesture[]) => void; onSave: (n: string) => void;
}) {
  return (
    <div className="gestures-view">
      <p className="dim">The small habits that make a character themselves, for example <i>when flustered: touches the front of her gele</i>. One that fits the moment is suggested in the prompt.</p>
      {names.length === 0 && <p className="dim">No characters in the plan.</p>}
      {names.map((n) => {
        const g = items[n] ?? [];
        const set = (i: number, patch: Partial<Gesture>) => onEdit(n, g.map((x, k) => (k === i ? { ...x, ...patch } : x)));
        return (
          <details key={n} className="gest-char" open={g.length > 0 || undefined}>
            <summary><b>{n}</b> <span className="dim">{g.length ? `${g.length} gesture${g.length === 1 ? "" : "s"}` : "none"}</span></summary>
            <ul className="gest-list">{g.map((x, i) => (
              <li key={i}>
                <span className="dim">When</span><input className="text-input" value={x.when} maxLength={60} placeholder="flustered" aria-label={`${n}, gesture ${i + 1}: when`} onChange={(e) => set(i, { when: e.target.value })} />
                <span className="dim">she</span><input className="text-input" value={x.do} maxLength={160} placeholder="touches the front of her gele" aria-label={`${n}, gesture ${i + 1}: what they do`} onChange={(e) => set(i, { do: e.target.value })} />
                <button className="icon-btn" onClick={() => onEdit(n, g.filter((_, k) => k !== i))} aria-label={`Remove ${n}'s gesture ${i + 1}`}><I.Close size={14} /></button>
              </li>))}</ul>
            <div className="arc-actions">
              {g.length < 8 && <button className="btn small" onClick={() => onEdit(n, [...g, { when: "", do: "" }])}>+ Add a gesture</button>}
              <button className="btn small primary" onClick={() => onSave(n)} disabled={!!busy || !dirty[n]}>Save {n}'s gestures</button>
            </div>
          </details>);
      })}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

export function GesturesSection({ dir, onChanged }: { dir: string; onChanged?: () => void }) {
  const [names, setNames] = useState<string[]>([]);
  const [items, setItems] = useState<Record<string, Gesture[]>>({});
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.acting<{ business: Record<string, Gesture[]> }>(dir, "get").then((r) => { setNames(Object.keys(r.business)); setItems(r.business); setDirty({}); }).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); }, [load]);
  const save = async (n: string) => { setBusy("save"); setErr(""); try { await api.acting(dir, "business_set", { character: n, items: items[n] ?? [] }); await load(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };
  return <GesturesView names={names} items={items} dirty={dirty} busy={busy} err={err} onEdit={(n, g) => { setItems({ ...items, [n]: g }); setDirty({ ...dirty, [n]: true }); }} onSave={save} />;
}
