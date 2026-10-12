import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { TakeCompare } from "./Compare";
import { RefGenSheet } from "./RefGen";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { api, errorText, fmtTime, type Board, type BoardShot, type Job, type Library, type RefItem, type RefKind, type ShotStatus, type Version } from "./api";
import { fill } from "./voiceLogic";
import type { VoiceShot } from "./api";
import * as I from "./icons";
import { FramesPanel } from "./Frames";
import { ask } from "./ask";

/**
 * Storyboard data for the timeline: status, thumbnail source and versions per shot, plus the reference library.
 * Reloaded when jobs change; thumbnails are made on demand (only for visible cards) and cached on disk.
 */
export function useBoard(dir: string, jobs: Job[]) {
  const [board, setBoard] = useState<Board | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const pending = useRef(new Set<string>());
  const reload = useCallback(() => api.storyboard(dir).then(setBoard).catch(() => {}), [dir]);
  const sig = jobs.map((j) => `${j.id}:${j.state}`).join(",");
  useEffect(() => { const t = setTimeout(reload, 300); return () => clearTimeout(t); }, [reload, sig]);
  const want = useCallback((srcs: string[]) => {
    const need = srcs.filter((s) => !(s in thumbs) && !pending.current.has(s));
    if (!need.length) return;
    need.forEach((s) => pending.current.add(s));
    api.thumbs(dir, need).then((r) => setThumbs((t) => ({ ...t, ...r })))
      .catch(() => setThumbs((t) => ({ ...t, ...Object.fromEntries(need.map((s) => [s, null])) })))
      .finally(() => need.forEach((s) => pending.current.delete(s)));
  }, [dir, thumbs]);
  return { board, reload, thumbs, want };
}

export const STATUS: Record<ShotStatus, { label: string; cls: string }> = {
  planned: { label: "Planned", cls: "planned" }, queued: { label: "Queued", cls: "gen" }, generating: { label: "Generating", cls: "gen" },
  ready: { label: "Ready", cls: "ready" }, failed: { label: "Failed", cls: "failed" }, needs_review: { label: "Needs review", cls: "review" },
  locked: { label: "Locked", cls: "locked" },
};

export function StatusChip({ s }: { s: ShotStatus }) {
  const m = STATUS[s];
  const icon = s === "ready" ? <I.Check size={11} /> : s === "locked" ? <I.Lock size={11} /> : s === "failed" || s === "needs_review" ?
    <I.Alert size={11} /> : s === "planned" ? <I.Circle size={11} /> : <span className="spin sm" />;
  return <span className={`chip ${m.cls}`}>{icon} {m.label}</span>;
}

const media = (dir: string, rel: string) => api.mediaUrl(`${dir}/${rel}`);
const isVideo = (p?: string | null) => !!p && /\.(mp4|mov|webm|mkv|m4v)$/i.test(p);

