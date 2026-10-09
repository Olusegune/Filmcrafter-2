import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, fmtTime, type ScriptPlan, type ShowItem, type ShowStatus } from "./api";
import { LibrarySheet } from "./Board";
import { DialogueEditor, VoicesSheet } from "./Dialogue";
import { AmbienceSheet, BudgetSheet, CardSheet, useShowOvernight } from "./ShowExtras";
import { SongMaker } from "./SongMaker";
import * as I from "./icons";
import { ask } from "./ask";

const AUDIO = ["mp3", "wav", "m4a", "flac", "aac", "ogg"];
const IMAGE = ["png", "jpg", "jpeg", "webp"];
const TRANSITION: Record<ShowItem["transition"], string> = { cut: "Cut", black: "Through black", flow: "Flow into next" };
const mins = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

/** A show: acts of numbers (songs) and spoken scenes, one cast and one world, exported as one film. */
export function ShowView({ dir, onOpenItem, onHome }: { dir: string; onOpenItem: (path: string) => void; onHome: () => void }) {
  const [st, setSt] = useState<ShowStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState<null | { kind: "number" | "scene"; song?: string; title: string; setting?: string; act: number }>(null);
  const [castOpen, setCastOpen] = useState(false);
  const [voicesOpen, setVoicesOpen] = useState(false);
  const [dialogue, setDialogue] = useState<ShowItem | null>(null);
  const [progress, setProgress] = useState("");
  const [script, setScript] = useState<null | { file: string; songs?: string; one?: boolean; plan?: ScriptPlan; err?: string }>(null);
  const [costumeAct, setCostumeAct] = useState<number | null>(null);
  const [card, setCard] = useState<null | { act: number; item?: ShowItem }>(null);
  const [ambience, setAmbience] = useState<ShowItem | null>(null);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [subs, setSubs] = useState(true);
  const [making, setMaking] = useState<number | null>(null);

  const load = useCallback(async () => { setSt(await api.show("status", dir)); }, [dir]);
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, [load]);
  useEffect(() => {
    const un = api.onEngine((e) => { if ((e.task === "show" || e.task === "voices") && e.stage) setProgress(String(e.stage)); });
    return () => { un.then((f) => f()); };
  }, []);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setErr(""); setNote("");
    try { await fn(); await load(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); setProgress(""); }
  };
  const chooseSong = async (actIndex: number) => {
    const f = await open({ filters: [{ name: "Song", extensions: AUDIO }] });
    if (typeof f === "string") setAdding({ kind: "number", song: f, title: f.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, ""), act: actIndex });
  };
  const addExisting = async (actIndex: number) => {
    const f = await open({ filters: [{ name: "PULSEFRAME Project", extensions: ["pulseframe"] }] });
    if (typeof f === "string") await act("existing", () => api.show("add_existing", dir, { project: f.replace(/[\\/][^\\/]+\.pulseframe$/i, ""), act: actIndex }));
  };
  const previewScript = async (file: string, songs?: string, one?: boolean) => {
    setScript({ file, songs, one });
    try { setScript({ file, songs, one, plan: await api.show<ScriptPlan>("preview_script", dir, { file, songs_dir: songs, one_song: !!one }) }); }
    catch (e) { setScript({ file, songs, one, err: errorText(e) }); }
  };
  const chooseScript = async () => {
    const f = await open({ filters: [{ name: "Script", extensions: ["txt", "md", "fountain", "pdf"] }] });
    if (typeof f === "string") await previewScript(f);
  };
  const chooseSongsFolder = async () => {
    const f = await open({ directory: true });
    if (script && typeof f === "string") await previewScript(script.file, f, script.one);
  };
  const importScript = () => {
    const x = script;
    setScript(null);
    if (!x) return;
    act("script", async () => {
      const r = await api.show<ShowStatus & { imported: { numbers: number; scenes: number; characters_added: number; songs_missing: number } }>(
        "import_script", dir, { file: x.file, songs_dir: x.songs, one_song: !!x.one });
      const n = r.imported;
      setNote(`Imported ${n.numbers} number${n.numbers === 1 ? "" : "s"} and ${n.scenes} scene${n.scenes === 1 ? "" : "s"}`
        + (n.characters_added ? `, ${n.characters_added} new character${n.characters_added === 1 ? "" : "s"} (cast their voices and images)` : "")
        + (n.songs_missing ? `. ${n.songs_missing} number${n.songs_missing === 1 ? " is" : "s are"} waiting for a song.` : "."));
    });
  };
  const attachSong = async (it: ShowItem) => {
    const f = await open({ filters: [{ name: "Song", extensions: AUDIO }] });
    if (typeof f === "string") await act("attach", () => api.show("attach_song", dir, { item: it.id, song: f }));
  };
  const exportShow = (actIndex?: number) => act("export", async () => {
    const r = await api.show<{ path: string; items: number; duration: number; subtitles?: string | null; chapters?: string | null; cues?: number; embedded?: boolean; embed_error?: string }>(
      "export", dir, { ...(actIndex === undefined ? {} : { act: actIndex }), subtitles: subs, chapters: subs });
    setNote(`Exported ${r.items} items (${mins(r.duration)}).` + (r.subtitles || r.chapters
      ? ` Also wrote ${[r.subtitles && `subtitles (${r.cues} lines)`, r.chapters && "chapters"].filter(Boolean).join(" and ")}${r.embedded ? ", built into the film" : r.embed_error ? ` (could not build them into the film: ${r.embed_error})` : ""}.` : ""));
    await revealItemInDir(r.path).catch(() => {});
  });
  const overnight = useShowOvernight(dir, st ? st.acts.flatMap((a) => a.items) : [], load, () => exportShow(), setNote);

  if (!st) return <div className="show-page"><p className="dim">{err || "Opening the show…"}</p></div>;
  const all = st.acts.flatMap((a) => a.items);
  const noVoice = Array.from(new Set(st.characters)).filter((c) => !st.voices[c]);

  return (
    <div className="show-page">
      <header className="show-head">
        <button className="icon-btn" onClick={onHome} title="Home" aria-label="Home"><I.Home /></button>
        <div className="show-title">
          <input className="show-name" defaultValue={st.title} aria-label="Show title"
                 onBlur={(e) => e.target.value.trim() && e.target.value !== st.title && act("rename", () => api.show("rename", dir, { title: e.target.value }))} />
          <span className="dim num">{all.length} item{all.length === 1 ? "" : "s"} · {mins(st.duration)}</span>
        </div>
        <div className="show-actions">
          <button className="btn ghost" disabled={!!busy} onClick={chooseScript} title="Build acts, numbers and scenes from a script">Import script…</button>
          <button className="btn ghost" onClick={() => setCastOpen(true)} title="Characters, places and props shared by every number and scene">Cast &amp; Bible</button>
          <button className="btn ghost" onClick={() => setVoicesOpen(true)}>Voices{noVoice.length ? ` (${noVoice.length} to cast)` : ""}</button>
          <button className={`btn ghost${st.budget.over ? " over" : st.budget.near ? " near" : ""}`} onClick={() => setBudgetOpen(true)}
                  title="Spending so far across the whole show, and the cap">{st.budget.cap_usd ? `$${st.budget.spent_usd.toFixed(0)} of $${st.budget.cap_usd.toFixed(0)}` : `$${st.budget.spent_usd.toFixed(2)} spent`}</button>
          {overnight.night
            ? <button className="btn ghost" onClick={overnight.halt} title={overnight.night.msg}>Stop overnight · {overnight.night.msg}</button>
            : <button className="btn ghost" disabled={!!busy || !all.length} onClick={overnight.start} title="Render every directed number and scene on your ComfyUI, one after another, then export the show">Render overnight</button>}
          <label className="dim" style={{ display: "flex", gap: 6, alignItems: "center" }} title="Write subtitles (spoken lines and lyrics) and chapters next to the film and build them into it">
            <input type="checkbox" checked={subs} onChange={(e) => setSubs(e.target.checked)} /> Subtitles &amp; chapters</label>
          <button className="btn primary" disabled={!!busy || !!overnight.night || !all.length} onClick={() => exportShow()}>{busy === "export" ? "Exporting…" : "Export the show"}</button>
        </div>
      </header>
      {(progress || note || err) && <p className={err ? "error-text" : "dim"} role={err ? "alert" : "status"}>{err || progress || note}</p>}

      {st.acts.map((a) => (
        <section key={a.index} className="show-act">
          <div className="show-act-head">
            <input className="show-act-name" defaultValue={a.name} aria-label={`Name of ${a.name}`}
                   onBlur={(e) => e.target.value.trim() && e.target.value !== a.name && act("rename", () => api.show("rename", dir, { title: e.target.value, act: a.index }))} />
            <span className="dim num">{mins(a.items.reduce((t, i) => t + i.duration, 0))}</span>
            <div style={{ flex: 1 }} />
            {st.characters.length > 0 && <button className="link" disabled={!!busy} onClick={() => setCostumeAct(a.index)}
                    title="Change what a character wears in this act">Costumes{Object.keys(a.costumes).length ? ` (${Object.keys(a.costumes).length})` : ""}</button>}
            {a.items.length > 0 && <button className="link" disabled={!!busy} onClick={() => exportShow(a.index)}>Export this act</button>}
            {a.items.length === 0 && st.acts.length > 1 && <button className="link" disabled={!!busy} onClick={() => act("act", () => api.show("remove_act", dir, { act: a.index }))}>Remove this empty act</button>}
          </div>
          <ol className="show-items">
            {a.items.map((it) => {
              const k = all.findIndex((x) => x.id === it.id);
              const needsDialogue = it.kind === "scene" && (!it.has_audio || it.lines === 0);
              return (
                <li key={it.id} className={`show-item ${it.kind}`}>
                  <div className="si-kind" aria-hidden>{it.kind === "number" ? "♪" : it.kind === "scene" ? "”" : "▭"}</div>
                  <div className="si-main">
                    <b>{it.title}</b>
                    <span className="dim num">
                      {it.kind === "number" ? "Number" : it.kind === "scene" ? `Spoken scene · ${it.lines} line${it.lines === 1 ? "" : "s"}` : `Intermission${it.subtitle ? ` · ${it.subtitle}` : ""}`}
                      {it.ambience ? " · with sound under it" : ""}
                      {it.duration ? ` · ${it.kind === "intermission" ? `${Math.round(it.duration)} s` : fmtTime(it.duration)}` : ""}
                      {it.kind === "intermission" ? "" : it.shots ? ` · ${it.rendered}/${it.shots} shots rendered` : it.analysed ? " · not directed yet" : needsDialogue ? "" : " · not analysed yet"}
                      {it.cost.usd || it.cost.kie_credits ? ` · spent ${it.cost.usd ? `$${it.cost.usd.toFixed(2)}` : ""}${it.cost.usd && it.cost.kie_credits ? " + " : ""}${it.cost.kie_credits ? `${it.cost.kie_credits} credits` : ""}` : ""}
                    </span>
                    {it.problems.length > 0 && <ul className="si-problems">{it.problems.map((x) => <li key={x}>{x}</li>)}</ul>}
                    <div className="si-progress" aria-hidden><i style={{ width: `${it.shots ? (100 * it.rendered) / it.shots : 0}%` }} /></div>
                  </div>
                  <div className="si-actions">
                    {it.kind === "scene" && <button className="btn sm" onClick={() => setDialogue(it)}>Dialogue</button>}
                    {it.kind === "intermission" && <button className="btn sm" onClick={() => setCard({ act: a.index, item: it })}>Card</button>}
                    {it.kind !== "number" && <button className="btn sm" onClick={() => setAmbience(it)} title="Ambience or music that plays under this item">Sound</button>}
                    {it.song_pending && <button className="btn sm" disabled={!!busy} onClick={() => attachSong(it)}>Attach song…</button>}
                    {it.kind !== "intermission" && <button className="btn sm primary" disabled={needsDialogue || it.song_pending} title={needsDialogue ? "Write and voice the dialogue first" : it.song_pending ? "Attach its song first" : undefined}
                            onClick={() => onOpenItem(it.path)}>Open</button>}
                    <button className="icon-btn" disabled={!!busy || k === 0} aria-label={`Move ${it.title} earlier`} onClick={() => act("move", () => api.show("move", dir, { item: it.id, delta: -1 }))}>↑</button>
                    <button className="icon-btn" disabled={!!busy || k === all.length - 1} aria-label={`Move ${it.title} later`} onClick={() => act("move", () => api.show("move", dir, { item: it.id, delta: 1 }))}>↓</button>
                    {st.acts.length > 1 && <select value={a.index} aria-label={`Act for ${it.title}`} onChange={(e) => act("act", () => api.show("set_act", dir, { item: it.id, act: Number(e.target.value) }))}>
                      {st.acts.map((x) => <option key={x.index} value={x.index}>{x.name}</option>)}</select>}
                    <button className="icon-btn" aria-label={`Remove ${it.title}`} title="Remove from the show (its folder is kept)"
                            onClick={async () => await ask(`Remove "${it.title}" from the show? Its folder is kept in the show's "removed" folder.`) && act("remove", () => api.show("remove", dir, { item: it.id }))}>
                      <I.Close size={14} /></button>
                  </div>
                  {k < all.length - 1 && <label className="si-transition">
                    <span className="dim">then</span>
                    <select value={it.transition} disabled={!!busy} onChange={(e) => act("transition", () => api.show("transition", dir, { item: it.id, kind: e.target.value }))}>
                      {Object.entries(TRANSITION).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </label>}
                </li>
              );
            })}
          </ol>
          <div className="show-add">
            <button className="btn ghost sm" disabled={!!busy} onClick={() => chooseSong(a.index)}>+ Song</button>
            <button className="btn ghost sm" disabled={!!busy} onClick={() => setMaking(a.index)} title="Compose a song with ElevenLabs Music (optional)">+ Make a song…</button>
            <button className="btn ghost sm" disabled={!!busy} onClick={() => setAdding({ kind: "scene", title: "", setting: "", act: a.index })}>+ Spoken scene</button>
            <button className="btn ghost sm" disabled={!!busy} onClick={() => addExisting(a.index)}>+ Existing project…</button>
            <button className="btn ghost sm" disabled={!!busy} onClick={() => setCard({ act: a.index })}>+ Intermission</button>
          </div>
        </section>
      ))}
      <button className="btn ghost" disabled={!!busy} onClick={() => act("act", () => api.show("add_act", dir, {}))}>+ Add an act</button>

      {making !== null && <SongMaker onClose={() => setMaking(null)}
        onUse={(s) => { const a = making; setMaking(null);
          act("add", () => api.show("add_number", dir, { song: s.path, title: s.title, lyrics: s.lyrics || undefined, act: a })); }} />}
      {adding && <div className="overlay" onClick={() => setAdding(null)}>
        <form className="sheet glass" onClick={(e) => e.stopPropagation()} style={{ width: "min(520px, calc(100vw - 48px))" }}
              onSubmit={(e) => { e.preventDefault(); const x = adding; setAdding(null);
                act("add", () => x.kind === "number" ? api.show("add_number", dir, { song: x.song, title: x.title.trim() || "Untitled", act: x.act })
                  : api.show("add_scene", dir, { title: x.title.trim() || "Scene", setting: x.setting, act: x.act })); }}>
          <h2>{adding.kind === "number" ? "Add a song" : "Add a spoken scene"}</h2>
          {adding.song && <p className="dim">{adding.song.split(/[\\/]/).pop()}</p>}
          <label className="field"><span>Title</span><input className="text-input" autoFocus value={adding.title} onChange={(e) => setAdding({ ...adding, title: e.target.value })} /></label>
          {adding.kind === "scene" && <label className="field"><span>Where and when (optional)</span>
            <textarea className="text-input" rows={2} value={adding.setting} placeholder="e.g. A rooftop at dusk, after the market closes"
                      onChange={(e) => setAdding({ ...adding, setting: e.target.value })} /></label>}
          <div className="sheet-actions"><button type="button" className="btn ghost" onClick={() => setAdding(null)}>Cancel</button>
            <button className="btn primary" type="submit">Add</button></div>
        </form>
      </div>}
      {script && <div className="overlay" onClick={() => setScript(null)}>
        <div className="sheet glass" onClick={(e) => e.stopPropagation()} style={{ width: "min(620px, calc(100vw - 48px))", maxHeight: "80vh", overflow: "auto" }}>
          <h2>Import a script</h2>
          <p className="dim">{script.file.split(/[\\/]/).pop()}</p>
          {script.err && <p className="error-text" role="alert">{script.err}</p>}
          {!script.plan && !script.err && <p className="dim">Reading the script…</p>}
          {script.plan && <>
            <p><b>{script.plan.totals.acts}</b> act{script.plan.totals.acts === 1 ? "" : "s"}, <b>{script.plan.totals.numbers}</b> number{script.plan.totals.numbers === 1 ? "" : "s"},
              {" "}<b>{script.plan.totals.scenes}</b> spoken scene{script.plan.totals.scenes === 1 ? "" : "s"}, <b>{script.plan.totals.lines}</b> line{script.plan.totals.lines === 1 ? "" : "s"} of dialogue.
              {script.plan.characters.length > 0 && <> Characters: {script.plan.characters.join(", ")}.</>}</p>
            {script.plan.acts.map((a, i) => <div key={i}><b>{a.name}</b>
              <ul className="script-items">{a.items.map((it, k) => <li key={k}>{it.kind === "number" ? "♪" : "”"} {it.title}
                {it.kind === "number" && <span className="dim"> {it.song ? `· song: ${it.song.split(/[\\/]/).pop()}` : "· needs a song"}</span>}</li>)}</ul></div>)}
            {script.plan.warnings.map((w) => <p key={w} className="si-problems"><span>{w}</span></p>)}
            {script.plan.format === "screenplay" && <label className="dim" style={{ display: "flex", gap: 6, alignItems: "center", margin: "6px 0" }}
                   title="Put all the music into one number, for a single recorded song that holds every verse and chorus">
              <input type="checkbox" checked={!!script.one} onChange={(e) => previewScript(script.file, script.songs, e.target.checked)} /> My music is one recorded song</label>}
            <p className="dim">Songs are not in a script. Pick a folder of recorded songs to match them by name, or attach each song afterwards. Nothing already in the show is changed.</p>
          </>}
          <div className="sheet-actions">
            <button className="btn ghost" onClick={() => setScript(null)}>Cancel</button>
            <button className="btn ghost" onClick={chooseSongsFolder} disabled={!script.plan}>{script.songs ? "Change songs folder…" : "Match songs from a folder…"}</button>
            <button className="btn primary" disabled={!script.plan} onClick={importScript}>Import</button>
          </div>
        </div>
      </div>}
      {costumeAct !== null && st.acts[costumeAct] && <CostumeSheet dir={dir} act={st.acts[costumeAct]} characters={Array.from(new Set(st.characters))}
                                                                 onClose={() => { setCostumeAct(null); load(); }} />}
      {card && <CardSheet dir={dir} act={card.act} item={card.item} onClose={(changed) => { setCard(null); if (changed) load(); }} />}
      {ambience && <AmbienceSheet dir={dir} item={ambience} onClose={() => { setAmbience(null); load(); }} />}
      {budgetOpen && <BudgetSheet dir={dir} budget={st.budget} onClose={() => { setBudgetOpen(false); load(); }} />}
      {castOpen && <LibrarySheet dir={st.cast_dir} scenes={[]} onClose={() => { setCastOpen(false); act("sync", () => api.show("sync", dir, {})); }} onChanged={() => {}} />}
      {voicesOpen && <VoicesSheet show={dir} characters={st.characters} onClose={() => { setVoicesOpen(false); load(); }} />}
      {dialogue && <DialogueEditor item={dialogue} characters={st.characters} voices={st.voices}
                                   onVoices={() => setVoicesOpen(true)} onClose={() => { setDialogue(null); load(); }}
                                   onOpen={(p) => { setDialogue(null); onOpenItem(p); }} />}
    </div>
  );
}

