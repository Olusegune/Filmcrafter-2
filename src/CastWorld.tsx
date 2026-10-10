import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type BibleCharacter, type BibleEnvironment, type BibleProp, type BibleView } from "./api";
import { ask } from "./ask";
import { askText } from "./askText";
import * as I from "./icons";

type Kind = "character" | "environment" | "prop";
type Entry = BibleCharacter | BibleEnvironment | BibleProp;
type Tab = "bible" | Kind;

const TABS: { id: Tab; label: string }[] = [{ id: "bible", label: "Rules & style" }, { id: "character", label: "Characters" }, { id: "environment", label: "Places" }, { id: "prop", label: "Props" }];
const RULES: [string, string, string][] = [["world", "The world", "What is always true here: the place, the era, how things work."], ["tone", "Tone", "How it should feel to watch."],
  ["rules", "Rules the film keeps", "Anything that must never change (a character never takes off her ring)."], ["avoid", "Avoid", "What should never appear."]];
const PHILOSOPHY: [string, string][] = [["visual", "Visual"], ["cinematography", "Cinematography"], ["lighting", "Lighting"], ["acting", "Acting"], ["colour", "Colour"], ["continuity", "Continuity"]];
const CHAR_FIELDS: [string, string, boolean][] = [["role", "Role in the story", false], ["age", "Age", false], ["physical", "Physical traits", true], ["relationships", "Relationships", true], ["arc", "Emotional arc", true], ["voice", "Voice", false], ["notes", "Notes", true]];
const SPATIAL: [string, string][] = [["entrances", "Entrances"], ["exits", "Exits"], ["doors", "Doors"], ["windows", "Windows"], ["landmarks", "Landmarks"], ["furniture", "Furniture"],
  ["blocking", "Where actors can stand"], ["camera_zones", "Where the camera can go"], ["lighting", "Lighting"], ["day_night", "Day or night"]];

const label = (t: Tab) => TABS.find((x) => x.id === t)!.label;

/**
 * The Production Bible, Cast and World: the one source of truth the rest of the film is made from. Seeded from the story, then yours.
 * Characters, places and props are single entries with related states (Sarah at 8, at 28, at 70; the kitchen by day and by night).
 */
export function CastWorld({ dir }: { dir: string }) {
  const [b, setB] = useState<BibleView | null>(null);
  const [tab, setTab] = useState<Tab>("character");
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");

  const apply = (v: BibleView) => setB(v);
  const run = useCallback(async (fn: () => Promise<BibleView>) => { setErr(""); try { const v = await fn(); setB(v); return v; } catch (e) { setErr(errorText(e)); return null; } }, []);
  useEffect(() => {
    // The first time, fill the Bible from the story. Seeding only adds, so doing it again is always safe.
    void run(async () => {
      const v = await api.bible("get", dir);
      if (v.counts.characters + v.counts.environments === 0) {
        const s = await api.bible("seed", dir);
        if (s.added && (s.added.characters || s.added.environments)) setNote(`Filled from your story: ${s.added.characters} characters and ${s.added.environments} places. Check them and add what the story doesn't say.`);
        return s;
      }
      return v;
    });
  }, [dir, run]);

  if (!b) return <div className="cw"><div className="film-load dim">{err || "Opening the Bible…"}</div></div>;
  const list: Entry[] = tab === "character" ? b.characters : tab === "environment" ? b.environments : tab === "prop" ? b.props : [];
  const cur = list.find((x) => x.id === sel) ?? list[0] ?? null;

  const refresh = async () => {
    const s = await run(() => api.bible("seed", dir));
    if (s?.added) setNote(s.added.characters || s.added.environments ? `Added ${s.added.characters} characters and ${s.added.environments} places from the story.` : "Everything in the story is already here.");
  };
  const add = async () => {
    const name = await askText(`Name the new ${tab === "environment" ? "place" : tab}`, tab === "character" ? "e.g. Sarah" : tab === "environment" ? "e.g. The kitchen" : "e.g. The letter");
    if (!name) return;
    const v = await run(() => api.bible("upsert", dir, { kind: tab, item: { name } }));
    if (v?.id) setSel(v.id);
  };

  return (
    <div className="cw">
      <div className="cw-head">
        <div className="cw-tabs" role="tablist">
          {TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => { setTab(t.id); setSel(null); }}>
            {t.label}{t.id !== "bible" && <span className="dim"> {t.id === "character" ? b.counts.characters : t.id === "environment" ? b.counts.environments : b.counts.props}</span>}</button>)}
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn ghost sm" onClick={refresh} title="Add anything new from the story. Nothing you wrote is changed.">Add from the story</button>
      </div>
      {note && <p className="cw-note" role="status">{note} <button className="link" onClick={() => setNote("")}>OK</button></p>}
      {b.need.length > 0 && tab === "bible" && <ul className="cw-need">{b.need.map((n) => <li key={n}>{n}</li>)}</ul>}
      {err && <p className="error-text" role="alert">{err}</p>}

      {tab === "bible" ? <RulesStyle b={b} onSave={(d) => run(() => api.bible("update_rules", dir, d))} /> : (
        <div className="cw-body">
          <ul className="cw-list" aria-label={label(tab)}>
            {list.map((x) => {
              const pic = x.media[0]?.path;
              return <li key={x.id}><button className={cur?.id === x.id ? "on" : ""} onClick={() => setSel(x.id)}>
                <span className="thumb" style={pic ? { backgroundImage: `url("${api.mediaUrl(`${dir}/${pic}`)}")` } : undefined}>{!pic && <I.ImageIcon size={14} />}</span>
                <span className="nm">{x.name}</span>{x.states.length > 1 && <span className="dim">{x.states.length} states</span>}</button></li>;
            })}
            <li><button className="add" onClick={add}>+ Add {tab === "environment" ? "a place" : tab === "prop" ? "a prop" : "a character"}</button></li>
          </ul>
          {cur ? <Editor key={cur.id} dir={dir} kind={tab as Kind} item={cur} media={b.media_kinds} run={run} apply={apply} />
            : <p className="dim cw-empty">{tab === "character" ? "No characters yet. They appear from the story, or add one." : tab === "environment" ? "No places yet." : "No props yet. Add anything that must look the same every time it appears."}</p>}
        </div>)}
    </div>
  );
}