/** Shot cards on the timeline: real thumbnails, status, hover preview, double-click to open. Only visible cards are drawn. */
export function StoryCards({ dir, shots, pps, view, selected, thumbs, want, onSelect, onOpen, voices, onVoice }: {
  dir: string; shots: BoardShot[]; pps: number; view: [number, number]; selected: string | null;
  voices?: Record<string, VoiceShot>; onVoice?: (id: string) => void;                       // a film's own recorded voices: a mic on each card that has someone speaking
  thumbs: Record<string, string | null>; want: (srcs: string[]) => void;
  onSelect: (id: string) => void; onOpen: (id: string) => void;
}) {
  const [hover, setHover] = useState<{ id: string; x: number; top: number } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const visible = shots.filter((s) => s.end * pps >= view[0] - 200 && s.start * pps <= view[1] + 200);
  const srcs = visible.map((s) => s.thumb_src).filter((s): s is string => !!s);
  useEffect(() => { want(srcs); }, [srcs.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const hovered = hover && shots.find((s) => s.id === hover.id);
  return (
    <>
      {visible.map((s) => {
        const t = s.thumb_src ? thumbs[s.thumb_src] : null;
        const w = Math.max(8, (s.end - s.start) * pps - 3);
        return (
          <div key={s.id} data-shot-id={s.id} className={`shot-card story ${selected === s.id ? "sel" : ""} st-${s.status}`}
               style={{ left: s.start * pps + 1, width: w, backgroundImage: t ? `url("${media(dir, t)}")` : undefined }}
               title={`${s.id} · ${s.framing ?? ""}`}
               onClick={(e) => { e.stopPropagation(); onSelect(s.id); }}
               onDoubleClick={(e) => { e.stopPropagation(); onOpen(s.id); }}
               onMouseEnter={(e) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                 window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setHover({ id: s.id, x: r.left, top: r.top }), 450); }}
               onMouseLeave={() => { window.clearTimeout(timer.current); setHover(null); }}>
            {!t && <div className="ph">{w > 70 ? (s.thumb_source === "placeholder" ? "No image yet" : "…") : ""}</div>}
            <div className="card-top"><span className="id num">{s.id.slice(1)}</span>
              {s.keyframe_check === "fail" && <span className="kf-flag fail" title="The keyframe's hands or body look wrong. Open Keyframe tools to see which." aria-label="Keyframe hands or body look wrong">✋</span>}
              {s.keyframe_check === "look" && <span className="kf-flag look" title="The keyframe passed but its hands are worth a look." aria-label="Keyframe hands worth a look">✋</span>}
              {s.versions.length > 1 && w > 70 && <span className="vers num">v{s.versions.length}</span>}</div>
            {voices?.[s.id] && (voices[s.id].people ?? []).length > 0 && (() => {
              const v = voices[s.id], n = v.people.length, r = v.people.filter((p) => p.recording).length, f = fill(v);
              return <>
                <button className={`kc-voice ${r === n ? "all" : r ? "some" : "none"}`} onClick={(e) => { e.stopPropagation(); onVoice?.(s.id); }}
                        aria-label={r ? `${s.id}: ${r}/${n} voices recorded` : `+ Add a voice to ${s.id}`} title={r ? `${r} of ${n} voice${n === 1 ? "" : "s"} recorded: open` : "Add your recorded voice (or drop the file here)"}>
                  <I.Mic size={11} />{w > 60 && <span className="num">{r ? `${r}/${n}` : "+"}</span>}</button>
                {f.total > 0 && <i className={`kc-voicebar ${f.over ? "over" : ""}`} style={{ width: Math.min(w, Math.max(4, f.total * pps)) }} aria-hidden="true" />}
              </>;
            })()}
            {w > 54 && <div className="card-bot"><i className={`dot-st ${STATUS[s.status].cls}`} />{w > 90 && STATUS[s.status].label}</div>}
          </div>
        );
      })}
      {hovered && <HoverPreview dir={dir} shot={hovered} x={hover!.x} top={hover!.top} thumb={hovered.thumb_src ? thumbs[hovered.thumb_src] : null} />}
    </>
  );
}

function HoverPreview({ dir, shot, x, top, thumb }: { dir: string; shot: BoardShot; x: number; top: number; thumb?: string | null }) {
  const left = Math.min(Math.max(8, x), window.innerWidth - 340);
  return (
    <div className="hover-preview glass" style={{ left, bottom: window.innerHeight - top + 8, position: "fixed" }}>
      {shot.preview && isVideo(shot.preview) ? <video src={media(dir, shot.preview)} autoPlay muted loop playsInline /> :
        thumb ? <img src={media(dir, thumb)} alt="" /> : <div className="ph big">No image yet</div>}
      <div className="hp-meta"><b className="num">{shot.id}</b> <StatusChip s={shot.status} />
        <span className="num dim">{(shot.end - shot.start).toFixed(1)}s · {shot.thumb_source}</span></div>
      <div className="hp-beat">{shot.beat}</div>
      <div className="dim" style={{ fontSize: 11 }}>Double-click to open</div>
    </div>
  );
}

// ---------------------------------------------------------------- shot viewer

