import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ModelChoice } from "./ModelChoice";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { api, errorText, fmtTime, type Choreography, type EngineEvent, type Library, type Onboarding, type Probe,
  type RefItem, type RefKind, type WizardStage } from "./api";
import * as I from "./icons";
import "./wizard.css";
import { ask } from "./ask";

/**
 * New-project setup: Music → Lyrics → Script → Characters, props & environments → Choreography → Production review.
 * One shared, persisted state (project.json "onboarding"); every stage saves before moving on, so leaving and
 * reopening resumes exactly here. Only the music is required.
 */
const STAGES: { id: Exclude<WizardStage, "review" | "done">; n: string; title: string; optional: boolean }[] = [
  { id: "music", n: "01", title: "Upload Your Music", optional: false },
  { id: "lyrics", n: "02", title: "Add Your Lyrics", optional: true },
  { id: "script", n: "03", title: "Add a Script", optional: true },
  { id: "assets", n: "04", title: "Add Characters, Props & Environments", optional: true },
  { id: "choreography", n: "05", title: "Add Choreography", optional: true },
];
const ORDER: WizardStage[] = ["music", "lyrics", "script", "assets", "choreography", "review"];
const AUDIO = ["mp3", "wav", "m4a", "flac", "aac", "ogg"];
const VIDEO = ["mp4", "mov", "m4v", "mkv", "webm"];
const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const baseName = (p: string) => p.split(/[\\/]/).pop()!;
const media = (dir: string, rel: string) => api.mediaUrl(`${dir}/${rel}`);

export function Wizard({ initialDir, initialFile, onExit, onFinish, produce, onProduce }: {
  initialDir: string | null; initialFile?: string | null;
  onExit: () => void; onFinish: (dir: string, director: boolean) => void; produce?: boolean; onProduce?: (dir: string) => void;
}) {
  const [dir, setDir] = useState<string | null>(initialDir);
  const [ob, setOb] = useState<Onboarding>({ stage: "music", done: [], skipped: [] });
  const [title, setTitle] = useState("");
  const [loaded, setLoaded] = useState(!initialDir);
  const [phase, setPhase] = useState<"in" | "out">("in");
  const [dirn, setDirn] = useState<1 | -1>(1);
  const [error, setError] = useState("");
  const [announce, setAnnounce] = useState("");
  const saveHook = useRef<null | (() => Promise<boolean>)>(null);   // the current stage's "save before leaving"
  const [canNext, setCanNext] = useState(false);
  const obRef = useRef(ob);   // latest saved state: stages update it while saving, before the step changes

  // Resume an unfinished project exactly where it was left.
  useEffect(() => {
    if (!initialDir) return;
    api.loadProject(initialDir).then((p) => {
      setTitle(p.project.title);
      const o: Onboarding = { stage: "music", done: [], skipped: [], ...(p.project.onboarding ?? {}), ...(p.project.onboarding?.stage === "done" ? { stage: "review" } : {}) };
      obRef.current = o; setOb(o);
      setLoaded(true);
    }).catch((e) => { setError(errorText(e)); setLoaded(true); });
  }, [initialDir]);
  useEffect(() => { try { localStorage.setItem("pf-setup-seen", "1"); } catch { /* optional */ } }, []);

  const persist = useCallback(async (next: Onboarding, d = dir) => {
    obRef.current = next;
    setOb(next);
    if (d) await api.setOnboarding(d, next);
  }, [dir]);

  const go = useCallback(async (to: WizardStage, mark?: "done" | "skipped") => {
    setError("");
    const cur = ob.stage;
    if (mark === "done" || (mark !== "skipped" && ORDER.indexOf(to) > ORDER.indexOf(cur))) {
      // validate + save before any transition
      if (saveHook.current) {
        try { if (!(await saveHook.current())) return; } catch (e) { setError(errorText(e)); return; }
      }
    }
    const base = obRef.current;
    const done = new Set(base.done), skipped = new Set(base.skipped);
    if (mark === "done") { done.add(cur); skipped.delete(cur); }
    if (mark === "skipped") { skipped.add(cur); }
    const next: Onboarding = { ...base, stage: to, done: [...done], skipped: [...skipped] };
    setDirn(ORDER.indexOf(to) >= ORDER.indexOf(cur) ? 1 : -1);
    const swap = async () => {
      try { await persist(next); } catch (e) { setError(errorText(e)); return; }
      setPhase("in");
      const label = to === "review" ? "Production review" : STAGES.find((s) => s.id === to)?.title;
      setAnnounce(`Step ${ORDER.indexOf(to) + 1} of 6: ${label}`);
    };
    if (reduced()) { await swap(); return; }
    setPhase("out");
    window.setTimeout(swap, 140);
  }, [ob, persist]);

  const saveExit = async () => {
    if (saveHook.current) { try { await saveHook.current(); } catch { /* keep what we have */ } }
    if (dir) await api.setOnboarding(dir, obRef.current).catch(() => {});
    onExit();
  };

  if (!loaded) return <div className="wiz"><div className="wiz-loading" role="status">Opening your project…</div></div>;
  const stage = ob.stage === "done" ? "review" : ob.stage;
  const idx = ORDER.indexOf(stage);
  const meta = STAGES.find((s) => s.id === stage);
  const reachable = (s: WizardStage) => s === "music" || (!!dir && (ob.done.includes("music") || s === stage));
  const register = (fn: (() => Promise<boolean>) | null, ok: boolean) => { saveHook.current = fn; setCanNext(ok); };

  return (
    <div className={`wiz wiz-${stage}`} style={{ ["--bg" as string]: `url("${bgFor(stage)}")` }}>
      <div className="wiz-backdrop" aria-hidden />
      {heroFor(stage) && <div className="wiz-hero" aria-hidden style={{ backgroundImage: `url("${heroFor(stage)}")` }} />}
      <header className="wiz-top">
        <div className="wiz-brand"><I.Mark size={26} /><span>PULSEFRAME</span></div>
        <div className="wiz-top-right">
          {title && <span className="dim wiz-title-chip" title="Project">{title}</span>}
          <button className="btn ghost small" onClick={saveExit}>{dir ? "Save & exit" : "Cancel"}</button>
        </div>
      </header>

      <main className={`wiz-stage phase-${phase}`} style={{ ["--dx" as string]: `${dirn * 28}px` }}>
        {stage !== "review" ? (
          <div className="wiz-head">
            <div className="wiz-num num">{meta!.n}</div>
            <div>
              <h1>{meta!.title}{meta!.optional && <span className="wiz-opt"> (Optional)</span>}</h1>
              <p>{SUBTITLE[stage]}</p>
            </div>
          </div>
        ) : null}
        <div className="wiz-body">
          {stage === "music" && <MusicStage dir={dir} initialFile={initialFile ?? null} ob={ob} register={register}
                                            onCreated={async (d, t, extra) => { setDir(d); setTitle(t); await persist({ ...obRef.current, ...extra }, d); }}
                                            onTitle={setTitle} onError={setError} />}
          {stage === "lyrics" && dir && <LyricsStage dir={dir} register={register} onError={setError} />}
          {stage === "script" && dir && <ScriptStage dir={dir} ob={ob} register={register} onError={setError}
                                                     onConcept={(c, notes) => persist({ ...obRef.current, concept: c, concept_notes: notes })} />}
          {stage === "assets" && dir && <AssetsStage dir={dir} register={register} onError={setError} producer={!!produce} onSkipToEnd={() => go("review", "skipped")} />}
          {stage === "choreography" && dir && <ChoreoStage dir={dir} register={register} onError={setError} />}
          {stage === "review" && dir && <ReviewStage dir={dir} ob={ob} onEdit={(s) => go(s)} onError={setError} produce={!!produce}
                                                     onProduce={async () => {
                                                       const o = obRef.current;
                                                       await persist({ ...o, stage: "done", done: [...new Set([...o.done, "review" as WizardStage])] });
                                                       onProduce?.(dir);
                                                     }}
                                                     onStart={async (director) => {
                                                       const o = obRef.current;
                                                       await persist({ ...o, stage: "done", done: [...new Set([...o.done, "review" as WizardStage])] });
                                                       onFinish(dir, director);
                                                     }} />}
        </div>
      </main>

      {error && <div className="wiz-error" role="alert"><I.Alert size={16} /> <span>{error}</span>
        <button className="icon-btn" onClick={() => setError("")} aria-label="Dismiss"><I.Close size={14} /></button></div>}
      <div className="sr-only" role="status" aria-live="polite">{announce}</div>

      <footer className="wiz-foot">
        <button className="wiz-back" onClick={() => idx === 0 ? saveExit() : go(ORDER[idx - 1])}>
          <span className="circle"><I.ArrowLeft size={18} /></span><span>{idx === 0 ? "Home" : "Back"}</span>
        </button>
        <nav className="wiz-dots" aria-label="Setup steps">
          {ORDER.map((s, i) => {
            const label = s === "review" ? "Production review" : STAGES[i].title;
            const state = s === stage ? "on" : ob.done.includes(s) ? "done" : ob.skipped.includes(s) ? "skipped" : "";
            return <button key={s} className={`wiz-dot ${s === "review" ? "final" : ""} ${state}`} disabled={!reachable(s) || s === stage}
                           aria-current={s === stage ? "step" : undefined} title={label} aria-label={`${label}${state === "done" ? " (done)" : state === "skipped" ? " (skipped)" : ""}`}
                           onClick={() => go(s)} />;
          })}
        </nav>
        <div className="wiz-next-area">
          {stage === "music" && dir && canNext && <button className="btn ghost wiz-skip" onClick={() => go("review", "done")}
                                                        title="Skip the optional steps; you can add them later in the Studio"><I.Rocket size={15} /> Quick start</button>}
          {meta?.optional && <button className="btn ghost wiz-skip" onClick={() => go(ORDER[idx + 1], "skipped")}>Skip this step</button>}
          {stage !== "review" && !canNext && <span className="wiz-why dim" role="status">{stage === "music" ? "Choose your song to continue." : meta?.optional ? "Finish this step, or skip it." : "Finish this step to continue."}</span>}
          {stage !== "review" && <button className="btn primary wiz-next" disabled={!canNext} onClick={() => go(ORDER[idx + 1], "done")}
                                         title={!canNext ? (stage === "music" ? "Choose your song first" : "Finish this step first") : undefined}>
            {stage === "choreography" ? "Continue to review" : "Next"} <I.ArrowRight size={18} /></button>}
        </div>
      </footer>
    </div>
  );
}