/** The show folder an item belongs to (items live in <show>/items/<item>), or null for a path that can't be one. */
export function showDirOf(dir: string): string | null {
  const parts = dir.replace(/[\\/]+$/, "").split(/[\\/]/);
  if (parts.length < 3 || parts[parts.length - 2].toLowerCase() !== "items") return null;
  const sep = dir.includes("\\") ? "\\" : "/";
  return parts.slice(0, -2).join(sep);
}

/** What each character wears in one act: an image and a note that stand in for the cast image in every item of the act. */
function CostumeSheet({ dir, act, characters, onClose }: { dir: string; act: ShowStatus["acts"][number]; characters: string[]; onClose: () => void }) {
  const [costumes, setCostumes] = useState(act.costumes);
  const [notes, setNotes] = useState<Record<string, string>>(Object.fromEntries(Object.entries(act.costumes).map(([k, v]) => [k, v.note ?? ""])));
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const call = async (who: string, data: Record<string, unknown>) => {
    setBusy(who); setErr("");
    try { const r = await api.show("set_costume", dir, { act: act.index, character: who, ...data }); setCostumes(r.acts[act.index].costumes); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const pick = async (who: string) => {
    const f = await open({ filters: [{ name: "Costume image", extensions: IMAGE }] });
    if (typeof f === "string") await call(who, { image: f, note: notes[who] ?? "" });
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass" onClick={(e) => e.stopPropagation()} style={{ width: "min(620px, calc(100vw - 48px))", maxHeight: "80vh", overflow: "auto" }}>
        <h2>Costumes: {act.name}</h2>
        <p className="dim">A costume replaces the character's cast image, and adds your note, for every number and scene in this act. The cast itself is not changed.</p>
        {err && <p className="error-text" role="alert">{err}</p>}
        {characters.map((c) => (
          <div key={c} className="costume-row">
            <b>{c}</b>
            <input className="text-input" value={notes[c] ?? ""} placeholder="e.g. a blue ball gown, hair up" aria-label={`Costume note for ${c}`}
                   onChange={(e) => setNotes({ ...notes, [c]: e.target.value })} />
            <button className="btn sm" disabled={!!busy} onClick={() => pick(c)}>{costumes[c]?.file ? "Change image…" : "Choose image…"}</button>
            <button className="btn sm" disabled={!!busy || (!(notes[c] ?? "").trim() && !costumes[c]?.file)} onClick={() => call(c, { note: notes[c] ?? "" })}>Save note</button>
            {costumes[c] && <button className="btn sm ghost" disabled={!!busy} onClick={() => { setNotes({ ...notes, [c]: "" }); call(c, { clear: true }); }}>Remove</button>}
          </div>
        ))}
        <div className="sheet-actions"><button className="btn primary" onClick={onClose}>Done</button></div>
      </div>
    </div>
  );
}