/** Every version of a shot, side by side with the one in use. Approve, lock, retry; references for this shot. */
export function ShotViewer({ dir, shot, library, onClose, onChanged, onRegenerate }: {
  dir: string; shot: BoardShot; library: Library; onClose: () => void; onChanged: () => void; onRegenerate: () => void;
}) {
  const takes = shot.versions.filter((v) => v.kind !== "image");
  const [pick, setPick] = useState<string | null>(shot.approved ?? takes.filter((v) => v.state === "ready").slice(-1)[0]?.id ?? takes.slice(-1)[0]?.id ?? null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const v = takes.find((t) => t.id === pick) ?? null;
  const [comparing, setComparing] = useState(false);   // side by side: the picked take (left) and another one (right)
  const [other, setOther] = useState<string | null>(null);
  const w = comparing ? takes.find((t) => t.id === other) ?? null : null;
  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await f(); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const shotAssign = library.assign.shots[shot.id] ?? {};
  const onIds = new Set(shot.references.map((r) => r.id));
  const toggle = (id: string, on: boolean) => act(() => api.library(dir, "assign", { scope: "shot", key: shot.id, id, on }));
  const inherit = (id: string) => act(() => api.library(dir, "reset", { scope: "shot", key: shot.id, id }));
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass viewer-sheet" role="dialog" aria-label={`Shot ${shot.id}`} onClick={(e) => e.stopPropagation()}>
        <div className="vs-head">
          <h2 className="num">Shot {shot.id}</h2><StatusChip s={shot.status} />
          <span className="dim num">{fmtTime(shot.start)} → {fmtTime(shot.end)} · {(shot.end - shot.start).toFixed(1)}s</span>
          <div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button>
        </div>
        <div className="vs-body">
          <div className="vs-main">
            {comparing ? <TakeCompare left={v} right={w} src={(t) => (t.output && isVideo(t.output) ? media(dir, t.output) : null)} busy={busy} locked={shot.locked}
                                      onUse={(t) => act(() => api.library(dir, "approve", { shot: shot.id, job: t.id }))}
                                      onSwap={() => { if (other) { setPick(other); setOther(pick); } }} /> :
            <div className="vs-media">
              {v?.output && isVideo(v.output) ? <video key={v.id} src={media(dir, v.output)} controls autoPlay muted loop playsInline /> :
                shot.keyframe ? <img src={media(dir, shot.keyframe)} alt="Keyframe" /> :
                  <div className="ph big">{v ? stateText(v) : "Nothing rendered yet"}</div>}
            </div>}
            {v && !comparing && <div className="vs-take">
              <b>Version {v.n}</b> · {v.provider} · <span className="num">{v.model}</span>
              {v.cost != null && <> · <span className="num">{v.cost} {v.cost_unit === "credits" ? "credits" : "USD"}</span></>}
              {v.approved && <span className="chip ready" style={{ marginLeft: 8 }}><I.Check size={11} /> In the video</span>}
              {v.error && <div className="error-text" style={{ marginTop: 6 }}>{v.error}</div>}
            </div>}
            <div className="vs-actions">
              {v && !comparing && v.state === "ready" && !v.approved && <button className="btn primary" disabled={busy || shot.locked}
                onClick={() => act(() => api.library(dir, "approve", { shot: shot.id, job: v.id }))}>Use this version</button>}
              {v && (v.state === "failed" || v.state === "uncertain") &&
                <button className="btn" disabled={busy} onClick={() => act(() => api.resolveJob(dir, v.id, "retry"))}>Retry</button>}
              <button className="btn" disabled={busy || shot.locked} onClick={onRegenerate}
                      title="Opens the render panel. The version in use stays until you choose a new one.">Regenerate…</button>
              <button className="btn ghost" disabled={busy} onClick={() => act(() => api.library(dir, "lock", { shot: shot.id, on: !shot.locked }))}>
                <I.Lock size={13} /> {shot.locked ? "Unlock" : "Lock"}</button>
            </div>
            <FramesPanel dir={dir} shot={shot.id} onChanged={onChanged} />
            <PromptView dir={dir} shot={shot.id} />
            {shot.locked && <p className="dim">Locked: this shot won't be re-rendered and its version can't change until you unlock it.</p>}
            {err && <div className="error-text">{err}</div>}
          </div>
          <div className="vs-side">
            <h4>Versions ({takes.length})
              {takes.filter((t) => t.state === "ready").length > 1 && <button className="link" style={{ marginLeft: 8 }}
                onClick={() => { setComparing((c) => !c); setOther(null); }}>{comparing ? "Done comparing" : "Compare side by side"}</button>}</h4>
            {comparing && <p className="dim">Click a version to show it on the right.</p>}
            {takes.length === 0 && <p className="dim">No renders yet. Regenerate to make the first one.</p>}
            <div className="vs-versions">
              {[...takes].reverse().map((t) => (
                <button key={t.id} className={`vs-ver ${pick === t.id || (comparing && other === t.id) ? "on" : ""}`}
                        onClick={() => (comparing && t.id !== pick ? setOther(t.id) : setPick(t.id))}>
                  <span className="num">v{t.n}</span>
                  <span className="vv-model">{t.model.split("/").slice(-2).join("/")}</span>
                  {t.approved ? <span className="chip ready"><I.Check size={10} /> In use</span> : <span className={`chip ${verCls(t)}`}>{stateText(t)}</span>}
                </button>
              ))}
            </div>
            <h4 style={{ marginTop: 16 }}>References for this shot</h4>
            <p className="dim" style={{ marginBottom: 6 }}>From the library. Changes here only affect this shot.</p>
            <ul className="vs-refs">
              {library.items.map((it) => {
                const on = onIds.has(it.id);
                const local = (shotAssign.add ?? []).includes(it.id) || (shotAssign.remove ?? []).includes(it.id);
                const from = shot.references.find((r) => r.id === it.id)?.from;
                return (
                  <li key={it.id} className={on ? "on" : ""}>
                    <label><input type="checkbox" checked={on} disabled={busy} onChange={(e) => toggle(it.id, e.target.checked)} />
                      <span className="k-kind">{KIND_LABEL[it.kind]}</span> {it.name}</label>
                    <span className="dim">{local ? <button className="link" onClick={() => inherit(it.id)}>reset</button> : from ?? ""}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The exact words the next render of this shot sends (on the model this project's routing would use). Free: nothing is rendered. */
function PromptView({ dir, shot }: { dir: string; shot: string }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"video" | "image">("video");
  const [res, setRes] = useState<{ prompt: string; model: string; refs: string[] } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!open) return;
    let live = true;
    setRes(null); setErr("");
    (async () => {
      const r = await api.routing<{ provider: string | null; model?: string; label?: string; reason?: string }>(dir, "pick", { kind });
      if (!r.provider) throw new Error(r.reason ?? "No renderer is set up for this yet.");
      const p = await api.renderPreview(dir, shot, r.provider, r.model ?? null, {}, kind);
      const role = p.manifest.roles?.prompt ?? "prompt";
      if (live) setRes({ prompt: String(p.payload[role] ?? ""), model: r.label ?? p.manifest.title, refs: (p.references ?? []).map((x) => x.label) });
    })().catch((e) => live && setErr(errorText(e)));
    return () => { live = false; };
  }, [open, kind, dir, shot]);
  return (
    <details className="vs-prompt" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Prompt that will be sent</summary>
      <div className="vs-prompt-kind">
        {(["video", "image"] as const).map((k) => <button key={k} className={`link ${kind === k ? "on" : ""}`} onClick={() => setKind(k)}>{k === "video" ? "Video" : "Keyframe"}</button>)}
        {res && <span className="dim">· {res.model}</span>}
        {res && <button className="link" style={{ marginLeft: "auto" }} onClick={() => navigator.clipboard.writeText(res.prompt)}>Copy</button>}
      </div>
      {!res && !err && <p className="dim"><span className="spin sm" /> Building the request…</p>}
      {err && <p className="error-text">{err}</p>}
      {res && <><pre className="vs-prompt-text">{res.prompt || "(this model takes no text prompt)"}</pre>
        {res.refs.length > 0 && <p className="dim">With {res.refs.length} reference image{res.refs.length === 1 ? "" : "s"}: {res.refs.join(", ")}</p>}</>}
    </details>
  );
}

const stateText = (v: Version) => ({ ready: "Ready", failed: "Failed", uncertain: "Check", queued: "Queued", submitting: "Sending",
  submitted: "Generating", dismissed: "Dismissed" } as Record<string, string>)[v.state] ?? v.state;
const verCls = (v: Version) => v.state === "ready" ? "planned" : v.state === "failed" ? "failed" : v.state === "uncertain" ? "review" : "gen";

// ---------------------------------------------------------------- library

export const KIND_LABEL: Record<RefKind, string> = {
  character: "Character", set: "Set", prop: "Prop", wardrobe: "Wardrobe", lighting: "Lighting", style: "Style",
  video: "Motion", audio: "Audio",
};
const KIND_HINT: Record<RefKind, string> = {
  character: "Joins every shot the character performs in.", set: "A location. Assign it to the scenes that happen there.",
  prop: "An object that must look the same every time.", wardrobe: "Outfits and costume details.",
  lighting: "Mood and lighting to match.", style: "Art direction or colour reference.",
  video: "A clip whose motion or camera move to follow (models that accept video).",
  audio: "Sound to follow (models that accept reference audio).",
};
const KINDS = Object.keys(KIND_LABEL) as RefKind[];
const MEDIA_EXT = ["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "m4v", "mp3", "wav", "m4a"];

/** Characters, sets, props, wardrobe, lighting, style, motion and audio references; project-wide or per scene. */
export function LibrarySheet({ dir, scenes, onClose, onChanged, autoMake }: {
  dir: string; scenes: { number: number; heading: string }[]; onClose: () => void; onChanged: () => void; autoMake?: boolean;
}) {
  const [lib, setLib] = useState<Library | null>(null);
  const [draft, setDraft] = useState<{ kind: RefKind; name: string; files: string[]; notes: string; id?: string } | null>(null);
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const [makeOpen, setMakeOpen] = useState(!!autoMake);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const load = useCallback(() => api.library<Library>(dir, "library").then(setLib).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const srcs = (lib?.items ?? []).flatMap((i) => i.files.slice(0, 1)).filter((f) => !(f in thumbs) && !/\.(mp3|wav|m4a)$/i.test(f));
    if (srcs.length) api.thumbs(dir, srcs).then((t) => setThumbs((o) => ({ ...o, ...t }))).catch(() => {});
  }, [lib, dir]); // eslint-disable-line react-hooks/exhaustive-deps

  const importFiles = useCallback(async (paths: string[]) => {
    setErr("");
    const got: string[] = [];
    for (const p of paths) {
      try { got.push((await api.importReference(dir, p)).ref.replace(/^project:/, "")); } catch (e) { setErr(errorText(e)); }
    }
    if (!got.length) return;
    const first = got[0].split("/").pop()!.replace(/\.[^.]+$/, "");
    const kind: RefKind = /\.(mp4|mov|webm|m4v)$/i.test(got[0]) ? "video" : /\.(mp3|wav|m4a)$/i.test(got[0]) ? "audio" : "prop";
    setDraft((d) => d ? { ...d, files: [...d.files, ...got] } : { kind, name: first.replace(/[_-]+/g, " "), files: got, notes: "" });
  }, [dir]);

  useEffect(() => {
    const un = getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "enter" || p.type === "over") setOver(true);
      else if (p.type === "leave") setOver(false);
      else if (p.type === "drop") { setOver(false); importFiles(p.paths.filter((f) => MEDIA_EXT.includes(f.split(".").pop()!.toLowerCase()))); }
    });
    return () => { un.then((f) => f()); };
  }, [importFiles]);

  const pick = async () => {
    const f = await open({ multiple: true, filters: [{ name: "Images, video, audio", extensions: MEDIA_EXT }] });
    if (f) importFiles(Array.isArray(f) ? f : [f]);
  };
  const save = async () => {
    if (!draft) return;
    try { setLib(await api.library<Library>(dir, "upsert", draft)); setDraft(null); onChanged(); window.dispatchEvent(new Event("pf-library-changed")); } catch (e) { setErr(errorText(e)); }
  };
  const call = async (action: string, data: Record<string, unknown>) => {
    try { setLib(await api.library<Library>(dir, action, data)); onChanged(); window.dispatchEvent(new Event("pf-library-changed")); } catch (e) { setErr(errorText(e)); }
  };
  const sceneState = (id: string, n: number) => {
    const c = lib?.assign.scenes[String(n)];
    return c?.add?.includes(id) ? "on" : c?.remove?.includes(id) ? "off" : "inherit";
  };
  const cycleScene = (it: RefItem, n: number) => {
    const s = sceneState(it.id, n);
    const onProject = lib!.assign.project.includes(it.id);
    // inherit -> the opposite of the project setting -> back to inherit
    if (s === "inherit") call("assign", { scope: "scene", key: n, id: it.id, on: !onProject });
    else call("reset", { scope: "scene", key: n, id: it.id });
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className={`sheet glass library-sheet ${over ? "drop" : ""}`} role="dialog" aria-label="Reference library" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Reference library</h2><div style={{ flex: 1 }} />
          <button className="btn ghost" onClick={() => setMakeOpen(true)} title="Make pictures for characters, outfits, props and places that have none, from their specs">Make missing pictures…</button>
          <button className="btn" onClick={pick}>Add files…</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Everything the models should match. Project-wide items reach every shot; turn them on or off per scene here,
          or per shot from the shot viewer. Drop images, clips or audio anywhere on this sheet. When a model takes fewer references than a
          shot has, characters go first, then wardrobe, sets, props, lighting and style.</p>
        {makeOpen && <RefGenSheet dir={dir} onClose={() => { setMakeOpen(false); load(); }} onChanged={() => { load(); onChanged(); }} />}
        <BibleEditor dir={dir} />
        {draft && <div className="lib-draft">
          <div className="lib-draft-files">{draft.files.map((f) => <span key={f} className="chip num">{f.split("/").pop()}</span>)}</div>
          <div className="kv settings-kv">
            <span className="k">Kind</span>
            <select className="text-input" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as RefKind })}>
              {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select>
            <span className="k">Name</span>
            <input className="text-input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                   placeholder={draft.kind === "character" ? "Exactly as named in the script" : "e.g. Night train platform"} />
            <span className="k">Notes</span>
            <input className="text-input" value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                   placeholder="Optional: what to match (sent with the reference)" />
          </div>
          <p className="dim">{KIND_HINT[draft.kind]}</p>
          <div className="sheet-actions"><button className="btn ghost" onClick={() => setDraft(null)}>Cancel</button>
            <button className="btn primary" onClick={save} disabled={!draft.name.trim()}>Save reference</button></div>
        </div>}
        {err && <div className="error-text">{err}</div>}
        {!lib ? <div className="dim">Loading…</div> : KINDS.filter((k) => lib.items.some((i) => i.kind === k)).map((k) => (
          <div key={k} className="lib-group">
            <h4>{KIND_LABEL[k]}s</h4>
            {lib.items.filter((i) => i.kind === k).map((it) => {
              const t = thumbs[it.files[0]];
              const onProject = lib.assign.project.includes(it.id);
              return (
                <div key={it.id} className="lib-item">
                  <div className="lib-thumb" style={{ backgroundImage: t ? `url("${media(dir, t)}")` : undefined }}>
                    {!t && <span>{/\.(mp3|wav|m4a)$/i.test(it.files[0] ?? "") ? "♪" : "—"}</span>}</div>
                  <div className="lib-body">
                    <div className="lib-name">{it.name} {it.files.length > 1 && <span className="dim num">· {it.files.length} files</span>}</div>
                    {it.notes && <div className="dim">{it.notes}</div>}
                    <div className="lib-scope">
                      {it.kind === "character" && !it.sheet ? <span className="dim">Auto: shots where {it.name} performs</span> :
                        <label><input type="checkbox" checked={onProject} onChange={(e) => call("assign", { scope: "project", id: it.id, on: e.target.checked })} /> Whole project</label>}
                      {scenes.length > 0 && <span className="scene-chips"><span className="dim" title="Click a scene to override: on, off, or back to inherit">Scenes</span>{scenes.map((s) => {
                        const st = sceneState(it.id, s.number);
                        return <button key={s.number} className={`sc-chip ${st}`} title={`Scene ${s.number}: ${s.heading} — ${st === "inherit" ? "inherits" : st}`}
                                       onClick={() => cycleScene(it, s.number)}>{s.number}</button>;
                      })}</span>}
                    </div>
                  </div>
                  <div className="lib-actions">
                    <button className="btn ghost small" onClick={() => setDraft({ id: it.id, kind: it.kind, name: it.name, files: it.files, notes: it.notes ?? "" })}>Edit</button>
                    <button className="btn ghost small" onClick={async () => { if (await ask(`Remove “${it.name}” from the library? The file stays in the project folder.`)) call("delete", { id: it.id }); }}>Remove</button>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
        {lib && lib.items.length === 0 && !draft && <p className="dim">No references yet. Add character images first: they matter most.</p>}
      </div>
    </div>
  );
}

/** Approve the newest keyframe for every shot that has none yet. Shows them all first; never replaces an approved keyframe. */
export function ApproveKeyframes({ dir, pending, onClose, onDone }: {
  dir: string; pending: Record<string, string>; onClose: () => void; onDone: () => void;
}) {
  const ids = Object.keys(pending).sort();
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.thumbs(dir, Object.values(pending)).then(setThumbs).catch(() => {}); }, [dir, pending]);
  const chosen = ids.filter((i) => !skip.has(i));
  const go = async () => {
    setBusy(true); setErr("");
    try { await api.library(dir, "approve_keyframes", { shots: chosen }); onDone(); }
    catch (e) { setErr(errorText(e)); setBusy(false); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass approve-sheet" role="dialog" aria-label="Approve keyframes" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Approve {chosen.length} keyframe{chosen.length === 1 ? "" : "s"}</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">The newest keyframe of each shot that doesn't have one approved yet. Click any you don't want; you can make another
          for those later. Approved keyframes are where each video render starts. Shots that already have one keep it.</p>
        <div className="approve-grid">
          {ids.map((id) => {
            const t = thumbs[pending[id]];
            const off = skip.has(id);
            return (
              <button key={id} className={`approve-cell ${off ? "off" : ""}`} title={off ? "Skipped: click to include" : "Click to skip"}
                      onClick={() => setSkip((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; })}>
                <span className="approve-img" style={{ backgroundImage: t ? `url("${media(dir, t)}")` : undefined }} />
                <span className="num">{id}</span>{off ? <span className="dim"> · skip</span> : <I.Check size={11} />}
              </button>
            );
          })}
        </div>
        {err && <div className="error-text">{err}</div>}
        <div className="sheet-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || !chosen.length} onClick={go}>{busy ? "Approving…" : `Approve ${chosen.length}`}</button>
        </div>
      </div>
    </div>
  );
}

type Bible = { world: string; rules: string; palette: string; avoid: string };
const BIBLE_ROWS: { k: keyof Bible; label: string; hint: string }[] = [
  { k: "world", label: "World", hint: "e.g. Present-day Lagos, humid nights, lived-in homes" },
  { k: "rules", label: "Always", hint: "e.g. Sege wears the white undershirt until scene 5; the suitcase is brown leather" },
  { k: "palette", label: "Palette", hint: "e.g. predawn blue, sodium orange, warm amber skin light" },
  { k: "avoid", label: "Never show", hint: "e.g. text on screen, weapons, snow" },
];

/** Production Bible basics: rules every shot's prompt carries. Saved with the project; free. */
function BibleEditor({ dir }: { dir: string }) {
  const [b, setB] = useState<Bible | null>(null);
  const [saved, setSaved] = useState<Bible | null>(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.library<Bible>(dir, "bible").then((x) => { setB(x); setSaved(x); setOpen(Object.values(x).some(Boolean)); }).catch(() => {}); }, [dir]);
  if (!b) return null;
  const dirty = JSON.stringify(b) !== JSON.stringify(saved);
  const save = () => api.library<Bible>(dir, "bible", { bible: b }).then((x) => { setB(x); setSaved(x); setErr(""); }).catch((e) => setErr(errorText(e)));
  return (
    <div className="bible">
      <button className="bible-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <b>Production Bible</b><span className="dim">World rules every shot follows{Object.values(saved ?? {}).some(Boolean) ? "" : " (empty)"}</span>
        <span className="grow" />{open ? "Hide" : "Edit"}</button>
      {open && <>
        <div className="kv settings-kv">
          {BIBLE_ROWS.map((r) => <Fragment key={r.k}><span className="k">{r.label}</span>
            <textarea className="text-input" rows={2} value={b[r.k]} placeholder={r.hint}
                      onChange={(e) => setB({ ...b, [r.k]: e.target.value })} /></Fragment>)}
        </div>
        {err && <div className="error-text">{err}</div>}
        <div className="sheet-actions"><span className="dim">Used in every keyframe and video prompt from now on.</span>
          <button className="btn primary" onClick={save} disabled={!dirty}>{dirty ? "Save bible" : "Saved"}</button></div>
      </>}
    </div>
  );
}
