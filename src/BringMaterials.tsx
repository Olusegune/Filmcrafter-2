import { useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type MaterialItem, type MaterialsPlan, type MaterialsResult } from "./api";
import * as I from "./icons";
import { canTick, KIND_LABEL, SECTIONS, summaryWords, typeWords } from "./materialsWords";

type Choice = { on?: boolean; as?: string; target?: string; new_name?: string };

/**
 * "Bring your own materials": storyboards, character and place sheets, a shot list and notes. Choosing files only reads them and shows where each would go; nothing is added to the film until
 * "Bring it into the film", and nothing here is bought or sent anywhere. What is already approved or written by the person is left alone unless they tick it.
 */
export function BringMaterials({ dir, onClose, onDone }: { dir: string; onClose: () => void; onDone: () => void }) {
  const [plan, setPlan] = useState<MaterialsPlan | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [reference, setReference] = useState(true);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [result, setResult] = useState<MaterialsResult | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) { e.stopImmediatePropagation(); onClose(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  });                                                                  // eslint-disable-line react-hooks/exhaustive-deps

  const scan = async (sources: string[]) => {
    setBusy("scan"); setErr(""); setResult(null);
    try { setPlan(await api.filmMaterials("scan", dir, { sources })); setChoices({}); } catch (e) { setErr(errorText(e)); }
    setBusy("");
  };
  const pickFiles = async () => { const f = await open({ multiple: true, filters: [{ name: "Storyboards, sheets, lists, notes", extensions: ["png", "jpg", "jpeg", "webp", "pdf", "csv", "tsv", "txt", "md", "zip"] }] }); if (f) void scan(Array.isArray(f) ? f : [f]); };
  const pickFolder = async () => { const f = await open({ directory: true, multiple: false }); if (typeof f === "string") void scan([f]); };

  const change = (id: string, patch: Choice, refresh = false) => {
    const next = { ...choices, [id]: { ...choices[id], ...patch } };
    setChoices(next);
    if (!refresh || !plan) return;
    window.clearTimeout(timer.current);                                // ask the engine again, so the line reads what will really happen
    timer.current = window.setTimeout(async () => {
      try { const r = await api.filmMaterials<MaterialsPlan>("review", dir, { token: plan.token, choices: next }); setPlan({ ...plan, ...r }); } catch (e) { setErr(errorText(e)); }
    }, 350);
  };
  const isOn = (it: MaterialItem) => canTick(it) && (choices[it.id]?.on ?? it.on);
  const chosen = useMemo(() => (plan?.items ?? []).filter(isOn), [plan, choices]);   // eslint-disable-line react-hooks/exhaustive-deps

  const apply = async () => {
    if (!plan) return;
    setBusy("apply"); setErr("");
    try {
      const sent: Record<string, unknown> = { ...choices, _options: { reference } };
      for (const it of plan.items) if (canTick(it)) sent[it.id] = { ...choices[it.id], on: isOn(it) };
      setResult(await api.filmMaterials<MaterialsResult>("apply", dir, { token: plan.token, choices: sent }));
      setPlan(null); onDone();
    } catch (e) { setErr(errorText(e)); }
    setBusy("");
  };

  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass bm" role="dialog" aria-label="Bring your own materials" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Bring your own materials</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close" disabled={!!busy}><I.Close size={18} /></button></div>
        {!plan && !result && <>
          <p className="bm-lead">Besides a script, you can bring a storyboard, character and place sheets, a shot list and notes. They guide how the film is made: panels become the chosen picture for their shots, sheets become the pictures the characters and places are made from, and the shot list fills in the shots.</p>
          <ul className="bm-kinds">
            <li><b>Storyboard</b> pictures, a PDF of them, or a zip. Name them by shot (<code>S01-03.png</code>) or put them in order.</li>
            <li><b>Sheets</b> in folders such as <code>characters/Sarah/front.png</code>, <code>locations/Kitchen.jpg</code>, <code>props/Red kettle.png</code>.</li>
            <li><b>Shot list</b> as a CSV (from Excel or Google Sheets): scene, shot, size, movement, length, description, dialogue, notes.</li>
            <li><b>Notes</b> as .txt or .md (a tone, world or rules note can be added to the Bible).</li>
          </ul>
          <div className="cv-actions"><button className="btn primary" onClick={() => void pickFiles()} disabled={!!busy}>{busy === "scan" ? "Reading…" : "Choose files…"}</button>
            <button className="btn" onClick={() => void pickFolder()} disabled={!!busy}>Choose a folder…</button></div>
          <p className="why">Choosing only reads them. Nothing is added to the film until you say so, and nothing is bought or sent anywhere. Your originals stay where they are.</p>
        </>}
        {err && <p className="why bm-warn" role="alert">{err}</p>}
        {plan && <>
          <p className="bm-lead">{summaryWords(plan.counts) ? <>Ready to bring in: <b>{summaryWords(plan.counts)}</b>. Untick anything that is not right.</> : "Nothing is ticked yet."}</p>
          {plan.problems.map((p) => <p key={p} className="why bm-warn">{p}</p>)}
          {SECTIONS.map((sec) => {
            const rows = plan.items.filter((i) => sec.types.includes(i.type));
            if (!rows.length) return null;
            return <section key={sec.id} className="bm-sec"><h3>{sec.title} <span className="dim">{rows.length}</span></h3><p className="why">{sec.hint}</p>
              <ul className="bm-list">{rows.map((it) => <Row key={it.id} it={it} on={isOn(it)} choice={choices[it.id]} shots={plan.shots ?? []} onChange={change} />)}</ul></section>;
          })}
          <label className="ov-check bm-opt"><input type="checkbox" checked={reference} onChange={(e) => setReference(e.target.checked)} /> Let each storyboard panel guide the framing of its shot's hero picture (free; the picture itself is still made, and priced, later)</label>
          <div className="cv-actions">
            <button className="btn primary" disabled={!!busy || !chosen.length} onClick={() => void apply()}>{busy === "apply" ? "Bringing in…" : `Bring ${chosen.length} into the film`}</button>
            <button className="btn" disabled={!!busy} onClick={() => { setPlan(null); setChoices({}); }}>Start again</button>
            <span className="why">A snapshot of the film's records is taken first.</span></div>
        </>}
        {result && <>
          <p className="bm-lead" role="status">{result.message}</p>
          {result.applied.length > 0 && <ul className="bm-done">{result.applied.map((a) => <li key={a.id}><I.Check size={13} /> {a.what}<span className="dim"> ({a.title})</span></li>)}</ul>}
          {result.failed.map((f) => <p key={f.id} className="why bm-warn">{f.title}: {f.why}</p>)}
          {result.changed_since_scan.length > 0 && <p className="why bm-warn">These files changed after they were read, so they were not used: {result.changed_since_scan.join(", ")}. Choose them again.</p>}
          <div className="cv-actions"><button className="btn primary" onClick={onClose}>Done</button><button className="btn" onClick={() => setResult(null)}>Bring in more</button></div>
        </>}
      </div>
    </div>
  );
}

