import { useCallback, useEffect, useRef, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText } from "./api";
import * as I from "./icons";
import "./motiongraphics.css";

type Slot = { id: string; label: string; default: string };
type Template = { id: string; name: string; use: string; seconds: number; layers: number; slots: Slot[] };

/** The picture the engine draws for a template with these words (the same code that draws it in the film; movement is not shown). */
function Preview({ dir, id, texts, alt }: { dir: string; id: string; texts: Record<string, string>; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const key = JSON.stringify(texts);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.layerKit<{ path: string }>(dir, "builtin_preview", { id, texts }).then((r) => { if (live) { setSrc(api.mediaUrl(`${dir}/${r.path}`)); setErr(""); } }).catch((e) => live && setErr(errorText(e)));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [dir, id, key]);                                                              // eslint-disable-line react-hooks/exhaustive-deps
  return src ? <img src={src} alt={alt} loading="lazy" /> : <div className="mg-wait" role={err ? "alert" : undefined}>{err || "Drawing…"}</div>;
}

/**
 * Motion graphics: ready-made titles, lower thirds, callouts and cards. Choose one, type its words, see exactly how it will look, and add it at the playhead. It becomes a few ordinary layers
 * (a group you can take away again as one): change the words, colours, timing or movement afterwards in the timeline and the Layers panel. Free and drawn by FilmCrafter itself.
 */
export function MotionGraphicsSheet({ dir, time, onClose, onChanged }: { dir: string; time: number; onClose: () => void; onChanged?: () => void }) {
  const [list, setList] = useState<Template[] | null>(null);
  const [pick, setPick] = useState<string>("lower_third");
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ group: string; made: number; at: number; name: string } | null>(null);
  const at = Math.max(0, Math.round(time * 10) / 10);
  useEffect(() => { api.layerKit<{ templates: Template[] }>(dir, "builtin_list").then((r) => setList(r.templates)).catch((e) => setErr(errorText(e))); }, [dir]);
  const tpl = list?.find((t) => t.id === pick) ?? null;
  const words = (t: Template) => Object.fromEntries(t.slots.map((s) => [s.id, texts[`${t.id}:${s.id}`] ?? s.default]));
  const choose = (id: string) => { setPick(id); setDone(null); setErr(""); };
  const add = useCallback(async () => {
    if (!tpl) return;
    setBusy(true); setErr("");
    try {
      const r = await api.layerKit<{ made: number; group: string }>(dir, "builtin_apply", { id: tpl.id, at, texts: words(tpl) });
      setDone({ group: r.group, made: r.made, at, name: tpl.name });
      window.dispatchEvent(new Event("pf-overlays-changed")); onChanged?.();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }, [tpl, dir, at, texts]);                                                       // eslint-disable-line react-hooks/exhaustive-deps
  const away = async () => {
    if (!done) return;
    setBusy(true); setErr("");
    try { await api.layerKit(dir, "template_remove", { group: done.group }); setDone(null); window.dispatchEvent(new Event("pf-overlays-changed")); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const saved = useRef(false);
  saved.current = !!done;

  return (
    <Sheet label="Motion graphics" className="mg-sheet" onDismiss={onClose}>
      <div className="vs-head"><h2>Motion graphics <span className="dim pd-sub">titles, lower thirds and cards</span></h2><div style={{ flex: 1 }} />
        <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      <p className="sub">Choose one, type its words, and add it at the playhead. It becomes a few ordinary layers: you can change the words, colours, timing and movement afterwards, or take the whole thing away again. Drawn by FilmCrafter, free, and sharp at any size.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {!list ? <p className="dim">Loading…</p> : (
        <div className="mg-grid">
          <ul className="mg-cards" aria-label="Motion graphics">
            {list.map((t) => (
              <li key={t.id} className={`mg-card ${pick === t.id ? "on" : ""}`} aria-label={t.name}>
                <button type="button" className="mg-pick" aria-pressed={pick === t.id} onClick={() => choose(t.id)}>
                  <Preview dir={dir} id={t.id} texts={words(t)} alt={`How ${t.name} looks`} />
                  <span className="mg-name">{t.name}</span>
                  <span className="dim mg-use">{t.use}</span>
                  <span className="dim mg-len">{t.seconds.toFixed(1)} s · {t.layers} layers</span>
                </button>
              </li>))}
          </ul>
          {tpl && (
            <aside className="mg-side" aria-label={`${tpl.name} words`}>
              <h3 className="perf-h">{tpl.name}</h3>
              <p className="dim">{tpl.use}</p>
              {tpl.slots.map((s) => (
                <label key={s.id} className="mg-slot">{s.label}
                  <input type="text" maxLength={60} value={texts[`${tpl.id}:${s.id}`] ?? s.default} onChange={(e) => { setDone(null); setTexts((x) => ({ ...x, [`${tpl.id}:${s.id}`]: e.target.value })); }} />
                </label>))}
              <button type="button" className="btn primary" disabled={busy} onClick={() => void add()}>Add at the playhead ({at.toFixed(1)} s)</button>
              {done && (
                <p className="mg-done" role="status">Added {done.name}: {done.made} layers from {done.at.toFixed(1)} s. They are in the timeline and the Layers panel.{" "}
                  <button type="button" className="link" onClick={() => void away()}>Take it away again</button></p>)}
              <p className="dim mg-note">The picture shows how it looks once it has settled; it moves in when the film plays.</p>
            </aside>)}
        </div>)}
    </Sheet>
  );
}
