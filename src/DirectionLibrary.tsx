import { Badge, directionGlyph } from "./glyphs";
import { useEffect, useMemo, useState } from "react";
import { api, errorText } from "./api";
import * as I from "./icons";
import { paletteBand, swatch } from "./colorWords";

type Direction = { id: string; name: string; region: string; origin: string; tags: string[]; genres: string[]; known_for?: string;
  energy: string; summary: string; camera: string; light: string; palette: string[]; editing: string; movement: string; design: string;
  look: string; acting: string; avoid?: string; respect?: string; custom?: boolean };
type Match = { id: string; score: number; why: string[] };

const PARTS = [
  { id: "brief", label: "Brief for the three directions and the treatment" },
  { id: "bible", label: "Production Bible (world, palette, never show)" },
  { id: "look", label: "Look" },
  { id: "acting", label: "Acting profile" },
];

/** Worldwide creative-direction library: browse, match to the story, apply to the project, or save your own. */
export function DirectionLibrarySheet({ dir, onClose, onApplied }: { dir: string; onClose: () => void; onApplied: () => void }) {
  const [all, setAll] = useState<Direction[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [song, setSong] = useState<{ energy: string; moods: string[]; genres: string[]; words: number } | null>(null);
  const [region, setRegion] = useState("Best for your story");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [parts, setParts] = useState<string[]>(PARTS.map((p) => p.id));
  const [overwrite, setOverwrite] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [making, setMaking] = useState(false);
  const load = () => {
    api.directionLibrary<{ directions: Direction[]; current: string | null }>("list", dir).then((r) => { setAll(r.directions); setCurrent(r.current); }).catch((e) => setErr(errorText(e)));
    api.directionLibrary<{ matches: Match[]; story: typeof song }>("match", dir).then((r) => { setMatches(r.matches); setSong(r.story); if (!r.matches.length) setRegion("All"); }).catch(() => setRegion("All"));
  };
  useEffect(load, [dir]); // eslint-disable-line react-hooks/exhaustive-deps
  const regions = useMemo(() => ["Best for your story", "All", ...[...new Set(all.map((d) => d.region))]], [all]);
  const why = new Map(matches.map((m) => [m.id, m]));
  const shown = (region === "Best for your story" ? matches.map((m) => all.find((d) => d.id === m.id)!).filter(Boolean)
    : all.filter((d) => region === "All" || d.region === region))
    .filter((d) => !q || `${d.name} ${d.origin} ${d.tags.join(" ")} ${d.genres.join(" ")} ${d.summary}`.toLowerCase().includes(q.toLowerCase()));
  const d = all.find((x) => x.id === sel);
  const apply = async () => {
    if (!d) return;
    setErr(""); setMsg("");
    try {
      const r = await api.directionLibrary<{ name: string; changed: string[] }>("apply", dir, { id: d.id, parts, overwrite });
      setCurrent(d.id); setMsg(`${r.name} applied: ${r.changed.join(", ") || "nothing new to change (your own settings were kept)"}.`); onApplied();
    } catch (e) { setErr(errorText(e)); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass dl-sheet" role="dialog" aria-label="Direction library" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Direction library</h2><div style={{ flex: 1 }} />
          <button className="btn ghost small" onClick={() => { setMaking(true); setSel(null); }}>Save my own…</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Great filmmakers from around the world, each turned into a working brief for camera, light, colour, pace and design: a way of seeing to learn from, never a copy. Apply one and it guides your Bible and the pictures. Free.</p>
        {song && song.words > 0 && <p className="dl-song"><I.Wave size={13} /> Your story: {song.energy} energy{song.genres.length ? `, ${song.genres.join(", ")}` : ""}{song.moods.length ? `, ${song.moods.slice(0, 3).join(", ")}` : ""}</p>}
        <div className="dl-filters">
          <div className="dl-regions" role="tablist" aria-label="Where it comes from">{regions.map((r) => <button key={r} role="tab" aria-selected={region === r} className={region === r ? "on" : ""} onClick={() => setRegion(r)}>{r}</button>)}</div>
          <input className="text-input dl-search" type="search" placeholder="Search: mood, genre, country…" aria-label="Search directions" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {err && <div className="error-text">{err}</div>}
        {msg && <div className="dl-msg"><I.Check size={14} /> {msg}</div>}
        <div className="dl-body">
          <div className="dl-grid">{shown.map((x) => (
            <button key={x.id} className={`dl-card ${sel === x.id ? "on" : ""}`} onClick={() => { setSel(x.id); setMaking(false); }} aria-pressed={sel === x.id}>
              <span className="dl-band" style={{ background: paletteBand(x.palette) }}>
                <Badge icon={directionGlyph(x.name, x.origin, x.summary)} size={20} />
                {current === x.id && <span className="dl-flag use">In use</span>}
                {current !== x.id && why.get(x.id)?.why.length ? <span className="dl-flag fit" title={why.get(x.id)!.why.join(" · ")}>Fits your story</span> : null}
              </span>
              <span className="dl-body-text">
                <b>{x.name}</b>
                <span className="dl-origin">{x.origin}</span>
                <span className="dl-sum">{x.summary}</span>
              </span>
            </button>))}
            {shown.length === 0 && <p className="dim">No directions match.</p>}</div>
          <div className="dl-detail">
            {making ? <SaveOwn onSaved={() => { setMaking(false); load(); setRegion("My directions"); }} /> : !d ? <div className="dl-empty"><span className="dl-empty-art" aria-hidden="true"><i /><i /><i /><i /></span><b>Pick a direction</b><span className="dim">Its camera, light, palette, editing and design appear here, ready to apply.</span></div> : <>
              <div className="dl-hero" style={{ background: paletteBand(d.palette) }} aria-hidden="true" />
              <h3>{d.name}</h3><div className="dim">{d.origin} · {d.region}</div>
              {d.known_for && <div className="dl-known">{d.known_for}</div>}
              <p className="dl-lead">{d.summary}</p>
              <div className="dl-swatches" aria-label="Palette">{d.palette.map((c) => <span key={c} className="dl-sw"><i style={{ background: swatch(c) }} />{c}</span>)}</div>
              <dl className="dl-kv">
                <dt>Camera</dt><dd>{d.camera}</dd><dt>Light</dt><dd>{d.light}</dd>
                <dt>Editing</dt><dd>{d.editing}</dd><dt>Movement</dt><dd>{d.movement}</dd><dt>Design</dt><dd>{d.design}</dd>
              </dl>
              <details className="dl-more"><summary>Suits, look and acting</summary>
                <dl className="dl-kv">
                  <dt>Suits</dt><dd>{d.genres.join(", ") || "any"} · {d.energy} energy</dd>
                  <dt>Look · acting</dt><dd>{d.look || "—"} · {d.acting || "—"}</dd>
                  {d.avoid && <><dt>Avoid</dt><dd>{d.avoid}</dd></>}
                </dl></details>
              {d.respect && <div className="dl-respect"><I.Alert size={13} /> {d.respect}</div>}
              <details className="dl-more"><summary>What to apply <span className="dim">{parts.length} of {PARTS.length}</span></summary>
                <div className="dl-parts">{PARTS.map((p) => <label key={p.id}><input type="checkbox" checked={parts.includes(p.id)}
                  onChange={(e) => setParts((s) => e.target.checked ? [...s, p.id] : s.filter((x) => x !== p.id))} /> {p.label}</label>)}
                  <label><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} /> Replace my own look, acting and bible entries too</label></div></details>
              <p className="dim dl-then">Then press “Show me three directions”: the AI builds on this brief.</p>
              <div className="dl-apply-bar">
                {d.custom && <button className="btn ghost" onClick={() => api.directionLibrary("delete", null, { id: d.id }).then(() => { setSel(null); load(); })}>Delete</button>}
                <button className="btn primary" onClick={apply} disabled={!parts.length}>Use this direction</button></div>
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}

function SaveOwn({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState<Record<string, string>>({ name: "", origin: "", summary: "", camera: "", light: "", palette: "", editing: "", movement: "", design: "", avoid: "" });
  const [err, setErr] = useState("");
  const row = (k: string, label: string, ph: string) => <><span className="k">{label}</span>
    <input className="text-input" value={f[k]} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></>;
  return (
    <div>
      <h3>Save my own direction</h3>
      <div className="kv settings-kv">
        {row("name", "Name", "e.g. Grandma's Kitchen")}{row("origin", "Inspired by", "e.g. my childhood in Ibadan")}
        {row("summary", "In one line", "What it looks and feels like")}{row("camera", "Camera", "")}{row("light", "Light", "")}
        {row("palette", "Palette", "Comma-separated colours")}{row("editing", "Editing", "")}{row("movement", "Movement", "")}
        {row("design", "Design", "Places, wardrobe, props")}{row("avoid", "Avoid", "")}
      </div>
      {err && <div className="error-text">{err}</div>}
      <div className="sheet-actions"><button className="btn primary" onClick={() => api.directionLibrary("save", null, { ...f, palette: f.palette.split(",") })
        .then(onSaved).catch((e) => setErr(errorText(e)))}>Save to my library</button></div>
    </div>
  );
}