const SUBTITLE: Record<string, string> = {
  music: "Start with your song. It is the master timeline: every cut, move and lyric follows it.",
  lyrics: "Paste them, load a file, or let PULSEFRAME transcribe them from the vocal. Section tags like [Chorus] give the best song map.",
  script: "Paste a screenplay or story, upload a file, or let PULSEFRAME propose creative directions after it listens to the song.",
  assets: "Reference images keep faces, outfits, objects and places consistent in every shot. Characters matter most.",
  choreography: "Upload a choreography sheet or reference video, write movement notes, pick a style, or skip for acting-led videos.",
};
const bgFor = (s: WizardStage) => `onboarding/bg_${({ music: "music", lyrics: "lyrics", script: "script", assets: "assets", choreography: "choreo", review: "review", done: "review" } as Record<string, string>)[s]}.jpg`;
const heroFor = (s: WizardStage) => ({ music: "onboarding/music_hero.jpg", lyrics: "onboarding/lyrics_hero.jpg", assets: "onboarding/assets_hero.jpg" } as Record<string, string>)[s];

type Register = (fn: (() => Promise<boolean>) | null, ok: boolean) => void;

// ---------------------------------------------------------------- 01 music

function MusicStage({ dir, initialFile, ob, register, onCreated, onTitle, onError }: {
  dir: string | null; initialFile: string | null; ob: Onboarding; register: Register;
  onCreated: (dir: string, title: string, extra: Partial<Onboarding>) => Promise<void>; onTitle: (t: string) => void; onError: (e: string) => void;
}) {
  const [probe, setProbe] = useState<Probe | null>(ob.probe ? { ...ob.probe, kind: "audio" } : null);
  const [name, setName] = useState(ob.song_name ?? "");
  const [pendingVideo, setPendingVideo] = useState<{ path: string; probe: Probe } | null>(null);
  const [busy, setBusy] = useState("");
  const [over, setOver] = useState(false);
  const [songPath, setSongPath] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const tried = useRef(false);

  useEffect(() => {
    if (!dir) return;
    api.loadProject(dir).then((p) => { setSongPath(p.song_path); setTitle(p.project.title); }).catch(() => {});
  }, [dir]);
  useEffect(() => { register(null, !!dir && !!probe && !busy); }, [dir, probe, busy]); // eslint-disable-line react-hooks/exhaustive-deps

  const useAudio = async (path: string, p: Probe, fromVideo?: string) => {
    setBusy(dir ? "Replacing the song…" : "Creating your project…");
    try {
      const t = (p.title || baseName(fromVideo ?? path).replace(/\.[^.]+$/, "")).replace(/[-_]+/g, " ").trim() || "Untitled";
      const extra: Partial<Onboarding> = { probe: { duration: p.duration, peaks: p.peaks }, song_name: baseName(fromVideo ?? path),
                                           source_video: fromVideo ?? null, stage: "music" };
      if (dir) { await api.replaceSong(dir, path); await onCreated(dir, title || t, extra); }
      else {
        const d = await api.createProject(path, t, null, null, null);
        setTitle(t); onTitle(t);
        await onCreated(d, t, extra);
      }
      setProbe(p); setName(extra.song_name!);
    } catch (e) { onError(errorText(e)); } finally { setBusy(""); }
  };

  const take = useCallback(async (path: string) => {
    const ext = path.split(".").pop()!.toLowerCase();
    if (![...AUDIO, ...VIDEO].includes(ext)) { onError("Use an audio file (MP3, WAV, M4A, FLAC) or a video with a soundtrack (MP4, MOV)."); return; }
    setBusy("Reading the file…"); onError("");
    try {
      const p = await api.probeMedia(path);
      setBusy("");
      if (p.kind === "video") setPendingVideo({ path, probe: p });   // the user decides: soundtrack as master audio, or not
      else await useAudio(path, p);
    } catch (e) { setBusy(""); onError(errorText(e)); }
  }, [dir, title]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (initialFile && !dir && !tried.current) { tried.current = true; take(initialFile); } }, [initialFile, dir, take]);
  useEffect(() => {
    const un = getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "enter" || p.type === "over") setOver(true);
      else if (p.type === "leave") setOver(false);
      else if (p.type === "drop") { setOver(false); if (p.paths[0]) take(p.paths[0]); }
    });
    return () => { un.then((f) => f()); };
  }, [take]);

  const choose = async () => {
    const f = await open({ filters: [{ name: "Music", extensions: AUDIO }, { name: "Video with soundtrack", extensions: VIDEO }] });
    if (typeof f === "string") take(f);
  };
  const saveTitle = async () => {
    if (!dir || !title.trim()) return;
    try { await api.setProjectSettings(dir, { title: title.trim() }); onTitle(title.trim()); } catch (e) { onError(errorText(e)); }
  };

  return (
    <div className="wiz-col">
      <div className={`wiz-drop ${over ? "over" : ""}`} onClick={busy ? undefined : choose} role="button" tabIndex={0}
           onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && choose()} aria-label="Choose your song">
        <div className="wiz-drop-icon"><I.Wave size={40} /></div>
        <div>
          <div className="wiz-drop-title">{probe ? "Drop another file to replace the song" : "Drop your audio file here"}</div>
          <div className="dim">MP3, WAV, M4A or FLAC · or a video, to use its soundtrack</div>
          <button className="btn primary wiz-pill" disabled={!!busy} onClick={(e) => { e.stopPropagation(); choose(); }}>
            {busy ? busy : probe ? "Choose a different file" : "Choose Music"}</button>
        </div>
      </div>

      {pendingVideo && (
        <div className="wiz-card wiz-video-choice" role="dialog" aria-label="Video soundtrack">
          <I.Film size={22} />
          <div>
            <b>{baseName(pendingVideo.path)} is a video.</b>
            <p className="dim">Its soundtrack can become the master audio of this project ({fmtTime(pendingVideo.probe.duration)}).
              Reference videos for movement or style belong in Choreography or the reference library instead.</p>
            <div className="wiz-row">
              <button className="btn primary" onClick={() => { const v = pendingVideo; setPendingVideo(null); setBusy("Taking the soundtrack…");
                api.extractSoundtrack(v.path).then((r) => useAudio(r.path, { ...v.probe, kind: "audio" }, v.path)).catch((e) => { setBusy(""); onError(errorText(e)); }); }}>
                Use its soundtrack as the song</button>
              <button className="btn ghost" onClick={() => setPendingVideo(null)}>Choose a song instead</button>
            </div>
          </div>
        </div>
      )}

      {probe && dir && <SongCard dir={dir} songPath={songPath} name={name} probe={probe} />}
      {probe && dir && (
        <div className="wiz-field">
          <label htmlFor="wiz-title">Project title</label>
          <input id="wiz-title" className="text-input" value={title} onChange={(e) => setTitle(e.target.value)} onBlur={saveTitle} />
        </div>
      )}
      {probe && <p className="dim wiz-note"><I.Check size={13} /> Imported. PULSEFRAME maps beats, sections and lyrics when you start directing.</p>}
    </div>
  );
}