function Row({ it, on, choice, shots, onChange }: { it: MaterialItem; on: boolean; choice?: Choice; shots: { id: string; scene: number; title: string }[]; onChange: (id: string, c: Choice, refresh?: boolean) => void }) {
  const tick = canTick(it);
  const asKind = choice?.as;
  return (
    <li className={`bm-row ${on ? "on" : ""} ${it.blocked ? "blocked" : ""}`}>
      {tick ? <input type="checkbox" checked={on} onChange={(e) => onChange(it.id, { on: e.target.checked })} aria-label={`Bring in ${it.title}`} /> : <span className="bm-nobox" aria-hidden="true" />}
      {it.preview && <img className="bm-thumb" src={api.mediaUrl(it.preview)} alt="" loading="lazy" />}
      <div className="bm-main">
        <div className="bm-title"><b>{typeWords(it)}</b></div>
        <div className="dim bm-file">{it.rel ?? it.title}</div>
        {it.changes && <ul className="bm-changes">{it.changes.map((c) => <li key={c.label}><span className="dim">{c.label}:</span> {c.old !== "" && c.old !== undefined ? <><s>{String(c.old)}</s> → </> : null}<b>{String(c.new)}</b></li>)}</ul>}
        {it.excerpt && <div className="dim bm-excerpt">{it.excerpt}</div>}
        {it.notes.map((n) => <div key={n} className="why">{n}</div>)}
        {it.blocked && <div className="why bm-warn">{it.blocked}</div>}
        <div className="bm-controls">
          {(it.type === "unsorted" || it.type === "storyboard" || it.type === "asset") &&
            <label>This is <select className="text-input" value={asKind ?? (it.type === "asset" ? it.kind : it.type === "storyboard" ? "storyboard" : "")} onChange={(e) => onChange(it.id, { as: e.target.value, on: e.target.value !== "skip" }, true)}>
              {it.type === "unsorted" && <option value="">choose…</option>}
              {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>}
          {it.type === "storyboard" && <label>Shot <select className="text-input" value={choice?.target ?? it.shot ?? ""} onChange={(e) => onChange(it.id, { target: e.target.value, on: true }, true)}>
            <option value="">choose…</option>{shots.map((s) => <option key={s.id} value={s.id}>{s.id}{s.title && s.title !== "New shot" ? ` · ${s.title}` : ""}</option>)}</select></label>}
          {(it.type === "asset" || (it.type === "unsorted" && asKind && asKind !== "storyboard" && asKind !== "skip")) &&
            <label>Name <input className="text-input" defaultValue={it.name ?? ""} placeholder="Whose or what is it?" onChange={(e) => onChange(it.id, { new_name: e.target.value, on: !!e.target.value.trim() }, true)} /></label>}
          {it.type === "note" && <label>Use it <select className="text-input" value={choice?.target ?? it.target ?? "keep"} onChange={(e) => onChange(it.id, { target: e.target.value }, true)}>
            <option value="keep">Only keep it as a note</option><option value="world">Add to the Bible: world</option><option value="tone">Add to the Bible: tone</option><option value="rules">Add to the Bible: rules</option><option value="avoid">Add to the Bible: avoid</option></select></label>}
        </div>
      </div>
    </li>
  );
}
