import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Sheet } from "./Sheet";
import { api, errorText, type Grade, type GradingAction, type GradingState, type LutInfo } from "./api";
import * as I from "./icons";
import "./color.css";

type Num = keyof Pick<Grade, "exposure" | "brightness" | "contrast" | "highlights" | "shadows" | "whites" | "blacks" | "saturation" | "vibrance" | "hue" | "temperature" | "tint" | "gamma" | "lift" | "gain">;
const GROUPS: { title: string; items: [Num, string, number][] }[] = [
  { title: "Light", items: [["exposure", "Exposure", 0.05], ["brightness", "Brightness", 0.01], ["contrast", "Contrast", 0.01], ["highlights", "Highlights", 0.01], ["shadows", "Shadows", 0.01], ["whites", "Whites", 0.01], ["blacks", "Blacks", 0.01]] },
  { title: "Colour", items: [["temperature", "Temperature", 0.01], ["tint", "Tint", 0.01], ["saturation", "Saturation", 0.01], ["vibrance", "Vibrance", 0.01], ["hue", "Hue", 1]] },
  { title: "Balance", items: [["lift", "Lift", 0.01], ["gamma", "Gamma", 0.01], ["gain", "Gain", 0.01]] },
];
const RGB: [keyof Pick<Grade, "lift_rgb" | "gamma_rgb" | "gain_rgb">, string][] = [["lift_rgb", "Lift"], ["gamma_rgb", "Gamma"], ["gain_rgb", "Gain"]];
const SPACE_NAME: Record<string, string> = { rec709: "Rec.709", srgb: "sRGB", log: "Log", hdr_pq: "HDR (PQ)", hdr_hlg: "HDR (HLG)", dci_p3: "DCI-P3", other: "Other" };
const same = (a: Grade, b: Grade) => JSON.stringify(a) === JSON.stringify(b);

/** A slider that says its value, goes back to zero on a double click, and can be moved with the arrow keys. */
function Slider({ id, label, value, min, max, step, onChange }: { id: string; label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  const dp = step >= 1 ? 0 : step >= 0.05 ? 2 : 2;
  return (
    <div className="cs-row">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} aria-valuetext={`${value.toFixed(dp)}`} onChange={(e) => onChange(Number(e.target.value))} onDoubleClick={() => onChange(0)} />
      <output htmlFor={id} className={value !== 0 ? "on" : ""}>{value.toFixed(dp)}</output>
    </div>
  );
}

/**
 * Colour Studio: put a grade on a shot, a scene or the whole film, and a .cube LUT if you like. Nothing here changes a take: the grade is applied when the film is put together, the preview
 * frame is made by the same filter text, and every change can be undone. Free and local.
 */