/** The imported song: real waveform, real duration, play/pause. */
function SongCard({ dir, songPath, name, probe }: { dir: string; songPath: string | null; name: string; probe: { duration: number; peaks: number[] } }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!songPath) return;
    const a = new Audio(api.mediaUrl(songPath));
    a.preload = "metadata";
    a.ontimeupdate = () => setT(a.currentTime);
    a.onended = () => setPlaying(false);
    a.onerror = () => setErr("This file can't be previewed here, but it was imported.");
    audio.current = a;
    return () => { a.pause(); a.src = ""; audio.current = null; };   // stop and release when leaving the step
  }, [songPath, dir]);
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d")!;
    g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const bars = Math.min(probe.peaks.length, Math.floor(W / 3));
    const step = probe.peaks.length / bars, played = (t / probe.duration) * bars;
    for (let i = 0; i < bars; i++) {
      const v = probe.peaks[Math.floor(i * step)] ?? 0, h = Math.max(1.5, v * (H - 4));
      g.fillStyle = i < played ? "#64b7ff" : "rgba(232,180,92,0.75)";
      g.fillRect(i * 3, (H - h) / 2, 2, h);
    }
  }, [probe, t]);
  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) a.play().then(() => setPlaying(true)).catch(() => setErr("Playback couldn't start."));
    else { a.pause(); setPlaying(false); }
  };
  return (
    <div className="wiz-card wiz-song">
      <button className="wiz-play" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>{playing ? <I.Pause size={18} /> : <I.Play size={18} />}</button>
      <div className="wiz-song-name"><b title={name}>{name}</b><span className="dim num">{fmtTime(t).slice(0, -3)} / {fmtTime(probe.duration).slice(0, -3)}</span></div>
      <canvas ref={canvas} className="wiz-wave" aria-label="Waveform of the imported song"
              onClick={(e) => { const a = audio.current; if (!a) return; const r = (e.target as HTMLElement).getBoundingClientRect();
                a.currentTime = ((e.clientX - r.left) / r.width) * probe.duration; setT(a.currentTime); }} />
      <span className="chip ready"><I.Check size={11} /> Master audio</span>
      {err && <div className="dim" style={{ gridColumn: "1 / -1", fontSize: 12 }}>{err}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- 02 lyrics

function LyricsStage({ dir, register, onError }: { dir: string; register: Register; onError: (e: string) => void }) {
  const [tab, setTab] = useState<"paste" | "upload" | "auto">("paste");
  const [text, setText] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const saved = useRef("");
  useEffect(() => {
    api.loadProject(dir).then(async (p) => {
      if (p.project.lyrics) { try { const t = await api.readText(`${dir}/${p.project.lyrics}`); setText(t); saved.current = t; } catch { /* none */ } }
    }).catch(() => { /* an unreadable project opens with empty lyrics rather than a blank step */ }).finally(() => setLoaded(true));
  }, [dir]);
  const save = useCallback(async () => {
    if (text !== saved.current) { await api.writeProjectText(dir, "lyrics", text); saved.current = text; }
    return true;
  }, [dir, text]);
  useEffect(() => { register(save, loaded && !busy); }, [save, loaded, busy]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!loaded) return; const t = window.setTimeout(() => { save().catch(() => {}); }, 1500); return () => window.clearTimeout(t); }, [text, loaded, save]);
  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => {
      if (e.task === "onboarding" && e.stage) { setBusy(e.stage.charAt(0).toUpperCase() + e.stage.slice(1) + "…"); if (typeof e.progress === "number") setProgress(e.progress); }
    });
    return () => { un.then((f) => f()); };
  }, []);

  const upload = async () => {
    const f = await open({ filters: [{ name: "Lyrics", extensions: ["txt", "lrc", "md"] }] });
    if (typeof f !== "string") return;
    try {
      let t = await api.readText(f);
      if (f.toLowerCase().endsWith(".lrc")) t = t.split(/\r?\n/).map((l) => l.replace(/^\s*(\[\d+:\d+(?:\.\d+)?\])+\s*/, "")).filter((l) => !/^\[(ar|ti|al|by|offset):/i.test(l)).join("\n");
      if (text.trim() && !await ask("Replace the lyrics in the editor with this file?")) return;
      setText(t); setTab("paste");
    } catch (e) { onError(errorText(e)); }
  };
  const transcribe = async () => {
    if (text.trim() && !await ask("Replace the lyrics in the editor with a transcription?")) return;
    setBusy("Starting…"); setProgress(0); onError("");
    try { const r = await api.transcribeLyrics(dir); setText(r.text); setTab("paste"); }
    catch (e) { onError(errorText(e)); }
    finally { setBusy(""); setProgress(null); }
  };
  const sections = useMemo(() => [...text.matchAll(/^\s*\[([^\]]+)\]\s*$/gm)].map((m) => m[1]), [text]);
  const lines = text.split(/\r?\n/).filter((l) => l.trim() && !/^\s*\[.*\]\s*$/.test(l)).length;

  return (
    <div className="wiz-col">
      <div className="wiz-tabs" role="tablist" aria-label="How to add lyrics">
        <button role="tab" aria-selected={tab === "paste"} className={tab === "paste" ? "on" : ""} onClick={() => setTab("paste")}><I.Doc size={17} /> Paste Lyrics</button>
        <button role="tab" aria-selected={tab === "upload"} className={tab === "upload" ? "on" : ""} onClick={() => { setTab("upload"); upload(); }}><I.Upload size={17} /> Upload File</button>
        <button role="tab" aria-selected={tab === "auto"} className={tab === "auto" ? "on" : ""} onClick={() => setTab("auto")}><I.Wave size={17} /> Auto Transcribe</button>
      </div>
      {tab === "auto" && !busy && (
        <div className="wiz-card">
          <p style={{ margin: "0 0 10px" }}>PULSEFRAME isolates the vocal and writes down what it hears, with timings. It runs on this computer
            (a few minutes; faster with an NVIDIA GPU) and costs nothing. Check the result: section tags and spelling are yours to fix.</p>
          <button className="btn primary" onClick={transcribe}><I.Wave size={16} /> Transcribe the vocal</button>
        </div>
      )}
      {busy && (
        <div className="wiz-card" role="status">
          <div className="wiz-row"><span className="spin" /> {busy}</div>
          {progress !== null && <div className="progress"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
          <p className="dim" style={{ margin: "8px 0 0", fontSize: 12 }}>You can keep working in the editor; the transcription only fills it in if you allow it.</p>
        </div>
      )}
      <div className="wiz-editor-wrap">
        <textarea className="wiz-editor" value={text} onChange={(e) => setText(e.target.value)} spellCheck
                  aria-label="Lyrics" placeholder={"[Verse 1]\nFirst line of the song…\n\n[Chorus]\n…"} />
        <div className="wiz-editor-foot">
          <span>{sections.length ? <>Sections: {sections.slice(0, 8).map((s, i) => <span key={i} className="wiz-tag">{s}</span>)}</> : "Tip: put [Verse], [Chorus], [Bridge] on their own lines."}</span>
          <span className="num">{lines} line{lines === 1 ? "" : "s"}</span>
        </div>
      </div>
      <p className="dim wiz-note">Saved as you type. Lyrics are timed to the song when PULSEFRAME maps it; you can adjust them later in the Studio.</p>
    </div>
  );
}

