import { useCallback, useEffect, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { api, errorText, type CatalogItem, type ComposeModels, type ComposeState, type Job, type KeyStatus, type MotionClip, type TakePrompt } from "./api";
import { PromptPanel, promptOverrides } from "./PromptPanel";
import { ask } from "./ask";
import { ConfirmRender } from "./Render";
import { FramesStage, type ModelPick } from "./Frames";
import { ModelPicker } from "./ModelPicker";
import * as I from "./icons";

/** Three ways to make a shot, one screen: two pictures it moves between, pictures it takes its people and places from, or a video of the movement that your character performs. */
export type Mode = "frames" | "refs" | "motion";
export const MODES: { id: Mode; label: string; blurb: string }[] = [
  { id: "frames", label: "Start → End", blurb: "Two pictures: the model animates from the first to the last. The most control over where a shot begins and lands." },
  { id: "refs", label: "References", blurb: "Pictures of your people, places and things; the model invents the opening and keeps them looking like themselves." },
  { id: "motion", label: "Motion", blurb: "A video of a movement (a dance, a walk, a performance) and a picture of your character: the character does the movement." },
];
const MODE_KEY = "pf-compose-mode";
const storedMode = (): Mode => { try { const m = localStorage.getItem(MODE_KEY); return MODES.some((x) => x.id === m) ? (m as Mode) : "frames"; } catch { return "frames"; } };

/** What a motion take still needs, in the order the screen asks for it. Pure. */
export function motionStep(s: Pick<ComposeState, "video" | "image">): { step: "video" | "image" | "ready"; text: string } {
  if (!s.video) return { step: "video", text: "Choose the motion video: 3 to 30 seconds of someone doing the movement, with their head, shoulders and body in view." };
  if (!s.image) return { step: "image", text: "Choose the character picture, or make this shot's keyframe first." };
  return { step: "ready", text: "Both are set. The character in the picture will perform the movement in the video." };
}
export const secs = (n: number | null | undefined) => (n == null ? "" : `${Math.round(n * 10) / 10} s`);
const toPick = (c: CatalogItem | undefined, fallbackProvider: string): ModelPick | null => (c ? { provider: c.provider || fallbackProvider, model: c.model, label: c.title.split(" · ").slice(-1)[0] } : null);

/** The model and one line of direction, shared by the three ways. */
function Settings({ catalog, value, onModel, note, onNote, label }: { catalog: CatalogItem[]; value: string; onModel: (m: string) => void; note?: string; onNote?: (t: string) => void; label: string }) {
  return (
    <div className="cp-settings">
      {catalog.length > 0 ? <ModelPicker catalog={catalog} value={value} onChange={onModel} label={label} id="cp-model" />
        : <p className="dim">The model list isn't loaded yet; the shot's usual video model is used.</p>}
      {onNote && <>
        <label className="fr-label" htmlFor="cp-note">Direction for this take <span className="dim">(optional: one line, added to the prompt)</span></label>
        <textarea id="cp-note" className="text-input" rows={2} maxLength={600} value={note ?? ""} onChange={(e) => onNote(e.target.value)} placeholder="e.g. a slow push in; she never looks at the camera" /></>}
    </div>
  );
}

/** Pure: how a saved motion is described under its picture. */
export function clipLine(c: Pick<MotionClip, "seconds" | "width" | "height">): string {
  return [c.seconds != null ? secs(c.seconds) : "", c.width && c.height ? `${c.width}×${c.height}` : ""].filter(Boolean).join(" · ");
}

/** Pure: the saved motions that match what was typed (in the name or a tag) and the chosen tag. */
export function filterClips(clips: MotionClip[], query: string, tag: string | null): MotionClip[] {
  const q = query.trim().toLowerCase();
  return clips.filter((c) => (!tag || (c.tags ?? []).includes(tag)) && (!q || c.name.toLowerCase().includes(q) || (c.tags ?? []).some((t) => t.includes(q))));
}

/** Pure: every tag in use with how many motions carry it, most used first. */
export function tagCounts(clips: MotionClip[]): [string, number][] {
  const n = new Map<string, number>();
  for (const c of clips) for (const t of c.tags ?? []) n.set(t, (n.get(t) ?? 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** Pure: "walk, slow, , Dance" as ["walk", "slow", "dance"] (the engine applies the same limits). */
export function parseTags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) { const t = raw.replace(/\s+/g, " ").trim().toLowerCase().slice(0, 24).trim(); if (t && !out.includes(t)) out.push(t); }
  return out.slice(0, 8);
}

/** Motions you want to use more than once, kept on this computer for every project. Use one on this shot, save the shot's own, rename, remove. */
function MotionLibrary({ dir, shot, hasVideo, onUsed, busy }: { dir: string; shot: string; hasVideo: boolean; onUsed: (s: ComposeState) => void; busy: boolean }) {
  const [clips, setClips] = useState<MotionClip[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [work, setWork] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [tagging, setTagging] = useState<string | null>(null);
  const [tagText, setTagText] = useState("");
  const [removed, setRemoved] = useState<MotionClip | null>(null);       // the motion just removed, until something else happens: Remove can be undone
  const [peek, setPeek] = useState<string | null>(null);              // the motion whose picture is playing (pointer over it or keyboard focus)
  useEffect(() => { api.compose<MotionClip[]>(dir, "library_list").then((c) => { setClips(c); if (c.length && !hasVideo) setIsOpen(true); }).catch((e) => { setClips([]); setErr(errorText(e)); }); }, [dir]);
  const run = async (fn: () => Promise<void>) => { setWork(true); setErr(""); setNote(""); setRemoved(null); try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setWork(false); } };
  const refresh = async () => setClips(await api.compose<MotionClip[]>(dir, "library_list"));
  const add = () => run(async () => {
    const p = await open({ filters: [{ name: "Video", extensions: ["mp4", "mov"] }] });
    if (typeof p !== "string") return;
    const c = await api.compose<MotionClip>(dir, "library_add", { path: p });
    setNote(c.already ? `That video is already in the library as “${c.name}”.` : `Saved “${c.name}”.`); await refresh();
  });
  const saveShot = () => run(async () => { const c = await api.compose<MotionClip>(dir, "library_add", { shot }); setNote(c.already ? `Already in the library as “${c.name}”.` : `Saved “${c.name}” to the library.`); await refresh(); });
  const exportAll = () => run(async () => {
    const p = await save({ defaultPath: "FilmCrafter motion library.zip", filters: [{ name: "Motion library", extensions: ["zip"] }] });
    if (typeof p !== "string") return;
    const r = await api.compose<{ count: number }>(dir, "library_export", { path: p });
    setNote(`Saved ${r.count} motion${r.count === 1 ? "" : "s"} to the file.`);
  });
  const importPack = () => run(async () => {
    const p = await open({ filters: [{ name: "Motion library", extensions: ["zip"] }] });
    if (typeof p !== "string") return;
    const r = await api.compose<{ added: number; skipped: number; refused: number; items: MotionClip[] }>(dir, "library_import", { path: p });
    setClips(r.items);
    setNote(`Added ${r.added}. ${r.skipped ? `${r.skipped} already here. ` : ""}${r.refused ? `${r.refused} could not be used (not a valid motion video).` : ""}`.trim());
  });
  const saveTags = (id: string) => run(async () => { setClips(await api.compose<MotionClip[]>(dir, "library_tag", { id, tags: parseTags(tagText) })); setTagging(null); });
  const shown = filterClips(clips ?? [], query, tag);
  const tags = tagCounts(clips ?? []);
  const use = (id: string) => run(async () => onUsed(await api.compose<ComposeState>(dir, "library_use", { shot, id })));
  const rename = (id: string) => run(async () => { setClips(await api.compose<MotionClip[]>(dir, "library_rename", { id, name })); setEditing(null); });
  const remove = (c: MotionClip) => run(async () => { if (await ask(`Remove “${c.name}” from the library? Shots that already use it keep their own copy. You can undo this right after.`)) { setClips(await api.compose<MotionClip[]>(dir, "library_remove", { id: c.id })); setRemoved(c); } });
  const restore = () => run(async () => { if (!removed) return; setClips(await api.compose<MotionClip[]>(dir, "library_restore", { id: removed.id })); setNote(`Brought back “${removed.name}”.`); setRemoved(null); });
  return (
    <details className="cp-lib" open={isOpen} onToggle={(e) => setIsOpen((e.target as HTMLDetailsElement).open)}>
      <summary>My motion library{clips ? ` (${clips.length})` : ""}</summary>
      <p className="dim">Motions you use again and again, kept on this computer for every project. Choosing one copies it into this shot.</p>
      <div className="cp-lib-bar">
        <button className="btn ghost small" disabled={work || busy} onClick={add}>Add a video to the library…</button>
        {hasVideo && <button className="btn ghost small" disabled={work || busy} onClick={saveShot}>Save this shot's motion to the library</button>}
        <button className="btn ghost small" disabled={work || !clips?.length} onClick={exportAll} title="Save every motion, with its name and tags, in one file to take to another computer">Export the library…</button>
        <button className="btn ghost small" disabled={work || busy} onClick={importPack} title="Add the motions from a library file saved on another computer">Import a library…</button>
      </div>
      {clips && clips.length > 0 && <div className="cp-lib-find">
        <input className="text-input" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a motion by name or tag" aria-label="Find a motion" maxLength={60} />
        {tags.length > 0 && <div className="cp-tags" role="group" aria-label="Filter by tag">
          {tags.map(([t, n]) => <button key={t} className={`cp-tag ${tag === t ? "on" : ""}`} aria-pressed={tag === t} onClick={() => setTag(tag === t ? null : t)}>{t} <span className="dim">{n}</span></button>)}
        </div>}
      </div>}
      {clips && clips.length === 0 && <p className="dim">Nothing saved yet.</p>}
      {clips && clips.length > 0 && shown.length === 0 && <p className="dim">No motion matches. <button className="link" onClick={() => { setQuery(""); setTag(null); }}>Show all</button></p>}
      <ul className="cp-clips">
        {shown.map((c) => (
          <li key={c.id}>
            <div className="cp-clip-img" onPointerEnter={() => setPeek(c.id)} onPointerLeave={() => setPeek(null)} onFocus={() => setPeek(c.id)} onBlur={() => setPeek(null)} tabIndex={c.path ? 0 : undefined} aria-label={c.path ? `Preview ${c.name}` : undefined}>
              {peek === c.id && c.path ? <video src={api.mediaUrl(c.path)} muted loop autoPlay playsInline preload="metadata" />
                : c.thumb ? <img src={c.thumb} alt="" /> : <span className="dim">no picture</span>}</div>
            {editing === c.id
              ? <input className="text-input" autoFocus value={name} maxLength={60} aria-label="Name" onChange={(e) => setName(e.target.value)} onBlur={() => rename(c.id)} onKeyDown={(e) => { if (e.key === "Enter") rename(c.id); if (e.key === "Escape") setEditing(null); }} />
              : <button className="link cp-clip-name" title="Rename" onClick={() => { setEditing(c.id); setName(c.name); }}>{c.name}</button>}
            <span className="dim">{clipLine(c)}</span>
            {tagging === c.id
              ? <input className="text-input" autoFocus value={tagText} maxLength={200} aria-label="Tags, separated by commas" placeholder="walk, slow, dance" onChange={(e) => setTagText(e.target.value)} onBlur={() => saveTags(c.id)} onKeyDown={(e) => { if (e.key === "Enter") saveTags(c.id); if (e.key === "Escape") setTagging(null); }} />
              : <button className="link cp-clip-tags" title="Edit tags" onClick={() => { setTagging(c.id); setTagText((c.tags ?? []).join(", ")); }}>{(c.tags ?? []).length ? (c.tags ?? []).map((t) => `#${t}`).join(" ") : "Add tags"}</button>}
            <div className="cp-clip-actions"><button className="btn small" disabled={work || busy} onClick={() => use(c.id)}>Use for this shot</button>
              <button className="btn ghost small" disabled={work} onClick={() => remove(c)} aria-label={`Remove ${c.name}`}>Remove</button></div>
          </li>))}
      </ul>
      {removed && <p className="status-ok" role="status">Removed “{removed.name}”. <button className="link" disabled={work} onClick={restore}>Undo</button></p>}
      {note && <p className="status-ok" role="status">{note}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </details>
  );
}

function MotionMode({ dir, shot, provider, catalog, model, onModel, note, onNote, onQueued, onChanged }: {
  dir: string; shot: string; provider: string; catalog: CatalogItem[]; model: string; onModel: (m: string) => void; note: string; onNote: (t: string) => void;
  onQueued?: (j: Job[]) => void; onChanged?: () => void;
}) {
  const [s, setS] = useState<ComposeState | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.compose<ComposeState>(dir, "state", { shot }).then(setS).catch((e) => setErr(errorText(e))), [dir, shot]);
  useEffect(() => { setS(null); load(); }, [load]);
  const set = async (data: Record<string, unknown>, label = "…") => {
    setBusy(label); setErr("");
    try { setS(await api.compose<ComposeState>(dir, "set_motion", { shot, ...data })); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const pickVideo = async () => { const p = await open({ filters: [{ name: "Video", extensions: ["mp4", "mov"] }] }); if (typeof p === "string") await set({ video_path: p }, "Checking the video…"); };
  const pickImage = async () => { const p = await open({ filters: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "webp"] }] }); if (typeof p === "string") await set({ image_path: p }, "Adding the picture…"); };
  if (!s) return <div className="dim">{err || "Loading…"}</div>;
  const step = motionStep(s);
  const chosen = catalog.find((c) => c.model === model) ?? catalog[0];
  const render = async () => {
    if (!chosen) { setErr("No motion model is available. Add a Kie.ai key in Settings, then reopen this tab."); return; }
    const ok = await ask(`Make a motion take for ${shot} on ${chosen.title.split(" · ").slice(-1)[0]}.\n\nThe character in your picture will perform the movement in your ${secs(s.video_seconds)} video, in ${s.quality === "pro" ? "high" : "standard"} quality.\nIt is charged in ${provider === "kie" ? "Kie credits" : "provider credits"}; the exact price is shown on the take afterwards. Start?`);
    if (!ok) return;
    setBusy("Queuing…"); setErr("");
    try { if (note.trim() !== s.note) await api.compose(dir, "set_motion", { shot, note: note.trim() }); onQueued?.(await api.compose<Job[]>(dir, "queue_motion", { shot, provider: chosen.provider || provider, model: chosen.model })); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  return (
    <div className="cp-motion">
      <ol className="fr-steps" aria-label="Steps">
        {(["video", "image", "ready"] as const).map((k, i) => { const at = ["video", "image", "ready"].indexOf(step.step); return (
          <li key={k} className={step.step === k ? "now" : at > i ? "done" : ""}><i>{at > i ? <I.Check size={11} /> : i + 1}</i>{k === "video" ? "Motion video" : k === "image" ? "Character" : "Render"}</li>); })}
      </ol>
      <p className="fr-guide" role="status">{step.text}</p>
      <div className="cp-slots">
        <figure className="fr-frame">
          <div className={`fr-img cp-video ${s.video ? "" : "empty"}`}>
            <em className="fr-tag">MOTION</em>
            {s.video ? <video src={api.mediaUrl(`${dir}/${s.video}`)} controls muted loop playsInline /> : <span>A video of the movement</span>}
          </div>
          <figcaption><div className="fr-actions"><button className="btn sm" disabled={!!busy} onClick={pickVideo}>{s.video ? "Change the video…" : "Choose the motion video…"}</button>
            {s.video && <button className="btn ghost sm" disabled={!!busy} onClick={async () => { setS(await api.compose<ComposeState>(dir, "clear_motion", { shot })); }}>Remove</button>}</div>
            {s.video_seconds != null && <span className="dim">{secs(s.video_seconds)} · the shot is {secs(s.shot_seconds)}</span>}</figcaption>
        </figure>
        <div className="fr-arrow" aria-hidden>+</div>
        <figure className="fr-frame">
          <div className={`fr-img ${s.image ? "" : "empty"}`} style={{ backgroundImage: s.image ? `url("${api.mediaUrl(`${dir}/${s.image}`)}")` : undefined }}>
            <em className="fr-tag">CHARACTER</em>{!s.image && <span>Who performs it</span>}
          </div>
          <figcaption><div className="fr-actions"><button className="btn ghost sm" disabled={!!busy} onClick={pickImage}>Use my picture…</button>
            {!s.image_is_start && s.image && <button className="btn ghost sm" disabled={!!busy} onClick={() => set({ image_from_start: true })}>Use the keyframe</button>}</div>
            <span className="dim">{s.image_is_start ? "This shot's keyframe" : s.image ? "Your picture" : "Make a keyframe, or bring a picture"}</span></figcaption>
        </figure>
      </div>
      <MotionLibrary dir={dir} shot={shot} hasVideo={!!s.video} busy={!!busy} onUsed={(st) => { setS(st); onChanged?.(); }} />
      <div className="cp-options">
        <label>Facing<select value={s.orientation} disabled={!!busy} onChange={(e) => set({ orientation: e.target.value })} aria-label="Facing">
          <option value="video">Follow the video (best for dance and action)</option><option value="image">Follow the picture</option></select></label>
        <label>Quality<select value={s.quality} disabled={!!busy} onChange={(e) => set({ quality: e.target.value })} aria-label="Quality">
          <option value="pro">High (1080p)</option><option value="std">Standard (720p, cheaper)</option></select></label>
        <label>Background<select value={s.background} disabled={!!busy} onChange={(e) => set({ background: e.target.value })} aria-label="Background">
          <option value="video">From the motion video</option><option value="image">From the character picture</option></select></label>
      </div>
      <Settings catalog={catalog} value={chosen?.model ?? ""} onModel={onModel} note={note} onNote={onNote} label="Motion model" />
      {s.notes.map((n) => <p key={n} className="fr-note warn"><I.Alert size={13} /> {n}</p>)}
      {err && <p className="error-text" role="alert">{err}</p>}
      <div className="fr-cta"><button className="btn primary" disabled={!s.ready || !!busy || !chosen} onClick={render}>Render motion take</button>
        {busy ? <span className="dim"><span className="spin sm" /> {busy}</span> : !s.ready ? <span className="dim">Still needed: {s.missing.join(" and ")}.</span> : null}</div>
    </div>
  );
}

function RefsMode({ dir, shot, provider, catalog, model, onModel, take, promptPanel, refsPanel, onQueued }: {
  dir: string; shot: string; provider: string; catalog: CatalogItem[]; model: string; onModel: (m: string) => void; take: Record<string, unknown>; promptPanel: React.ReactNode;
  refsPanel?: React.ReactNode; onQueued?: (j: Job[]) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState("");
  const chosen = catalog.find((c) => c.model === model) ?? catalog[0];
  const render = async () => {
    setConfirm(false); setErr("");
    try { const jobs = await api.queueRender(dir, [shot], chosen?.provider || provider, chosen?.model ?? null, { _refs_only: true, ...take }, []); await api.ensureRenderer(dir); onQueued?.(jobs); }
    catch (e) { setErr(errorText(e)); }
  };
  return (
    <div className="cp-refs">
      <p className="fr-guide">Pictures of the people, places and things in this shot go to the model as references. There is no start frame, so the model invents the opening while keeping them looking like themselves.</p>
      {refsPanel}
      <Settings catalog={catalog} value={chosen?.model ?? ""} onModel={onModel} label="Reference model" />
      {promptPanel}
      {err && <p className="error-text" role="alert">{err}</p>}
      <div className="fr-cta"><button className="btn primary" disabled={!chosen} onClick={() => setConfirm(true)}>Render from references</button></div>
      {confirm && chosen && <ConfirmRender count={1} seconds={0} provider={chosen.provider || provider} model={`${chosen.title.split(" · ").slice(-1)[0]}, from reference pictures with no start frame`}
        onCancel={() => setConfirm(false)} onConfirm={render} dir={dir} shots={[shot]} modelId={chosen.model} />}
    </div>
  );
}

/** The inspector's Compose tab. */
export function ComposeTab({ dir, shot, keys, refsPanel, onChanged, onQueued, onOpenKeyframe }: {
  dir: string; shot: string; keys: KeyStatus; refsPanel?: React.ReactNode; onChanged?: () => void; onQueued?: (jobs: Job[]) => void; onOpenKeyframe?: () => void;
}) {
  const [mode, setModeState] = useState<Mode>(storedMode);
  const setMode = (m: Mode) => { setModeState(m); try { localStorage.setItem(MODE_KEY, m); } catch { /* a convenience only */ } };
  const provider = keys.kie ? "kie" : keys.fal ? "fal" : "kie";
  const [models, setModels] = useState<ComposeModels | null>(null);
  const [chosen, setChosen] = useState<Record<Mode, string>>({ frames: "", refs: "", motion: "" });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const note = notes[shot] ?? "";
  const [prompts, setPrompts] = useState<Record<string, TakePrompt>>({});
  const prompt: TakePrompt = prompts[shot] ?? { mode: "auto", text: "", only: false };
  useEffect(() => { api.compose<ComposeState>(dir, "state", { shot }).then((s) => setPrompts((p) => ({ ...p, [shot]: s.prompt }))).catch(() => {}); }, [dir, shot]);
  useEffect(() => { api.compose<ComposeModels>(dir, "models", { provider }).then(setModels).catch(() => setModels({ start_end: [], references: [], motion: [] })); }, [dir, provider]);
  const list = (m: Mode) => (models ? (m === "frames" ? models.start_end : m === "refs" ? models.references : models.motion) : []);
  const set = (m: Mode) => (v: string) => setChosen((c) => ({ ...c, [m]: v }));
  const info = MODES.find((m) => m.id === mode)!;
  const pickFrames = toPick(list("frames").find((c) => c.model === chosen.frames), provider);
  const modelFor = (m: Mode) => chosen[m] || list(m)[0]?.model || "";
  const setNote = (t: string) => setNotes((n) => ({ ...n, [shot]: t }));
  const panel = (m: Mode) => <PromptPanel dir={dir} shot={shot} provider={provider} model={modelFor(m)} prompt={prompt} onPrompt={(p) => setPrompts((all) => ({ ...all, [shot]: p }))} direction={note} onDirection={setNote} frames={m === "frames"} />;
  const take = promptOverrides(prompt, note);
  return (
    <div className="compose">
      <div className="cp-modes" role="tablist" aria-label="How to make this shot">
        {MODES.map((m) => <button key={m.id} role="tab" aria-selected={mode === m.id} className={mode === m.id ? "on" : ""} onClick={() => setMode(m.id)}>{m.label}</button>)}
      </div>
      <p className="dim cp-blurb">{info.blurb}</p>
      {mode === "frames" && <FramesStage dir={dir} shot={shot} hasKey={!!(keys.fal || keys.kie || keys.google)} onChanged={onChanged} onQueued={onQueued} onOpenKeyframe={onOpenKeyframe} pick={pickFrames} overrides={take}>
        <Settings catalog={list("frames")} value={chosen.frames || (pickFrames?.model ?? "")} onModel={set("frames")} label="Model for start and end" />
        {panel("frames")}
      </FramesStage>}
      {mode === "refs" && <RefsMode dir={dir} shot={shot} provider={provider} catalog={list("refs")} model={chosen.refs} onModel={set("refs")} take={take} promptPanel={panel("refs")} refsPanel={refsPanel} onQueued={onQueued} />}
      {mode === "motion" && <MotionMode dir={dir} shot={shot} provider={provider} catalog={list("motion")} model={chosen.motion} onModel={set("motion")} note={note} onNote={setNote} onQueued={onQueued} onChanged={onChanged} />}
    </div>
  );
}