/** The world's rules, the philosophy that guides every shot, and the visual style. */
function RulesStyle({ b, onSave }: { b: BibleView; onSave: (d: Record<string, unknown>) => void }) {
  const [rules, setRules] = useState(b.rules);
  const [phil, setPhil] = useState(b.philosophy);
  const [style, setStyle] = useState(b.style);
  const dirty = JSON.stringify([rules, phil, style]) !== JSON.stringify([b.rules, b.philosophy, b.style]);
  return (
    <div className="cw-rules">
      <section>
        <h2>Visual style</h2>
        <p className="dim">The look affects characters, places, materials, light, camera and movement together, not just a phrase added to a prompt.</p>
        <div className="cw-lanes" role="radiogroup" aria-label="Visual style">
          {b.lanes.map((l) => <button key={l} role="radio" aria-checked={style.lane === l} className={style.lane === l ? "on" : ""} onClick={() => setStyle({ ...style, lane: l })}>{l}</button>)}
        </div>
        <label className="field"><span>What defines this look</span><textarea className="text-input" rows={2} value={style.traits} onChange={(e) => setStyle({ ...style, traits: e.target.value })} placeholder="Materials, textures, how things move" /></label>
        <label className="field"><span>References (one per line: a film, a painter, a link)</span><textarea className="text-input" rows={3} value={style.references.join("\n")}
          onChange={(e) => setStyle({ ...style, references: e.target.value.split("\n") })} placeholder="Describe the qualities you want, not a film to copy" /></label>
      </section>
      <section>
        <h2>World rules</h2>
        {RULES.map(([k, name, hint]) => <label key={k} className="field"><span>{name}</span><textarea className="text-input" rows={2} value={rules[k] ?? ""} placeholder={hint} onChange={(e) => setRules({ ...rules, [k]: e.target.value })} /></label>)}
      </section>
      <section>
        <h2>How the film is made</h2>
        <div className="cw-grid2">{PHILOSOPHY.map(([k, name]) => <label key={k} className="field"><span>{name}</span><textarea className="text-input" rows={2} value={phil[k] ?? ""} onChange={(e) => setPhil({ ...phil, [k]: e.target.value })} /></label>)}</div>
      </section>
      <div className="cw-save"><span className="dim">{dirty ? "Unsaved changes" : `Saved · revision ${b.rev}`}</span>
        <button className="btn primary" disabled={!dirty} onClick={() => onSave({ rules, philosophy: phil, style: { ...style, references: style.references.map((r) => r.trim()).filter(Boolean) } })}>Save</button></div>
    </div>
  );
}