export function ColorStudioSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged?: () => void }) {
  const [st, setSt] = useState<GradingState | null>(null);
  const [scope, setScope] = useState<{ kind: "film" | "scene" | "shot"; key: string }>({ kind: "film", key: "" });
  const [draft, setDraft] = useState<Grade>({});
  const [look, setLook] = useState("");                                          // the shot the preview frame is made from
  const [pic, setPic] = useState<{ before: string; after: string } | null>(null);
  const [view, setView] = useState<"split" | "before" | "after">("split");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [q, setQ] = useState("");

  const saved = useMemo<Grade>(() => (st ? (scope.kind === "film" ? st.grades.film : scope.kind === "scene" ? st.grades.scenes[scope.key] : st.grades.shots[scope.key]) ?? {} : {}), [st, scope]);
  const dirty = !same(draft, saved);
  const apply = useCallback((s: GradingState) => { setSt(s); }, []);
  const call = useCallback(async (action: GradingAction, data: Record<string, unknown> = {}) => {
    setBusy(true); setErr(""); setNote("");
    try { const s = await api.grading(dir, action, data); apply(s); onChanged?.(); return s; } catch (e) { setErr(errorText(e)); return null; } finally { setBusy(false); }
  }, [dir, apply, onChanged]);

  useEffect(() => { let live = true; api.grading(dir, "state").then((s) => live && apply(s)).catch((e) => live && setErr(errorText(e))); return () => { live = false; }; }, [dir, apply]);
  // the sliders start from the saved grade when the scope changes or when the saved grade itself changes; an unrelated change (a favourite, a saved look) leaves what you are editing alone
  const bindKey = `${scope.kind}:${scope.key}:${JSON.stringify(saved)}`;
  const [bound, setBound] = useState(bindKey);
  if (bound !== bindKey) { setBound(bindKey); setDraft(saved); }

  const shots = st?.shots ?? [];
  const scenes = useMemo(() => { const seen = new Map<number, string>(); for (const s of shots) if (s.scene != null && !seen.has(s.scene)) seen.set(s.scene, s.heading); return [...seen]; }, [shots]);
  const inScope = useMemo(() => shots.filter((s) => scope.kind === "film" || (scope.kind === "scene" ? String(s.scene) === scope.key : s.id === scope.key)), [shots, scope]);
  useEffect(() => { if (!inScope.some((s) => s.id === look)) setLook(inScope[0]?.id ?? ""); }, [inScope, look]);

  // the preview frame is made again a moment after the last change, from the grade as it stands on screen
  const seq = useRef(0);
  useEffect(() => {
    if (!look || !st) return;
    const n = ++seq.current;
    const t = setTimeout(() => {
      api.grading<{ before: string; after: string }>(dir, "preview", { shot: look, grade: draft }).then((r) => { if (n === seq.current) { setPic(r); setNote(""); } })
        .catch((e) => { if (n === seq.current) { setPic(null); setNote(errorText(e)); } });
    }, 500);
    return () => clearTimeout(t);
  }, [dir, look, draft, st]);

  const set = (k: Num, v: number) => setDraft((g) => { const n = { ...g }; if (v === 0) delete n[k]; else n[k] = v; return n; });
  const setRgb = (k: "lift_rgb" | "gamma_rgb" | "gain_rgb", i: number, v: number) => setDraft((g) => { const a = [...(g[k] ?? [0, 0, 0])]; a[i] = v; const n = { ...g }; if (a.some(Boolean)) n[k] = a; else delete n[k]; return n; });
  const range = (k: string): [number, number] => { const r = st?.ranges[k]; return r ? [r[0], r[1]] : [-1, 1]; };
  const lutOf = (id?: string): LutInfo | undefined => st?.luts.find((l) => l.id === id);
  const lutOk = (l: LutInfo) => l.space_in === st?.picture_space && l.space_out === st?.picture_space;

  const importLut = async () => {
    const f = await open({ multiple: false, filters: [{ name: "LUT", extensions: ["cube"] }] });
    if (typeof f === "string") await call("lut_import", { path: f });
  };
  const key = scope.kind === "film" ? null : scope.key;
  const where = scope.kind === "film" ? "the whole film" : scope.kind === "scene" ? `scene ${scope.key}` : `shot ${scope.key}`;
  const swingNote = st?.swing[scope.kind === "film" ? "film" : `${scope.kind}:${scope.key}`];
  const shown = pic ? (rel: string) => api.mediaUrl(`${dir}/${rel}`) : null;
  const luts = (st?.luts ?? []).filter((l) => l.name.toLowerCase().includes(q.trim().toLowerCase()));
  const count = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

  return (
    <Sheet label="Color Studio" className="cs-sheet" onDismiss={onClose}>
      <div className="vs-head"><h2>Color <span className="dim pd-sub">Color Studio</span></h2><div style={{ flex: 1 }} />
        <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      <p className="sub">Grade a shot, a scene or the whole film. Your takes are never changed: the grade is added when the film is put together, and it can be undone. Free; nothing is sent anywhere.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {!st ? <p className="dim">Loading…</p> : (
        <div className="cs-grid">
          <nav className="cs-scope" aria-label="Where the grade goes">
            <button type="button" className={scope.kind === "film" ? "on" : ""} aria-current={scope.kind === "film" ? "true" : undefined} onClick={() => setScope({ kind: "film", key: "" })}>
              Whole film{Object.keys(st.grades.film).length ? <span className="pd-flag mine" title="Has a grade">●</span> : null}</button>
            {scenes.map(([n, h]) => (
              <button type="button" key={n} className={scope.kind === "scene" && scope.key === String(n) ? "on" : ""} aria-current={scope.kind === "scene" && scope.key === String(n) ? "true" : undefined} onClick={() => setScope({ kind: "scene", key: String(n) })}>
                <span className="num">{n}</span> {h || "Scene"}{st.grades.scenes[String(n)] ? <span className="pd-flag mine" title="Has a grade">●</span> : null}</button>))}
            {shots.length > 0 && <details className="cs-shots"><summary>Single shots <span className="dim">({count(shots.length, "shot")})</span></summary>
              {shots.map((s) => (
                <button type="button" key={s.id} className={scope.kind === "shot" && scope.key === s.id ? "on" : ""} aria-current={scope.kind === "shot" && scope.key === s.id ? "true" : undefined} onClick={() => setScope({ kind: "shot", key: s.id })}>
                  {s.id}{st.grades.shots[s.id] ? <span className="pd-flag mine" title="Has a grade">●</span> : null}</button>))}</details>}
          </nav>

          <div className="cs-main">
            <h3 className="perf-h">Grade for {where}</h3>
            <div className="cs-preview" aria-label="Before and after">
              <div className="cs-view" role="group" aria-label="Show">
                {(["split", "before", "after"] as const).map((v) => <button key={v} type="button" className={view === v ? "on" : ""} aria-pressed={view === v} onClick={() => setView(v)}>{v === "split" ? "Before and after" : v === "before" ? "Before" : "After"}</button>)}
                {scope.kind !== "shot" && inScope.length > 1 && <label className="cs-look">Shot to look at <select value={look} onChange={(e) => setLook(e.target.value)}>{inScope.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}</select></label>}
              </div>
              {!look ? <p className="dim cs-ph">No shot to look at yet.</p> : shown && pic ? (
                <div className={`cs-frames ${view}`}>
                  {view !== "after" && <figure><img src={shown(pic.before)} alt="Before the grade" /><figcaption>Before</figcaption></figure>}
                  {view !== "before" && <figure><img src={shown(pic.after)} alt="With the grade" /><figcaption>{dirty ? "After (not saved)" : "After"}</figcaption></figure>}
                </div>) : <p className="dim cs-ph" role="status">{note || "Making the preview frame…"}</p>}
              {note && pic && <p className="dim" role="status">{note}</p>}
            </div>

            <div className="cs-sliders">
              {GROUPS.map((g) => (
                <fieldset key={g.title}><legend>{g.title}</legend>
                  {g.items.map(([k, label, step]) => { const [lo, hi] = range(k); return <Slider key={k} id={`cs-${k}`} label={label} value={draft[k] ?? 0} min={lo} max={hi} step={step} onChange={(v) => set(k, v)} />; })}
                </fieldset>))}
              <details className="cs-rgb" open={RGB.some(([k]) => draft[k])}><summary>Red, green and blue separately</summary>
                {RGB.map(([k, label]) => (
                  <fieldset key={k}><legend>{label}</legend>
                    {["Red", "Green", "Blue"].map((c, i) => <Slider key={c} id={`cs-${k}-${i}`} label={c} value={draft[k]?.[i] ?? 0} min={-1} max={1} step={0.01} onChange={(v) => setRgb(k, i, v)} />)}
                  </fieldset>))}
              </details>
            </div>

            <section className="cs-lut" aria-label="LUT">
              <h4 className="pd-h">LUT <span className="dim">a colour look from a .cube file</span></h4>
              <div className="cs-lutrow">
                <label>Look <select value={draft.lut?.id ?? ""} onChange={(e) => setDraft((g) => { const n = { ...g }; if (e.target.value) n.lut = { id: e.target.value, intensity: g.lut?.intensity ?? 1 }; else delete n.lut; return n; })}>
                  <option value="">None</option>
                  {st.luts.map((l) => <option key={l.id} value={l.id}>{l.favorite ? "★ " : ""}{l.name}{lutOk(l) ? "" : " (not for Rec.709)"}</option>)}</select></label>
                <button type="button" className="btn small" onClick={importLut} disabled={busy}>Import a LUT…</button>
              </div>
              {draft.lut && <Slider id="cs-lutk" label="Intensity" value={draft.lut.intensity} min={0} max={1} step={0.01} onChange={(v) => setDraft((g) => ({ ...g, lut: { id: g.lut!.id, intensity: v } }))} />}
              {draft.lut && lutOf(draft.lut.id) && <p className="dim">{lutOf(draft.lut.id)!.kind === "technical" ? "Technical" : "Creative"} LUT: expects {SPACE_NAME[lutOf(draft.lut.id)!.space_in] ?? "other"} pictures, makes {SPACE_NAME[lutOf(draft.lut.id)!.space_out] ?? "other"}.
                {!lutOk(lutOf(draft.lut.id)!) && <b> FilmCrafter's pictures are Rec.709, so this one is not applied.</b>}</p>}
              {st.luts.length > 0 && (
                <details className="cs-lib"><summary>LUT library <span className="dim">({count(st.luts.length, "LUT")})</span></summary>
                  <label className="cs-q">Search <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name" /></label>
                  <ul>{luts.map((l) => (
                    <li key={l.id}><span>{l.name} <span className="dim">{l.kind}, {SPACE_NAME[l.space_in] ?? l.space_in} to {SPACE_NAME[l.space_out] ?? l.space_out}, {l.dims}D {l.size}</span></span>
                      <button type="button" className="btn small ghost" aria-pressed={l.favorite} aria-label={`${l.favorite ? "Unmark" : "Mark"} ${l.name} as a favorite`} onClick={() => call("lut_favorite", { id: l.id, on: !l.favorite })}>{l.favorite ? "★" : "☆"}</button>
                      <button type="button" className="btn small ghost" aria-label={`Remove ${l.name}`} onClick={() => call("lut_remove", { id: l.id })}>Remove</button></li>))}</ul>
                  {luts.length === 0 && <p className="dim">No LUT matches.</p>}
                </details>)}
            </section>

            {swingNote && (swingNote.clipped_whites || swingNote.crushed_blacks) && (
              <p className="cs-warn" role="status">{swingNote.clipped_whites ? "The brightest parts of this grade are pushed past white and will lose detail. " : ""}{swingNote.crushed_blacks ? "The darkest parts are pushed to pure black and will lose detail. " : ""}Ease off the sliders to keep them.</p>)}

            <div className="pd-field-actions cs-actions">
              <button type="button" className="btn small primary" disabled={busy || !dirty} onClick={() => call("set_grade", { scope: scope.kind, key, grade: draft })}>Save grade for {where}</button>
              <button type="button" className="btn small" disabled={busy || !dirty} onClick={() => setDraft(saved)}>Undo my changes</button>
              <button type="button" className="btn small ghost" disabled={busy || Object.keys(saved).length === 0} onClick={() => call("clear_grade", { scope: scope.kind, key })}>Take the grade off {where}</button>
              <span className="cs-sp" />
              <button type="button" className="btn small ghost" disabled={busy || st.history.length === 0} onClick={() => call("undo")} title={st.history.length ? `Undo: ${st.history[st.history.length - 1].what}` : "Nothing to undo"}>Undo last save</button>
            </div>

            <section className="cs-mine" aria-label="My looks">
              <h4 className="pd-h">My looks</h4>
              <div className="cs-lutrow">
                <label>Name <input type="text" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Soft evening" /></label>
                <button type="button" className="btn small" disabled={busy || !name.trim() || Object.keys(saved).length === 0} onClick={async () => { if (await call("preset_save", { name, scope: scope.kind, key })) setName(""); }}>Save {where === "the whole film" ? "the film's" : "this"} grade as a look</button>
              </div>
              {st.presets.length === 0 ? <p className="dim">Save a grade you like and put it on any scope in one press.</p> : (
                <ul>{st.presets.map((p) => (
                  <li key={p.name}><span>{p.name}</span>
                    <button type="button" className="btn small" disabled={busy} aria-label={`Put ${p.name} on ${where}`} onClick={() => call("preset_apply", { name: p.name, scope: scope.kind, key })}>Put on {where}</button>
                    <button type="button" className="btn small ghost" aria-label={`Delete the look ${p.name}`} onClick={() => call("preset_delete", { name: p.name })}>Delete</button></li>))}</ul>)}
            </section>
          </div>
        </div>)}
    </Sheet>
  );
}