// ---------------------------------------------------------------- 03 script

function ScriptStage({ dir, ob, register, onError, onConcept }: {
  dir: string; ob: Onboarding; register: Register; onError: (e: string) => void; onConcept: (c: "propose" | null, notes: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"paste" | "upload" | "concept">(ob.concept === "propose" ? "concept" : "paste");
  const [text, setText] = useState("");
  const [file, setFile] = useState<string | null>(null);
  const [notes, setNotes] = useState(ob.concept_notes ?? "");
  const [loaded, setLoaded] = useState(false);
  const [frames, setFrames] = useState<string[]>([]);
  const saved = useRef({ text: "", notes: ob.concept_notes ?? "", concept: ob.concept ?? null });
  useEffect(() => {
    api.loadProject(dir).then(async (p) => {
      const s = p.project.script;
      if (s === "script.txt") { const t = await api.readText(`${dir}/${s}`).catch(() => ""); setText(t); saved.current.text = t; }
      else if (s) setFile(s);
      const kf = Object.values((p.keyframes ?? {})[p.directed ? "directed" : "production"] ?? {}).slice(0, 4).map((r) => String(r).replace(/^project:/, ""));
      setFrames(kf);
      setLoaded(true);
    });
  }, [dir]);
  const save = useCallback(async () => {
    if (tab === "paste" && text !== saved.current.text) {
      if (file && text.trim() && !await ask(`Replace the uploaded script (${file}) with the pasted text? The file is kept in the project folder.`)) return false;
      await api.writeProjectText(dir, "script", text); saved.current.text = text; if (text.trim()) setFile(null);
    }
    const concept = tab === "concept" ? "propose" : null;
    if (concept !== saved.current.concept || notes !== saved.current.notes) {
      await onConcept(concept, notes); saved.current.concept = concept; saved.current.notes = notes;
    }
    return true;
  }, [dir, tab, text, file, notes, onConcept]);
  useEffect(() => { register(save, loaded); }, [save, loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async () => {
    const f = await open({ filters: [{ name: "Script", extensions: ["pdf", "txt", "md", "fountain"] }] });
    if (typeof f !== "string") return;
    if ((file || text.trim()) && !await ask("Use this file as the script? Your current script is kept in the project folder.")) return;
    try { const r = await api.attachScript(dir, f); setFile(r.script); setText(""); saved.current.text = ""; } catch (e) { onError(errorText(e)); }
  };

  return (
    <div className="wiz-split">
      <div className="wiz-col">
        <div className="wiz-tabs" role="tablist" aria-label="How to add a script">
          <button role="tab" aria-selected={tab === "paste"} className={tab === "paste" ? "on" : ""} onClick={() => setTab("paste")}><I.Doc size={17} /> Paste Script</button>
          <button role="tab" aria-selected={tab === "upload"} className={tab === "upload" ? "on" : ""} onClick={() => setTab("upload")}><I.Upload size={17} /> Upload File</button>
          <button role="tab" aria-selected={tab === "concept"} className={tab === "concept" ? "on" : ""} onClick={() => setTab("concept")}><I.Wand size={17} /> Creative Concept</button>
        </div>
        {tab === "paste" && <>
          {file && <div className="wiz-card wiz-row"><I.Doc size={18} /> <span>Current script: <b>{file}</b> (uploaded). Pasting text here would replace it.</span></div>}
          <div className="wiz-editor-wrap">
            <textarea className="wiz-editor mono" value={text} onChange={(e) => setText(e.target.value)} aria-label="Script"
                      placeholder={"INT. BEDROOM - NIGHT\nSHOT 1: Close on her eyes opening…\n\nOr simply describe the story you want the video to tell."} />
            <div className="wiz-editor-foot"><span>Scenes and shots you write are followed exactly.</span><span className="num">{text.length.toLocaleString()} characters</span></div>
          </div>
        </>}
        {tab === "upload" && (
          <div className="wiz-card">
            {file ? <div className="wiz-row"><I.Doc size={20} /><div><b>{file}</b><div className="dim">Attached. PULSEFRAME reads its scenes and shots when it maps the song.</div></div></div>
              : <p className="dim" style={{ marginTop: 0 }}>A PDF, TXT, Markdown or Fountain screenplay. The original is kept unchanged.</p>}
            <button className="btn primary" onClick={upload} style={{ marginTop: 10 }}><I.Upload size={16} /> {file ? "Choose another file" : "Choose script file"}</button>
          </div>
        )}
        {tab === "concept" && (
          <div className="wiz-card">
            <p style={{ marginTop: 0 }}>No script? After listening to the song, PULSEFRAME proposes <b>three creative directions</b> (performance, story, or both).
              You pick one and it writes the treatment and shot plan. Your uploaded or pasted script, if any, is never replaced without asking.</p>
            <label className="wiz-label" htmlFor="concept-notes">Describe the video you imagine <span className="dim">(optional)</span></label>
            <textarea id="concept-notes" className="wiz-editor short" value={notes} onChange={(e) => setNotes(e.target.value)}
                      placeholder="e.g. A night in Lagos, one long walk home, warm and hopeful; the singer performs on a rooftop at dawn." />
          </div>
        )}
      </div>
      <figure className="wiz-gallery" aria-label={frames.length ? "Storyboard frames from this project" : "Illustration"}>
        {frames.length ? frames.map((f) => <img key={f} src={media(dir, f)} alt="" />)
          : <img src="onboarding/script_example.jpg" alt="" className="example" />}
        {!frames.length && <figcaption>Illustration · your storyboard frames appear here once shots are drawn</figcaption>}
      </figure>
    </div>
  );
}

// ---------------------------------------------------------------- 04 assets

const CATS: { kind: RefKind; title: string; blurb: string; icon: React.ReactNode; add: string }[] = [
  { kind: "character", title: "Characters", blurb: "One clean image per person: face and full body. Named as in your script.", icon: <I.User size={22} />, add: "Add Characters" },
  { kind: "prop", title: "Props", blurb: "Objects that must look the same every time they appear.", icon: <I.Cube size={22} />, add: "Add Props" },
  { kind: "set", title: "Environments", blurb: "Locations and sets. Add as many as the story needs.", icon: <I.Mountain size={22} />, add: "Add Environments" },
  { kind: "wardrobe", title: "Wardrobe", blurb: "Costumes, outfits and styled looks.", icon: <I.Shirt size={22} />, add: "Add Wardrobe" },
];
const IMG_EXT = ["png", "jpg", "jpeg", "webp"];
/** "character_amara_v2.png" → "Amara": a readable name from a file name. */
export const niceName = (file: string) => {
  const words = baseName(file).replace(/\.[^.]+$/, "").split(/[\s_\-.]+/)
    .filter((w) => w && !/^(character|char|ref|reference|sheet|img|image|final|copy|v\d+|\d+)$/i.test(w));
  const n = words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  return n || baseName(file).replace(/\.[^.]+$/, "");
};

function AssetsStage({ dir, register, onError, producer, onSkipToEnd }: { dir: string; register: Register; onError: (e: string) => void; producer: boolean; onSkipToEnd: () => void }) {
  const [lib, setLib] = useState<Library | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [draft, setDraft] = useState<{ kind: RefKind; files: string[]; name: string; together: boolean } | null>(null);
  const [open_, setOpen] = useState<RefKind | null>(null);
  const [over, setOver] = useState<RefKind | null>(null);
  const cards = useRef<Record<string, HTMLElement | null>>({});
  const load = useCallback(() => api.library<Library>(dir, "library").then(setLib).catch((e) => onError(errorText(e))), [dir, onError]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { register(async () => true, true); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const srcs = (lib?.items ?? []).map((i) => i.files[0]).filter((f) => f && !(f in thumbs));
    if (srcs.length) api.thumbs(dir, srcs).then((t) => setThumbs((o) => ({ ...o, ...t }))).catch(() => {});
  }, [lib, dir]); // eslint-disable-line react-hooks/exhaustive-deps

  const importFiles = useCallback(async (kind: RefKind, paths: string[]) => {
    const ok = paths.filter((p) => IMG_EXT.includes(p.split(".").pop()!.toLowerCase()));
    if (!ok.length) { onError("Use PNG, JPG or WebP images."); return; }
    const rels: string[] = [];
    for (const p of ok) { try { rels.push((await api.importReference(dir, p)).ref.replace(/^project:/, "")); } catch (e) { onError(errorText(e)); } }
    if (!rels.length) return;
    const first = niceName(rels[0]);
    setDraft({ kind, files: rels, name: rels.length > 1 ? "" : first, together: false });
  }, [dir, onError]);

  // drop onto a specific category card
  useEffect(() => {
    const un = getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      const at = (pos?: { x: number; y: number }) => {
        if (!pos) return null;
        const s = window.devicePixelRatio || 1;
        return (Object.entries(cards.current).find(([, el]) => { if (!el) return false; const r = el.getBoundingClientRect();
          return pos.x / s >= r.left && pos.x / s <= r.right && pos.y / s >= r.top && pos.y / s <= r.bottom; })?.[0] ?? null) as RefKind | null;
      };
      if (p.type === "over") setOver(at(p.position));
      else if (p.type === "leave") setOver(null);
      else if (p.type === "drop") { const k = at(p.position) ?? "character"; setOver(null); importFiles(k, p.paths); }
    });
    return () => { un.then((f) => f()); };
  }, [importFiles]);

  const pick = async (kind: RefKind) => {
    const f = await open({ multiple: true, filters: [{ name: "Images", extensions: IMG_EXT }] });
    if (f) importFiles(kind, Array.isArray(f) ? f : [f]);
  };
  const saveDraft = async () => {
    if (!draft) return;
    try {
      if (draft.together || draft.files.length === 1) {
        if (!draft.name.trim()) { onError("Give it a name."); return; }
        await api.library(dir, "upsert", { kind: draft.kind, name: draft.name.trim(), files: draft.files });
      } else {
        for (const f of draft.files) await api.library(dir, "upsert", { kind: draft.kind, name: niceName(f), files: [f] });
      }
      setDraft(null); load();
    } catch (e) { onError(errorText(e)); }
  };

  const items = (k: RefKind) => (lib?.items ?? []).filter((i) => i.kind === k);
  return (
    <div className="wiz-assets">
      {producer && (
        <div className="wiz-tip" role="note">
          <span className="wiz-tip-ic"><I.Sparkle size={18} /></span>
          <div><b>No pictures yet? That is fine.</b>
            <span>This step only uses pictures you bring. To have the cast, props and places <em>designed for you</em> from the song, skip ahead and choose <b>Create the production</b> on the last step.</span></div>
          <button className="btn small" onClick={onSkipToEnd}>Skip to the end <I.ArrowRight size={13} /></button>
        </div>)}
      <div className="wiz-cats">
        {CATS.map((c) => {
          const its = items(c.kind);
          const pics = its.map((i) => thumbs[i.files[0]]).filter(Boolean) as string[];
          return (
            <section key={c.kind} ref={(el) => { cards.current[c.kind] = el; }} className={`wiz-cat ${over === c.kind ? "over" : ""}`} aria-label={c.title}>
              <div className="wiz-cat-head">{c.icon}<h3>{c.title}</h3><span className="num dim">{its.length || ""}</span></div>
              <p className="dim">{c.blurb}</p>
              <button className="wiz-cat-art" onClick={() => its.length ? setOpen(c.kind) : pick(c.kind)} aria-label={its.length ? `Show ${c.title.toLowerCase()}` : c.add}>
                {pics.length ? <>
                  <span className="big" style={{ backgroundImage: `url("${media(dir, pics[0])}")` }} />
                  <span className="row">{pics.slice(1, 5).map((p) => <span key={p} style={{ backgroundImage: `url("${media(dir, p)}")` }} />)}</span>
                </> : <span className="big example" style={{ backgroundImage: `url("onboarding/example_${c.kind}.jpg")` }}><em>Example</em></span>}
              </button>
              <div className="wiz-cat-actions">
                <button className="btn wiz-add" onClick={() => pick(c.kind)}>+ {c.add}</button>
                {its.length > 0 && <button className="icon-btn" onClick={() => setOpen(c.kind)} aria-label={`Manage ${c.title}`}><I.ArrowRight size={16} /></button>}
              </div>
            </section>
          );
        })}
      </div>
      <p className="dim wiz-note">Drop images onto a card, or use its button. Assign references to particular scenes or shots in the Studio's Library once the song is mapped.</p>

      {draft && (
        <div className="overlay" onClick={() => setDraft(null)}>
          <div className="sheet glass" role="dialog" aria-label="Name the reference" onClick={(e) => e.stopPropagation()} style={{ width: "min(520px, calc(100vw - 32px))" }}>
            <h2 style={{ fontSize: 20 }}>{draft.files.length} image{draft.files.length > 1 ? "s" : ""} · {CATS.find((c) => c.kind === draft.kind)!.title}</h2>
            <div className="wiz-draft-thumbs">{draft.files.map((f) => <img key={f} src={media(dir, f)} alt="" />)}</div>
            {draft.files.length > 1 && (
              <label className="wiz-row" style={{ margin: "8px 0" }}><input type="checkbox" checked={draft.together} onChange={(e) => setDraft({ ...draft, together: e.target.checked })} />
                Keep together as one {draft.kind === "character" ? "character (several views of the same person)" : "collection"}</label>
            )}
            {(draft.together || draft.files.length === 1) && <>
              <label className="wiz-label" htmlFor="asset-name">{draft.kind === "character" ? "Character name (as in your script)" : "Name"}</label>
              <input id="asset-name" autoFocus className="text-input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                     onKeyDown={(e) => e.key === "Enter" && saveDraft()} />
            </>}
            {!draft.together && draft.files.length > 1 && <p className="dim">Each image becomes its own {draft.kind === "set" ? "environment" : draft.kind}, named after its file. Rename them any time.</p>}
            <div className="sheet-actions"><button className="btn ghost" onClick={() => setDraft(null)}>Cancel</button>
              <button className="btn primary" onClick={saveDraft}>Add</button></div>
          </div>
        </div>
      )}
      {open_ && lib && <AssetManager dir={dir} kind={open_} items={items(open_)} thumbs={thumbs} onClose={() => setOpen(null)} onChanged={load} onAdd={() => pick(open_)} />}
    </div>
  );
}

function AssetManager({ dir, kind, items, thumbs, onClose, onChanged, onAdd }: {
  dir: string; kind: RefKind; items: RefItem[]; thumbs: Record<string, string | null>; onClose: () => void; onChanged: () => void; onAdd: () => void;
}) {
  const cat = CATS.find((c) => c.kind === kind)!;
  const [edit, setEdit] = useState<Record<string, { name: string; notes: string }>>({});
  const save = async (it: RefItem) => {
    const e = edit[it.id];
    if (!e) return;
    await api.library(dir, "upsert", { id: it.id, kind: it.kind, name: e.name, notes: e.notes, files: it.files });
    setEdit((x) => { const n = { ...x }; delete n[it.id]; return n; }); onChanged();
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass" role="dialog" aria-label={cat.title} onClick={(e) => e.stopPropagation()} style={{ width: "min(760px, calc(100vw - 32px))" }}>
        <div className="vs-head"><h2 style={{ fontSize: 22 }}>{cat.title}</h2><div style={{ flex: 1 }} />
          <button className="btn" onClick={onAdd}>+ {cat.add}</button><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        {items.map((it) => {
          const e = edit[it.id];
          return (
            <div key={it.id} className="lib-item">
              <div className="lib-thumb" style={{ backgroundImage: thumbs[it.files[0]] ? `url("${media(dir, thumbs[it.files[0]]!)}")` : undefined }} />
              <div className="lib-body">
                {e ? <>
                  <input className="text-input" aria-label="Name" value={e.name} onChange={(ev) => setEdit({ ...edit, [it.id]: { ...e, name: ev.target.value } })} />
                  <input className="text-input" aria-label="Notes" placeholder="What to match (optional)" style={{ marginTop: 4 }} value={e.notes}
                         onChange={(ev) => setEdit({ ...edit, [it.id]: { ...e, notes: ev.target.value } })} />
                </> : <><div className="lib-name">{it.name} {it.files.length > 1 && <span className="dim num">· {it.files.length} images</span>}</div>
                  {it.notes && <div className="dim">{it.notes}</div>}</>}
              </div>
              <div className="lib-actions">
                {e ? <button className="btn small primary" onClick={() => save(it)}>Save</button>
                  : <button className="btn ghost small" onClick={() => setEdit({ ...edit, [it.id]: { name: it.name, notes: it.notes ?? "" } })}>Edit</button>}
                <button className="btn ghost small" onClick={async () => { if (await ask(`Remove “${it.name}”? The image stays in the project folder.`)) { await api.library(dir, "delete", { id: it.id }); onChanged(); } }}>Remove</button>
              </div>
            </div>
          );
        })}
        {!items.length && <p className="dim">Nothing here yet.</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 05 choreography

const MODES: { id: NonNullable<Choreography["mode"]>; label: string; hint: string; icon: React.ReactNode }[] = [
  { id: "upload", label: "Upload choreography", hint: "Reference videos or formation images", icon: <I.Upload size={20} /> },
  { id: "written", label: "Write movement notes", hint: "Describe the moves in words", icon: <I.Doc size={20} /> },
  { id: "style", label: "Pick a movement style", hint: "Hip-hop, afrobeats, ballet and more", icon: <I.Dance size={20} /> },
  { id: "ai", label: "Let PULSEFRAME design it", hint: "Designed from the song, section by section", icon: <I.Wand size={20} /> },
  { id: "none", label: "No choreography", hint: "Acting and story only", icon: <I.Close size={20} /> },
];
const CHOREO_EXT = ["pdf", "txt", "md", "docx", "png", "jpg", "jpeg", "jfif", "webp", "gif", "bmp", "mp4", "mov", "m4v", "webm"];

function ChoreoStage({ dir, register, onError }: { dir: string; register: Register; onError: (e: string) => void }) {
  const [c, setC] = useState<Choreography | null>(null);
  const [styles, setStyles] = useState<string[]>([]);
  const [sectionNames, setSectionNames] = useState<string[]>([]);
  const [performers, setPerformers] = useState<string[]>([]);
  const saved = useRef("");
  useEffect(() => {
    api.getChoreography(dir).then((x) => { setC(x); saved.current = JSON.stringify(x); }).catch((e) => onError(errorText(e)));
    api.choreographyStyles().then((s) => setStyles(s.styles)).catch(() => {});
    api.loadProject(dir).then(async (p) => {
      if (p.project.lyrics) {
        const t = await api.readText(`${dir}/${p.project.lyrics}`).catch(() => "");
        setSectionNames([...new Set([...t.matchAll(/^\s*\[([^\]]+)\]\s*$/gm)].map((m) => m[1]))]);
      }
    });
    api.library<Library>(dir, "library").then((l) => setPerformers(l.items.filter((i) => i.kind === "character" && !i.sheet).map((i) => i.name))).catch(() => {});
  }, [dir, onError]);
  const save = useCallback(async () => {
    if (!c) return true;
    const mode = c.mode ?? "none";
    if (JSON.stringify({ ...c, mode }) !== saved.current) { const r = await api.setChoreography(dir, { ...c, mode }); saved.current = JSON.stringify(r); }
    return true;
  }, [c, dir]);
  useEffect(() => { register(save, !!c); }, [save, c]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!c) return <div className="dim">Loading…</div>;
  const set = (patch: Partial<Choreography>) => setC({ ...c, ...patch });
  const addFiles = async () => {
    const f = await open({ multiple: true, filters: [{ name: "Choreography", extensions: CHOREO_EXT }] });
    if (!f) return;
    const rels = [...c.files];
    let notes = c.notes;
    const problems: string[] = [];
    for (const p of Array.isArray(f) ? f : [f]) {
      const name = baseName(p);
      if (/\.(pdf|docx|txt|md)$/i.test(p)) {     // a document: its words become movement notes
        try {
          const d = await api.docText(p);
          notes = `${notes.trim() ? notes.trim() + "\n\n" : ""}From ${d.name}:\n${d.text}`.slice(0, 4000);
          if (d.truncated) problems.push(`${name}: only the first part was added to the notes.`);
        } catch (e) { problems.push(`${name}: ${errorText(e)}`); }
      } else {
        try { rels.push((await api.importReference(dir, p)).ref.replace(/^project:/, "")); }
        catch (e) { problems.push(`${name}: ${errorText(e)}`); }
      }
    }
    set({ files: rels, notes, mode: "upload" });
    if (problems.length) onError(problems.join(" "));
  };

  return (
    <div className="wiz-split">
      <div className="wiz-col">
        <div className="wiz-modes" role="radiogroup" aria-label="How should movement be decided?">
          {MODES.map((m) => <button key={m.id} role="radio" aria-checked={c.mode === m.id} className={c.mode === m.id ? "on" : ""}
                                    onClick={() => set({ mode: m.id })}><span className="wiz-mode-ic">{m.icon}</span><span className="wiz-mode-t"><b>{m.label}</b><small>{m.hint}</small></span></button>)}
        </div>
        {c.mode === "upload" && (
          <div className="wiz-card">
            <div className="wiz-row" style={{ justifyContent: "space-between" }}>
              <span>{c.files.length ? `${c.files.length} file${c.files.length > 1 ? "s" : ""} attached` : "Reference videos, images of formations or counts."}</span>
              <button className="btn primary" onClick={addFiles}><I.Upload size={15} /> Choose files</button></div>
            {c.files.length > 0 && <ul className="wiz-files">{c.files.map((f) => <li key={f}><span>{baseName(f)}</span>
              <button className="link" onClick={() => set({ files: c.files.filter((x) => x !== f) })}>Remove</button></li>)}</ul>}
            <label className="wiz-row" style={{ marginTop: 8 }}><input type="checkbox" checked={c.precise} onChange={(e) => set({ precise: e.target.checked })} />
              These files have exact counts or timestamps</label>
          </div>
        )}
        {(c.mode === "style" || c.mode === "written" || c.mode === "upload" || c.mode === "ai") && (
          <div className="wiz-card">
            <label className="wiz-label" htmlFor="ch-style">Overall style</label>
            <select id="ch-style" className="text-input" value={c.style ?? ""} onChange={(e) => set({ style: e.target.value || null })}>
              <option value="">{c.mode === "ai" ? "Let PULSEFRAME choose from the song" : "No particular style"}</option>
              {styles.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            {c.mode !== "style" && <>
              <label className="wiz-label" htmlFor="ch-notes" style={{ marginTop: 10 }}>{c.mode === "ai" ? "Anything to keep in mind (optional)" : "Movement notes"}</label>
              <textarea id="ch-notes" className="wiz-editor short" value={c.notes} onChange={(e) => set({ notes: e.target.value })}
                        placeholder="e.g. Grounded, restrained moves in the verses; the chorus opens up with the whole crew." />
            </>}
          </div>
        )}
        {(c.mode === "written" || c.mode === "upload") && (
          <div className="wiz-card">
            <div className="wiz-row" style={{ justifyContent: "space-between" }}><b>By section</b>
              <button className="btn small" onClick={() => set({ sections: [...c.sections, { section: sectionNames[0] ?? "Chorus", performers: [], notes: "" }] })}>+ Add a cue</button></div>
            {c.sections.map((s, i) => (
              <div key={i} className="wiz-cue">
                <select aria-label="Section" className="text-input" value={s.section} onChange={(e) => set({ sections: c.sections.map((x, k) => k === i ? { ...x, section: e.target.value } : x) })}>
                  {[...new Set([s.section, ...sectionNames, "Intro", "Verse", "Pre-Chorus", "Chorus", "Bridge", "Outro"])].map((n) => <option key={n}>{n}</option>)}
                </select>
                <select aria-label="Performer" className="text-input" value={s.performers[0] ?? ""} onChange={(e) => set({ sections: c.sections.map((x, k) => k === i ? { ...x, performers: e.target.value ? [e.target.value] : [] } : x) })}>
                  <option value="">Everyone</option>{performers.map((p) => <option key={p}>{p}</option>)}
                </select>
                <input aria-label="Movement" className="text-input" value={s.notes} placeholder="What happens"
                       onChange={(e) => set({ sections: c.sections.map((x, k) => k === i ? { ...x, notes: e.target.value } : x) })} />
                <button className="icon-btn" aria-label="Remove cue" onClick={() => set({ sections: c.sections.filter((_, k) => k !== i) })}><I.Close size={14} /></button>
              </div>
            ))}
          </div>
        )}
        {c.mode === "none" && <div className="wiz-card">The video will rely on acting, story and performance. You can add movement later.</div>}
        <p className="dim wiz-note">AI video follows choreography as direction. It captures style, energy and key moves, not every step exactly.</p>
      </div>
      <figure className="wiz-gallery" aria-label="Illustration">
        <img src="onboarding/choreo_example.jpg" alt="" className="example" />
        <figcaption>Illustration</figcaption>
      </figure>
    </div>
  );
}

// ---------------------------------------------------------------- production review

function ReviewStage({ dir, ob, onEdit, onStart, onProduce, produce, onError }: {
  dir: string; ob: Onboarding; onEdit: (s: WizardStage) => void; onStart: (director: boolean) => Promise<void>; onProduce: () => Promise<void>; produce: boolean; onError: (e: string) => void;
}) {
  const [p, setP] = useState<Awaited<ReturnType<typeof api.loadProject>> | null>(null);
  const [lyrics, setLyrics] = useState("");
  const [script, setScript] = useState("");
  const [lib, setLib] = useState<Library | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [choreo, setChoreo] = useState<Choreography | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.loadProject(dir).then(async (x) => {
      setP(x);
      if (x.project.lyrics) setLyrics(await api.readText(`${dir}/${x.project.lyrics}`).catch(() => ""));
      if (x.project.script === "script.txt") setScript(await api.readText(`${dir}/script.txt`).catch(() => ""));
    }).catch((e) => onError(errorText(e)));
    api.library<Library>(dir, "library").then((l) => { setLib(l); api.thumbs(dir, l.items.map((i) => i.files[0]).filter(Boolean)).then(setThumbs).catch(() => {}); }).catch(() => {});
    api.getChoreography(dir).then(setChoreo).catch(() => {});
  }, [dir, onError]);
  if (!p) return <div className="dim">Gathering your production…</div>;
  const lyricLines = lyrics.split(/\r?\n/).filter((l) => l.trim() && !/^\s*\[.*\]\s*$/.test(l));
  const sections = [...lyrics.matchAll(/^\s*\[([^\]]+)\]\s*$/gm)].map((m) => m[1]);
  const group = (k: RefKind) => (lib?.items ?? []).filter((i) => i.kind === k);
  const start = async (director: boolean) => { setBusy(true); try { await onStart(director); } catch (e) { onError(errorText(e)); setBusy(false); } };
  const makeProduction = async () => { setBusy(true); try { await onProduce(); } catch (e) { onError(errorText(e)); setBusy(false); } };
  const status = (s: WizardStage) => ob.skipped.includes(s) && !ob.done.includes(s) ? "Skipped" : "";

  return (
    <div className="wiz-review">
      <div className="wiz-review-head">
        <div className="wiz-review-eyebrow">Production review</div>
        <h1>{p.project.title}</h1>
        <p className="dim">Everything PULSEFRAME will direct from. Change anything before you start; all of it can also be changed later in the Studio.</p>
      </div>
      <div className="wiz-review-grid">
        <ReviewCard title="Music" required onEdit={() => onEdit("music")}>
          <div className="wiz-mini-wave">{(ob.probe?.peaks ?? []).filter((_, i) => i % 6 === 0).map((v, i) => <i key={i} style={{ height: `${Math.max(6, v * 100)}%` }} />)}</div>
          <b>{ob.song_name ?? p.project.song}</b>
          <span className="dim num">{ob.probe ? fmtTime(ob.probe.duration).slice(0, -3) : ""}{ob.source_video ? " · soundtrack of a video" : ""} · master audio</span>
        </ReviewCard>
        <ReviewCard title="Lyrics" note={status("lyrics")} onEdit={() => onEdit("lyrics")}>
          {lyricLines.length ? <><b>{lyricLines.length} lines{sections.length ? ` · ${sections.length} sections` : ""}</b>
            <span className="dim clamp">{lyricLines.slice(0, 3).join(" / ")}</span></> : <span className="dim">None. Lyrics can also be heard from the vocal when the song is mapped.</span>}
        </ReviewCard>
        <ReviewCard title="Script or treatment" note={status("script")} onEdit={() => onEdit("script")}>
          {p.project.script && p.project.script !== "script.txt" ? <><b>{p.project.script}</b><span className="dim">Uploaded screenplay</span></>
            : script.trim() ? <><b>Pasted script</b><span className="dim clamp">{script.trim().slice(0, 160)}</span></>
            : ob.concept === "propose" ? <><b>Creative directions</b><span className="dim clamp">Three directions proposed after listening{ob.concept_notes ? `: “${ob.concept_notes.slice(0, 90)}”` : ""}</span></>
            : <span className="dim">None. PULSEFRAME will propose creative directions.</span>}
        </ReviewCard>
        {CATS.map((c) => (
          <ReviewCard key={c.kind} title={c.title} note={status("assets")} onEdit={() => onEdit("assets")}>
            {group(c.kind).length ? <>
              <div className="wiz-review-thumbs">{group(c.kind).slice(0, 5).map((i) => <span key={i.id} title={i.name}
                style={{ backgroundImage: thumbs[i.files[0]] ? `url("${media(dir, thumbs[i.files[0]]!)}")` : undefined }} />)}</div>
              <span className="dim">{group(c.kind).map((i) => i.name).slice(0, 4).join(", ")}{group(c.kind).length > 4 ? ` +${group(c.kind).length - 4}` : ""}</span>
            </> : <span className="dim">None{c.kind === "character" ? ". Character images give the most consistent results." : ""}</span>}
          </ReviewCard>
        ))}
        <ReviewCard title="Choreography" note={status("choreography")} onEdit={() => onEdit("choreography")}>
          {choreo?.mode && choreo.mode !== "none" ? <><b>{MODES.find((m) => m.id === choreo.mode)?.label}{choreo.style ? ` · ${choreo.style}` : ""}</b>
            <span className="dim">{[choreo.files.length && `${choreo.files.length} file(s)`, choreo.sections.length && `${choreo.sections.length} section cue(s)`, choreo.notes && "notes"].filter(Boolean).join(" · ") || "Style only"}</span></>
            : <span className="dim">None: acting and performance led.</span>}
        </ReviewCard>
        <RenderChoice dir={dir} />
        <ReviewCard title="Project settings">
          <b>{p.project.aspect_ratio ?? "16:9"} · {p.project.quality ?? "standard"} quality</b>
          <span className="dim">Look: {typeof p.project.look === "object" ? (p.project.look.style === "auto" ? "Auto, matches your references" : p.project.look.style) : "Auto"} · change in the Studio</span>
        </ReviewCard>
      </div>
      <div className="wiz-review-actions">
        {(() => {
          const options = [
            { id: "direct", icon: <I.Clapper size={20} />, title: "Direct my video", text: "Quickest. The Director proposes looks from your song and writes the shot list; you work in Simple mode.", go: () => start(false) },
            { id: "produce", icon: <I.Sparkle size={20} />, title: "Create the production with AI", text: "Fullest. The Producer designs the cast, outfits, props, places and dance, then you approve each step and make the pictures.", go: makeProduction },
            { id: "manual", icon: <I.Sliders size={20} />, title: "Open Director Mode", text: "Hands-on. The same project with every model setting and reference visible. Nothing is planned for you.", go: () => start(true) },
          ];
          const order = produce ? ["produce", "direct", "manual"] : ["direct", "produce", "manual"];
          return <div className="wiz-paths" role="group" aria-label="How do you want to continue?">
            {order.map((id, k) => { const o = options.find((x) => x.id === id)!;
              return <button key={id} className={`wiz-path ${k === 0 ? "main" : ""}`} disabled={busy} onClick={o.go}>
                <span className="wiz-path-ic">{o.icon}</span><span className="wiz-path-t"><b>{o.title}</b><small>{o.text}</small></span><I.ArrowRight size={16} /></button>; })}
          </div>;
        })()}
        <p className="dim">{produce ? "The Producer plans your cast, outfits, props, places, movement and every shot, and you approve each step. "
          : "All three open this same project. Create the production plans the whole cast, props, places and shots for you, step by step. Director Mode shows every model setting and reference. "}
          PULSEFRAME first listens to the song (free, on this computer); nothing is rendered or billed until you confirm a price.</p>
      </div>
    </div>
  );
}

function ReviewCard({ title, required, note, onEdit, children }: { title: string; required?: boolean; note?: string; onEdit?: () => void; children: React.ReactNode }) {
  return (
    <section className="wiz-rcard" aria-label={title}>
      <div className="wiz-rcard-head"><h3>{title}</h3>{required && <span className="mat-need required">required</span>}
        {note && <span className="dim" style={{ fontSize: 11 }}>{note}</span>}<div style={{ flex: 1 }} />
        {onEdit && <button className="link" onClick={onEdit}>Edit</button>}</div>
      <div className="wiz-rcard-body">{children}</div>
    </section>
  );
}

/** Review step: where the renders happen, starting with "free on my computer" (ComfyUI). */
function RenderChoice({ dir }: { dir: string }) {
  const [mode, setMode] = useState<string>("");
  const [comfy, setComfy] = useState<"unknown" | "looking" | "ready" | "partial" | "missing">("unknown");
  const [note, setNote] = useState("");
  useEffect(() => { api.routing<{ mode: string; chosen: boolean }>(dir, "status").then((r) => setMode(r.chosen ? r.mode : "")).catch(() => {}); }, [dir]);
  const set = async (m: string) => { setMode(m); await api.routing(dir, "set", { mode: m }).catch(() => {}); if (m === "local" && comfy === "unknown") find(); };
  const find = async () => {
    setComfy("looking"); setNote("");
    try {
      const f = await api.comfySetup<{ running: { url: string }[]; installs: { kind: string }[] }>("detect");
      if (!f.running.length) { setComfy("missing"); setNote(f.installs.length ? `${f.installs[0].kind} is installed but not running: start it, then look again.` : "ComfyUI isn't on this computer. It's free from comfy.org (ComfyUI Desktop)."); return; }
      const r = await api.comfySetup<{ templates: { kind: string; ready: boolean; missing: string[] }[] }>("setup", { url: f.running[0].url });
      const ok = r.templates.filter((t) => t.ready).length;
      setComfy(ok === r.templates.length ? "ready" : "partial");
      setNote(ok === r.templates.length ? "Found and set up: keyframes and video render free on this computer." :
        `Found. Still to download in ComfyUI: ${r.templates.filter((t) => !t.ready).flatMap((t) => t.missing).join("; ")}`);
    } catch { setComfy("missing"); setNote("Couldn't check for ComfyUI."); }
  };
  const OPTS = [
    { id: "local", label: "Free on my computer", sub: "ComfyUI on your graphics card. No bills; slower, softer video." },
    { id: "cheapest", label: "Cheapest cloud", sub: "Lowest real price per shot (often cents)." },
    { id: "balanced", label: "Balanced", sub: "Good quality at a modest price." },
    { id: "premium", label: "Premium", sub: "The best models. Costs the most." },
  ];
  return (
    <div className="wiz-card wiz-render-choice">
      <div className="wiz-label">How it renders</div>
      <div className="wrc-grid">{OPTS.map((o) => (
        <button key={o.id} className={`wrc ${mode === o.id ? "on" : ""}`} onClick={() => set(o.id)}><b>{o.label}</b><span>{o.sub}</span></button>))}</div>
      {mode === "local" && <div className="wrc-note">
        {comfy === "looking" ? "Looking for ComfyUI…" : note || "PULSEFRAME will look for ComfyUI on this computer."}
        {comfy !== "looking" && comfy !== "ready" && <button className="link" onClick={find}> Look again</button>}</div>}
      {mode && mode !== "local" && <details className="wrc-models">
        <summary>Choose your picture model and video model <span className="dim">(optional)</span></summary>
        <p className="dim">Each model has its own strengths. Choosing one fixes it for the whole project, which keeps your characters looking the same in every picture. If you are not sure, leave both on <b>Let PULSEFRAME choose</b>.</p>
        <h4>Pictures</h4>
        <ModelChoice dir={dir} kind="image" />
        <h4>Video</h4>
        <ModelChoice dir={dir} kind="video" />
      </details>}
      <span className="dim">You can change this any time in the Studio (Plan & budget). Nothing is billed until you confirm a price.</span>
    </div>
  );
}