/** One character, place or prop: its words, its related states, and its pictures. */
function Editor({ dir, kind, item, run }: { dir: string; kind: Kind; item: Entry; media: string[]; run: (fn: () => Promise<BibleView>) => Promise<BibleView | null>; apply: (v: BibleView) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const val = (k: string) => draft[k] ?? ((item as unknown as Record<string, string>)[k] ?? "");
  const spatial = (k: string) => draft[`sp:${k}`] ?? ((item as BibleEnvironment).spatial?.[k] ?? "");
  const commit = (k: string) => {
    if (draft[k] === undefined) return;
    void run(() => api.bible("upsert", dir, { kind, item: { id: item.id, [k]: draft[k] } })).then(() => setDraft(({ [k]: _x, ...rest }) => rest));
  };
  const commitSpatial = (k: string) => {
    const key = `sp:${k}`;
    if (draft[key] === undefined) return;
    void run(() => api.bible("upsert", dir, { kind, item: { id: item.id, spatial: { [k]: draft[key] } } })).then(() => setDraft(({ [key]: _x, ...rest }) => rest));
  };
  const field = (k: string, name: string, multi: boolean) => (
    <label className="field" key={k}><span>{name}</span>
      {multi ? <textarea className="text-input" rows={2} value={val(k)} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} onBlur={() => commit(k)} />
        : <input className="text-input" value={val(k)} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} onBlur={() => commit(k)} />}</label>);

  const addPicture = async () => {
    const f = await open({ multiple: true, filters: [{ name: "Pictures", extensions: ["png", "jpg", "jpeg", "webp"] }] });
    const files = typeof f === "string" ? [f] : Array.isArray(f) ? f : [];
    for (const file of files) await run(() => api.bible("add_media", dir, { kind, id: item.id, file, label: "Reference", media_kind: item.media.length ? "reference" : "master" }));
  };
  const addState = async () => {
    const name = await askText("Name the state", kind === "character" ? "e.g. Age 8, Injured, In the red coat" : kind === "environment" ? "e.g. Night, Wrecked" : "e.g. Broken");
    if (name) await run(() => api.bible("add_state", dir, { kind, id: item.id, label: name }));
  };
  const remove = async () => { if (await ask(`Take “${item.name}” out of the Bible?\n\nThe Bible as it is now is kept in its history, and the pictures stay in the film folder.`, { ok: "Take out" })) await run(() => api.bible("remove", dir, { kind, id: item.id })); };

  return (
    <div className="cw-edit">
      <div className="cw-title"><input className="cw-name" value={val("name")} aria-label="Name" onChange={(e) => setDraft({ ...draft, name: e.target.value })} onBlur={() => commit("name")} />
        <span className="dim">{item.scenes.length ? `In scene${item.scenes.length === 1 ? "" : "s"} ${item.scenes.join(", ")}` : item.source === "story" ? "From the story" : "Added by you"}</span>
        <div style={{ flex: 1 }} /><button className="link" onClick={remove}>Take out</button></div>

      <section className="cw-pics">
        <h3>Pictures</h3>
        <div className="cw-media">
          {item.media.map((m) => (
            <figure key={m.path}><img src={api.mediaUrl(`${dir}/${m.path}`)} alt={m.label} />
              <figcaption><span>{m.kind === "master" ? "Master" : m.label}</span>
                <button className="link" onClick={() => run(() => api.bible("remove_media", dir, { kind, id: item.id, path: m.path }))}>remove</button></figcaption></figure>))}
          <button className="cw-addpic" onClick={addPicture}>+ Add pictures…</button>
        </div>
        {item.media.length === 0 && <p className="dim">{kind === "character" ? "Bring your own artwork or reference sheets: front, three-quarter, side, back, expressions. The first one is the master." : "Bring a picture so every shot can match it."}</p>}
      </section>

      {kind === "character" && <div className="cw-fields">{CHAR_FIELDS.map(([k, n, m]) => field(k, n, m))}</div>}
      {kind === "environment" && <>
        {field("description", "What it is", true)}{field("notes", "Notes", true)}
        <details className="cw-spatial" open={SPATIAL.some(([k]) => spatial(k))}><summary>Layout, so the place doesn't change between shots</summary>
          <div className="cw-grid2">{SPATIAL.map(([k, n]) => <label className="field" key={k}><span>{n}</span>
            <textarea className="text-input" rows={2} value={spatial(k)} onChange={(e) => setDraft({ ...draft, [`sp:${k}`]: e.target.value })} onBlur={() => commitSpatial(k)} /></label>)}</div></details></>}
      {kind === "prop" && field("notes", "Notes", true)}

      {kind === "character" && <section className="cw-wardrobe"><h3>Wardrobe</h3>
        {(item as BibleCharacter).wardrobe.length === 0 ? <p className="dim">No outfits yet.</p> : <ul>{(item as BibleCharacter).wardrobe.map((w) => <li key={w.id}><b>{w.name}</b> <span className="dim">{w.notes}</span></li>)}</ul>}
        <button className="btn ghost sm" onClick={async () => { const n = await askText("Name the outfit", "e.g. Red coat"); if (n) await run(() => api.bible("add_wardrobe", dir, { id: item.id, name: n })); }}>+ Add an outfit</button></section>}

      <section className="cw-states"><h3>States <span className="dim">the same {kind === "environment" ? "place" : kind} at another time or in another condition</span></h3>
        <ul>{item.states.map((s) => <li key={s.id}><b>{s.label}</b>{s.age && <span className="dim"> · age {s.age}</span>}{s.notes && <span className="dim"> · {s.notes}</span>}
          {item.states.length > 1 && <button className="link" onClick={() => run(() => api.bible("remove_state", dir, { kind, id: item.id, state: s.id }))}>remove</button>}</li>)}</ul>
        <button className="btn ghost sm" onClick={addState}>+ Add a state</button></section>
    </div>
  );
}
