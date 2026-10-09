import { SHORTCUTS, GROUPS, find as findShortcut, isTyping } from "./shortcuts";
import { KeyframeTools } from "./KeyframeTools";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toggleShotSound } from "./ShotSound";
import { Palette, type Command } from "./Palette";
import { PlayerOverlays } from "./PlayerOverlays";
import { api, errorText, fmtTime, type BoardShot, type EngineEvent, type LoadedProject, type Plan, type Scene, type Shot, type SongMap } from "./api";
import * as I from "./icons";
import { ACTIVE_STATES, ConfirmRender, defaultProvider, JobChip, latestJobs, RenderPanel } from "./Render";
import { AUTO_MODEL, type Job, type KeyStatus, type Overlay, type ShotHistory } from "./api";
import { ExportSheet } from "./Export";
import { ShotCamera } from "./Camera";
import { LookPicker, lookName, normalizeLook, useStyles } from "./Looks";
import { needsAttention, ReviewSheet } from "./Review";
import { ComposeTab } from "./Compose";
import { LightingSheet } from "./Lighting";
import { readFlag, writeFlag } from "./panelState";
import { attentionStarts, COMPACT_HEIGHT, HEIGHT_MAX, HEIGHT_MIN, PPS_MAX, PPS_MIN, readLayout, stepAttention, writeLayout } from "./timelineView";
import { QueueChip, RenderQueueSheet, useQueue } from "./RenderQueue";
import { batchOutcome } from "./queueMath";
import { KeyframePanel } from "./Keyframe";
import { addMediaToTimeline, OwnMediaPanel, StillPreview } from "./OwnMedia";
import { ContinuitySheet, ShotContinuity } from "./Continuity";
import { PerformanceSheet, ShotPerformance } from "./Performance";
import { RouteChip, RoutingSheet, useRouting } from "./Routing";
import { GoldenStrip } from "./GoldenStrip";
import { pickTestShot } from "./testShot";
import { Tour, tourSeen } from "./Tour";
import { ShotRefs } from "./ShotRefs";
import { SupervisorSheet } from "./Supervisor";
import { CleanupSheet } from "./Cleanup";
import { InsertFrameSheet } from "./InsertFrame";
import { LayersPanel } from "./Layers";
import { LayerStrip } from "./LayerStrip";
import { LayerLanes, LANE_H } from "./LayerLanes";
import { UpscaleSheet, type UpscaleRequest } from "./UpscaleSheet";
import { TransitionHandles } from "./TransitionHandles";
import { snapPoints } from "./laneMath";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { PreviewSheet } from "./PreviewSheet";
import { ColourMatchSheet } from "./ColourMatch";
import { beatGrid } from "./overlayMotion";
import { UpgradePanel } from "./Upgrade";
import { DirectionLibrarySheet } from "./DirectionLibrary";
import { CreativeDirections } from "./Directions";
import { CommandToast, DirectorCommand, type CommandResult } from "./Command";
import { MaterialsPanel } from "./Materials";
import { ApproveKeyframes, LibrarySheet, ShotViewer, StoryCards, useBoard } from "./Board";
import { SelectReview } from "./SelectReview";
import { ScriptSheet } from "./ScriptSheet";
import { Autopilot } from "./Autopilot";
import { Cta, DockCtx } from "./Dock";
import { ASPECTS, aspectCss, PROJECT_EVENT, QUALITY, saveFrame } from "./frame";
import { ask } from "./ask";

type Selection = { kind: "shot"; id: string } | { kind: "section"; index: number } | null;

export function Studio({ project, onHome, onSettings, onReload, onProduce }: {
  project: LoadedProject; onHome: () => void; onSettings: () => void; onReload: () => void; onProduce?: () => void;
}) {
  const map = project.song_map;
  const plan: Plan | null = project.directed ?? project.production;
  const scenes = plan?.scenes ?? [];
  const shots = useMemo(() => scenes.flatMap((s) => s.shots), [scenes]);
  // The project's shape and quality, kept live so every panel (and the preview boxes) follow a change the moment it is made.
  const [frame, setFrame] = useState({ aspect_ratio: project.project.aspect_ratio ?? "16:9", quality: project.project.quality ?? "standard" });
  useEffect(() => { setFrame({ aspect_ratio: project.project.aspect_ratio ?? "16:9", quality: project.project.quality ?? "standard" }); }, [project.dir]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const h = (e: Event) => setFrame((f) => ({ ...f, ...(e as CustomEvent).detail }));
    window.addEventListener(PROJECT_EVENT, h);
    return () => window.removeEventListener(PROJECT_EVENT, h);
  }, []);

  const audio = useRef<HTMLAudioElement | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(() => { try { const v = Number(localStorage.getItem("pf-volume")); return Number.isFinite(v) && localStorage.getItem("pf-volume") !== null ? v : 0.9; } catch { return 0.9; } });
  const [muted, setMuted] = useState(false);
  const [songError, setSongError] = useState("");
  const [sel, setSel] = useState<Selection>(null);
  // Production Review's "Open Director Mode" (read once for this project)
  const [director, setDirector] = useState(() => {
    try { const k = `pf-open-director:${project.dir}`; const v = localStorage.getItem(k) === "1"; localStorage.removeItem(k); return v; } catch { return false; }
  });
  const [inspector, setInspector] = useState(true);
  const [timelineOpen, setTimelineOpenState] = useState(() => readFlag("pf-timeline", true));     // the timeline can be put away to give the video the room; remembered
  const setTimelineOpen = (v: boolean | ((x: boolean) => boolean)) => setTimelineOpenState((cur) => { const n = typeof v === "function" ? v(cur) : v; writeFlag("pf-timeline", n); return n; });
  const needsRef = useRef<ReadonlySet<string>>(new Set());                                  // the shots that need a look, for the key handler
  const [tlCompact, setTlCompactState] = useState(() => !!readLayout(project.dir).compact);     // compact timeline, remembered for this project
  const setTlCompact = (v: boolean | ((x: boolean) => boolean)) => setTlCompactState((cur) => { const n = typeof v === "function" ? v(cur) : v; writeLayout(project.dir, { compact: n }); return n; });
  const [job, setJob] = useState<{ title: string; detail: string } | null>(null);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Job[]>(project.jobs ?? []);
  const [keys, setKeys] = useState<KeyStatus>({ openai: false, fal: false, kie: false, google: false, elevenlabs: false });
  const [confirmAll, setConfirmAll] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lookOpen, setLookOpen] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);
  const [lightOpen, setLightOpen] = useState(false);
  useEffect(() => { const h = () => setLightOpen(true); window.addEventListener("pf-open-lighting", h); return () => window.removeEventListener("pf-open-lighting", h); }, []);
  const [batch, setBatch] = useState<{ text: string; failed: number } | null>(null);
  const [commanding, setCommanding] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cmdResult, setCmdResult] = useState<CommandResult | null>(null);
  const [keyframes, setKeyframes] = useState<Record<string, Record<string, string>>>(project.keyframes ?? {});
  const [look, setLook] = useState(normalizeLook(project.project.look));
  const [viewing, setViewing] = useState<string | null>(null);
  // right after a production is built, "Make the pictures" opens the Library on the picture maker (once)
  const openMake = useMemo(() => { try { const k = `pf-open-refgen:${project.dir}`; const on = localStorage.getItem(k) === "1"; if (on) localStorage.removeItem(k); return on; } catch { return false; } }, [project.dir]);
  const [libraryOpen, setLibraryOpen] = useState(openMake);
  const [scriptOpen, setScriptOpen] = useState(false);
  const [inspW, setInspW] = useState(() => { try { return Math.min(720, Math.max(320, Number(localStorage.getItem("pf-insp-w")) || 400)); } catch { return 400; } });
  const inspRef = useRef(inspW); inspRef.current = inspW;
  const dragInspector = (e: React.PointerEvent) => {
    const x0 = e.clientX, w0 = inspW;
    const move = (ev: PointerEvent) => setInspW(Math.min(720, Math.max(320, w0 + (x0 - ev.clientX))));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      try { localStorage.setItem("pf-insp-w", String(Math.round(inspRef.current))); } catch { /* optional */ } };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const [contOpen, setContOpen] = useState(false);
  const [perfOpen, setPerfOpen] = useState(false);
  const [routeOpen, setRouteOpen] = useState(false);
  const [kfTools, setKfTools] = useState(false);                       // Keyframe tools: check hands in every keyframe, redo on one picture model
  useEffect(() => {                                                    // a panel asks to be shown where a layer is: open the timeline and go there
    const show = () => setTimelineOpen(true);
    const go = (e: Event) => { const t = Number((e as CustomEvent<number>).detail); if (Number.isFinite(t)) seek(t); };
    window.addEventListener("pf-show-timeline", show); window.addEventListener("pf-seek", go);
    return () => { window.removeEventListener("pf-show-timeline", show); window.removeEventListener("pf-seek", go); };
  });   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const on = () => setKfTools(true); window.addEventListener("pf-open-keyframe-tools", on); return () => window.removeEventListener("pf-open-keyframe-tools", on); }, []);
  const [supOpen, setSupOpen] = useState(false);
  const [cleanOpen, setCleanOpen] = useState(false);
  const [frameOpen, setFrameOpen] = useState(false);
  const [upscaling, setUpscaling] = useState<UpscaleRequest | null>(null);
  useEffect(() => { const on = (e: Event) => setUpscaling((e as CustomEvent<UpscaleRequest>).detail); window.addEventListener("pf-open-upscale", on); return () => window.removeEventListener("pf-open-upscale", on); }, []);
  const barRef = useRef<HTMLElement | null>(null);
  const narrowWindow = useNarrow(1320);
  const [moreOpen, setMoreOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  useEffect(() => { if (layersOpen) setInspector(true); }, [layersOpen]);   // the panel lives in the inspector column, so open it
  const [previewOpen, setPreviewOpen] = useState(false);
  const [colourOpen, setColourOpen] = useState(false);
  const [layerSel, setLayerSel] = useState<string | null>(null);
  const [focusLayer, setFocusLayer] = useState<Overlay | null>(null);
  const [focus, setFocus] = useState(false);
  const [keysHelp, setKeysHelp] = useState(false);
  const [rerender, setRerender] = useState<string | null>(null);
  const [night, setNight] = useState<{ active?: boolean; ready?: boolean; shots?: number; with_video?: number; export?: string | null; finished?: number | null; comfy_video?: string } | null>(null);
  const [toastMsg, setToastMsg] = useState("");
  const say = (t: string) => { setToastMsg(t); window.setTimeout(() => setToastMsg(""), 2600); };
  // Undo for changes to a shot (approve, keyframe, end frame, motion, lock): the engine keeps the journal; this offers it
  const [hist, setHist] = useState<ShotHistory | null>(null);
  const [undoOffer, setUndoOffer] = useState<string | null>(null);
  const [histTick, setHistTick] = useState(0);
  const seenHist = useRef<Set<string> | null>(null);                                                  // changes already seen, so only a new one is offered
  const offerTimer = useRef<number | undefined>(undefined);
  const quickApprove = async (id: string) => {   // A: approve this shot's waiting keyframe, or its newest take
    try {
      if (pendingKf[id]) { await api.library(project.dir, "approve_keyframes", { shots: [id] }); say(`Keyframe approved for ${id}`); }
      else { const t = latest.get(id); if (t?.state === "ready") { await api.library(project.dir, "approve", { shot: id, job: t.id }); say(`Take approved for ${id}`); } else say(`${id} has nothing new to approve`); }
      mediaChanged();
    } catch (e) { say(errorText(e)); }
  };
  useEffect(() => {   // automatic backups: on open, then every 10 minutes (skipped when nothing changed)
    const snap = () => api.backups(project.dir, "backup", "auto").catch(() => {});
    snap();
    const t = setInterval(snap, 10 * 60_000);
    return () => clearInterval(t);
  }, [project.dir]);
  useEffect(() => {   // overnight status: poll while it runs
    let alive = true;
    const pull = () => api.overnight<typeof night>(project.dir, "status").then((s) => alive && setNight(s)).catch(() => {});
    pull(); const t = window.setInterval(pull, 20000);
    return () => { alive = false; window.clearInterval(t); };
  }, [project.dir]);   // eslint-disable-line react-hooks/exhaustive-deps
  const setFocusMode = useCallback(async (on: boolean) => {
    setFocus(on);
    try { const { getCurrentWindow } = await import("@tauri-apps/api/window"); await getCurrentWindow().setFullscreen(on); } catch { /* browser preview */ }
  }, []);
  const [dlOpen, setDlOpen] = useState(false);
  useEffect(() => { const f = () => setDlOpen(true); window.addEventListener("pf-open-directions", f); return () => window.removeEventListener("pf-open-directions", f); }, []);
  useEffect(() => { const f = () => setSupOpen(true); window.addEventListener("pf-open-supervisor", f); return () => window.removeEventListener("pf-open-supervisor", f); }, []);
  const { route } = useRouting(project.dir);
  // Autopilot: from the top bar, or straight after the setup wizard's "Direct my video"
  const [autopilot, setAutopilot] = useState(() => {
    try { const k = `pf-autopilot:${project.dir}`; const v = localStorage.getItem(k) === "1"; localStorage.removeItem(k); return v; } catch { return false; }
  });
  useEffect(() => {
    const on = () => setAutopilot(true);
    window.addEventListener("pf-open-autopilot", on);
    return () => window.removeEventListener("pf-open-autopilot", on);
  }, []);
  useEffect(() => {
    const on = () => setScriptOpen(true);
    window.addEventListener("pf-open-script", on);
    return () => window.removeEventListener("pf-open-script", on);
  }, []);
  const [pendingKf, setPendingKf] = useState<Record<string, string>>({});
  const [approvingKf, setApprovingKf] = useState(false);
  const styles = useStyles();
  // Studio-level File/View menu items.
  useEffect(() => {
    const on = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      if (id === "export" && plan) setExporting(true);
      if (id === "mode_simple") setDirector(false);
      if (id === "mode_director") setDirector(true);
      if (id === "inspector") setInspector((v) => !v);
      if (id === "command" && plan) setCommanding(true);
    };
    window.addEventListener("pf-menu", on);
    return () => window.removeEventListener("pf-menu", on);
  }, [plan]);
  const saveLook = async (l: typeof look) => {
    setLookOpen(false);
    try { await api.setLook(project.dir, l); setLook(l); } catch (e) { setError(errorText(e)); }
  };
  const planName = project.directed ? "directed" : "production";
  const [tourOpen, setTourOpen] = useState(() => !tourSeen());
  const latest = useMemo(() => latestJobs(jobs, planName), [jobs, planName]);
  // Review judges the newest finished take of each shot (a newer failed attempt doesn't hide it).
  const takes = useMemo(() => latestJobs(jobs.filter((j) => j.state === "ready"), planName), [jobs, planName]);
  const { board, reload: reloadBoard, thumbs, want } = useBoard(project.dir, jobs);
  const refreshPendingKf = useCallback(() => {  // new keyframes waiting for approval
    api.library<Record<string, string>>(project.dir, "pending_keyframes").then((r) => setPendingKf(r ?? {})).catch(() => {});
  }, [project.dir]);
  useEffect(() => { refreshPendingKf(); }, [refreshPendingKf, board]);
  const mediaChanged = useCallback(() => {
    api.loadProject(project.dir).then((p) => { if (p.jobs) mergeJobs(p.jobs); if (p.keyframes) setKeyframes(p.keyframes); }).catch(() => {});
    reloadBoard(); refreshPendingKf();
  }, [project.dir, reloadBoard, refreshPendingKf]);   // eslint-disable-line react-hooks/exhaustive-deps
  const afterHistory = useCallback(() => {
    reloadBoard(); mediaChanged(); setHistTick((t) => t + 1);
    api.loadProject(project.dir).then((p) => { if (p.keyframes) setKeyframes(p.keyframes); }).catch(() => {});
    window.dispatchEvent(new Event("pf-media-changed"));
  }, [project.dir, reloadBoard, mediaChanged]);   // eslint-disable-line react-hooks/exhaustive-deps
  const loadHist = useCallback((offer: boolean) => {
    api.shotHistory(project.dir, "list").then((h) => {
      setHist(h);
      const seen = seenHist.current;
      const fresh = seen ? h.undo.filter((e) => !seen.has(e.id)) : [];
      seenHist.current = new Set([...(seen ?? []), ...h.undo.map((e) => e.id)]);
      if (offer && fresh.length) {
        setUndoOffer(fresh[0].label);
        window.clearTimeout(offerTimer.current);
        offerTimer.current = window.setTimeout(() => setUndoOffer(null), 8000);
      }
    }).catch(() => {});
  }, [project.dir]);
  useEffect(() => { seenHist.current = null; loadHist(false); const on = () => loadHist(true); window.addEventListener("pf-shot-changed", on); return () => window.removeEventListener("pf-shot-changed", on); }, [loadHist]);
  const stepHist = (which: "undo" | "redo") => {
    setUndoOffer(null);
    api.shotHistory(project.dir, which).then((h) => { setHist(h); seenHist.current = new Set([...(seenHist.current ?? []), ...h.undo.map((e) => e.id)]); say(`${which === "undo" ? "Undone" : "Redone"}: ${h.label ?? "change"}`); afterHistory(); }).catch((err) => say(errorText(err)));
  };
  const [mediaNote, setMediaNote] = useState("");
  const [mediaMenu, setMediaMenu] = useState(false);
  const stillable = (board?.shots ?? []).filter((b) => b.keyframe && !b.preview && !b.locked).length;
  const boardShot = useMemo(() => new Map((board?.shots ?? []).map((b) => [b.id, b])), [board]);

  const queue = useQueue(jobs);
  const prevActive = useRef(0), batchSince = useRef(0);
  useEffect(() => {   // when a run of renders settles, say so and say what came out (also if the window was in the background)
    if (queue.active > 0 && prevActive.current === 0) batchSince.current = Math.floor(Date.now() / 1000) - 5;
    if (queue.active === 0 && prevActive.current > 0 && batchSince.current) {
      const o = batchOutcome(jobs, batchSince.current);
      setBatch({ text: o.text, failed: o.failed });
      batchSince.current = 0;
    }
    prevActive.current = queue.active;
  }, [queue.active]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!batch) return; const t = setTimeout(() => setBatch(null), 25000); return () => clearTimeout(t); }, [batch]);

  const mergeJobs = useCallback((incoming: Job[]) => setJobs((cur) => {
    const byId = new Map(cur.map((j) => [j.id, j]));
    for (const j of incoming) byId.set(j.id, { ...byId.get(j.id), ...j });
    return [...byId.values()];
  }), []);

  useEffect(() => {
    let alive = true;
    const pull = () => { if (document.visibilityState === "visible") api.loadProject(project.dir).then((p) => alive && p.jobs && mergeJobs(p.jobs)).catch(() => {}); };
    const t = window.setInterval(pull, 8000);
    window.addEventListener("focus", pull);
    return () => { alive = false; window.clearInterval(t); window.removeEventListener("focus", pull); };
  }, [project.dir, mergeJobs]);

  useEffect(() => {
    const refresh = () => api.keyStatus().then(setKeys).catch(() => {});
    refresh();
    window.addEventListener("pf-keys-changed", refresh);
    // Reconnect to renders that were running when the app closed (PRD §29).
    if ((project.jobs ?? []).some((j) => ACTIVE_STATES.includes(j.state))) api.ensureRenderer(project.dir);
    const un = api.onEngine((e) => { if (e.event === "job" && e.job) mergeJobs([e.job as Job]); });
    return () => { window.removeEventListener("pf-keys-changed", refresh); un.then((f) => f()); };
  }, [project.dir, project.jobs, mergeJobs]);

  useEffect(() => {
    if (!project.song_path) return;
    const a = new Audio(api.mediaUrl(project.song_path));
    a.preload = "auto";
    audio.current = a;
    a.onended = () => setPlaying(false);
    a.onerror = () => setSongError("The song file can't be played. It may have been moved or deleted from the project folder.");
    a.oncanplay = () => setSongError("");
    return () => { a.pause(); audio.current = null; };
  }, [project.song_path]);

  useEffect(() => {
    if (audio.current) audio.current.volume = muted ? 0 : volume;
    try { localStorage.setItem("pf-volume", String(volume)); } catch { /* optional */ }
  }, [volume, muted, project.song_path]);

  useEffect(() => {
    let raf = 0;
    const tick = () => { if (audio.current) setTime(audio.current.currentTime); raf = requestAnimationFrame(tick); };
    if (playing) raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const toggle = useCallback(() => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) {
      a.play().then(() => setPlaying(true)).catch((e) => {
        setPlaying(false);
        setSongError(a.error ? "The song file can't be played. It may have been moved or deleted from the project folder." : `Couldn't start playback: ${e?.message ?? e}`);
      });
    } else { a.pause(); setPlaying(false); }
  }, []);
  const seek = useCallback((t: number) => {
    const a = audio.current;
    const c = Math.max(0, Math.min(t, map?.duration ?? 0));
    if (a) a.currentTime = c;
    setTime(c);
  }, [map]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const typing = isTyping(e.target);
      const el = e.target as HTMLElement;
      const hit = findShortcut(e, { typing });
      if (e.key === "Escape" && focus) { setFocusMode(false); return; }
      if (!hit) return;
      // Space (and Enter) on a focused button or link belongs to that control, so keyboard users can press it
      if (e.code === "Space" && /^(BUTTON|A|SUMMARY)$/.test(el.tagName)) return;
      e.preventDefault();
      const starts = shots.map((s) => s.start).sort((a, b) => a - b);
      const cur = shots.find((s) => time >= s.start && time < s.end);
      switch (hit.id) {
        case "command": if (plan) setCommanding(true); break;
        case "play": case "play_k": toggle(); break;
        case "mute": setMuted((m) => !m); break;
        case "focus": setFocusMode(!focus); break;
        case "back5": case "back5s": seek(time - 5); break;
        case "fwd5": case "fwd5s": seek(time + 5); break;
        case "start": seek(0); break;
        case "end": seek(map?.duration ?? 0); break;
        case "prev": { const prev = [...starts].reverse().find((t) => t < time - 0.25); seek(prev ?? 0); break; }
        case "next": { const next = starts.find((t) => t > time + 0.05); if (next !== undefined) seek(next); break; }
        case "prev_flag": case "next_flag": {
          const t = stepAttention(attentionStarts(shots, needsRef.current), time, hit.id === "next_flag" ? 1 : -1);
          if (t === null) say(hit.id === "next_flag" ? "No later shot needs attention." : "No earlier shot needs attention."); else seek(t);
          break;
        }
        case "undo_shot": case "redo_shot": stepHist(hit.id === "undo_shot" ? "undo" : "redo"); break;
        case "approve": if (cur) quickApprove(cur.id); break;
        case "frames": if (cur) { setSel({ kind: "shot", id: cur.id }); setInspector(true); setTimeout(() => window.dispatchEvent(new CustomEvent("pf-open-tab", { detail: "frames" })), 50); } break;
        case "rerender": if (cur) { setSel({ kind: "shot", id: cur.id }); setInspector(true); setRerender(cur.id); } break;
        case "layers": if (plan) setLayersOpen((v) => !v); break;
        case "add_text": if (plan) api.overlays(project.dir, "add", { kind: "text", text: "Your text", y: 0.5, anim: "rise", start: Math.max(0, Math.floor(time * 10) / 10), end: Math.min(map?.duration ?? time + 4, Math.max(0, Math.floor(time * 10) / 10) + 4) })
          .then((r) => { window.dispatchEvent(new Event("pf-overlays-changed")); setLayerSel(r[r.length - 1]?.id ?? null); setLayersOpen(true); }).catch((err) => say(errorText(err))); break;
        case "hide_layer": if (layerSel) api.overlays<Overlay[]>(project.dir, "list").then((all) => { const o = all.find((x) => x.id === layerSel); return o ? api.overlays(project.dir, "update", { id: o.id, enabled: !o.enabled }) : null; })
          .then(() => window.dispatchEvent(new Event("pf-overlays-changed"))).catch((err) => say(errorText(err))); break;
        case "keys": setKeysHelp((v) => !v); break;
        case "timeline": setTimelineOpen((v) => !v); break;
        case "timeline_compact": if (timelineOpen) setTlCompact((v) => !v); break;
        case "palette": setPaletteOpen((v) => !v); break;
        case "undo": case "redo": case "redo_y": if (layersOpen) window.dispatchEvent(new CustomEvent("pf-layers-history", { detail: hit.id === "undo" ? "undo" : "redo" })); else e.preventDefault(); break;
        case "shot_sound": if (cur) toggleShotSound(project.dir, cur.id).then((m) => { say(m); window.dispatchEvent(new Event("pf-media-changed")); }).catch((err) => say(errorText(err))); break;
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [toggle, seek, time, focus, setFocusMode, shots, map, plan, layersOpen, layerSel]);   // eslint-disable-line react-hooks/exhaustive-deps

  const current = shots.find((s) => time >= s.start && time < s.end) ?? null;
  const shown = sel?.kind === "shot" ? shots.find((s) => s.id === sel.id) ?? current : current;
  // the player's caption follows your edits (Export > Lyric captions): changed wording, hidden lines
  const [capLines, setCapLines] = useState<{ text: string; start: number; end: number; hidden: boolean }[]>([]);
  useEffect(() => {
    const pull = () => api.captions(project.dir, "get").then((c) => setCapLines(c.lines)).catch(() => setCapLines([]));
    pull();
    window.addEventListener("pf-captions-changed", pull);
    return () => window.removeEventListener("pf-captions-changed", pull);
  }, [project.dir, map]);
  const lyric = capLines.length
    ? capLines.find((l) => !l.hidden && time >= l.start && time <= l.end)
    : map?.lyrics.find((l) => l.start != null && l.end != null && time >= l.start && time <= l.end + 0.3);

  const directVideo = async () => {
    if (!(await api.aiReady())) { onSettings(); return; }
    setError("");
    setJob({ title: "Directing", detail: "Reading the script" });
    const un = await api.onEngine((e: EngineEvent) => {
      if (e.task === "director" && e.stage) setJob({ title: "Directing", detail: capital(e.stage) });
    });
    try { await api.directProject(project.dir); onReload(); }
    catch (e) { setError(errorText(e)); }
    finally { un(); setJob(null); }
  };

  const needsLook = new Set(shots.filter((s) => (s.flags?.length ?? 0) > 0 || needsAttention(latest.get(s.id)) || boardShot.get(s.id)?.keyframe_check === "fail").map((s) => s.id));
  needsRef.current = needsLook;
  const flagged = needsLook.size;
  // shots cut from the song alone have nothing described to render yet
  const described = (s: Shot) => !!((s as { visual_prompt?: string }).visual_prompt || s.beats?.length || (s as { description?: string }).description);
  const toRender = shots.filter((s) => { const j = latest.get(s.id); return (!j || j.state === "failed") && described(s); });
  const folded = useBarFold(barRef, [director, !!night?.active, Object.keys(pendingKf).length, shots.length, !!plan, project.directed, keys.fal, keys.kie, inspector, toRender.length]);
  const narrowBar = narrowWindow || folded;
  const renderAll = async () => {
    setConfirmAll(false);
    // the project's mode decides Auto (Local First: ComfyUI; Balanced: cheapest; Premium: best)
    const provider = route?.video.provider ?? defaultProvider(keys);
    const model = route?.video.provider ? route.video.model! : AUTO_MODEL[provider];
    if (route?.mode === "local" && !route.video.provider) { setError(route.video.reason ?? "Local First: nothing to render with."); return; }
    try { mergeJobs(await api.queueRender(project.dir, toRender.map((s) => s.id), provider, model, {})); }
    catch (e) { setError(errorText(e)); }
  };

  return (
    <div className={`studio ${focus ? "focus" : ""}`}>
      {focus && <button className="btn ghost focus-exit" onClick={() => setFocusMode(false)}>Exit full screen (Esc)</button>}
      <nav className="rail" aria-label="Main">
        <div className="logo"><I.Mark size={26} /></div>
        <RailBtn icon={<I.Home />} label="Home" onClick={onHome} />
        <RailBtn icon={<I.Folder />} label="Project" onClick={() => { setSel(null); setInspector(true); }} />
        <RailBtn icon={<I.Assets />} label="Library" onClick={() => setLibraryOpen(true)} />
        <RailBtn icon={<I.Studio />} label="Studio" active />
        <RailBtn icon={<I.Mountain />} label="Directions" onClick={() => setDlOpen(true)} />
        <RailBtn icon={<I.Wand />} label="Supervisor" onClick={() => setSupOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.User />} label="Acting" onClick={() => setPerfOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Film />} label="Continuity" onClick={() => setContOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Review />} label="Review" onClick={() => setReviewing(true)} disabled={!plan}
                 badge={shots.filter((s) => needsAttention(takes.get(s.id))).length} />
        <RailBtn icon={<I.Export />} label="Export" onClick={() => setExporting(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Layers />} label="Layers" onClick={() => setLayersOpen((v) => !v)} active={layersOpen} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Light />} label="Lighting" onClick={() => setLightOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Lens />} label="Colour match" onClick={() => setColourOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <RailBtn icon={<I.Trash />} label="Clean up" onClick={() => setCleanOpen(true)} disabled={!plan} why="Needs a shot plan first: press Direct My Video." />
        <div className="spacer" />
        <RailBtn icon={<I.Gear />} label="Settings" onClick={onSettings} />
      </nav>

      <main className="center">
        <header className="topbar" ref={barRef}>
          <div>
            <div className="title">{project.project.title}</div>
            {map && <div className="meta num">{Math.round(map.bpm)} BPM · {fmtTime(map.duration)} · {shots.length} shots
              {project.directed ? " · Directed" : plan ? " · Planned from script" : ""}</div>}
          </div>
          <div className="grow" />
          <div className="mode-toggle" role="group" aria-label="Mode">
            <button className={!director ? "on" : ""} onClick={() => setDirector(false)}>Simple</button>
            <button className={director ? "on" : ""} onClick={() => setDirector(true)}>Director Mode</button>
          </div>
          {night?.active && <button className="spend-chip route-chip" title="Stop the overnight render" onClick={async () => setNight(await api.overnight(project.dir, "stop"))}>
            <span className="spin sm" /> Overnight · {night.with_video}/{night.shots}</button>}
          <QueueChip q={queue} onOpen={() => setQueueOpen(true)} />
          <RouteChip dir={project.dir} onOpen={() => setRouteOpen(true)} sig={jobs.filter((j) => j.state === "ready").length + ":" + jobs.length} />
          {plan && <div className="menu-wrap">
            <button className="btn ghost" onClick={() => setMediaMenu((v) => !v)} aria-expanded={mediaMenu}>My media ▾</button>
            {mediaMenu && <div className="menu glass" role="menu" onMouseLeave={() => setMediaMenu(false)}>
              <button role="menuitem" onClick={async () => { setMediaMenu(false);
                try { const r = await addMediaToTimeline(project.dir, sel?.kind === "shot" ? sel.id : undefined); if (r) { mediaChanged();
                  setMediaNote(`Placed ${r.placed.length} file${r.placed.length === 1 ? "" : "s"}${r.skipped.length ? `; ${r.skipped.length} not placed (${r.skipped[0].reason})` : ""}.`); } }
                catch (e) { setMediaNote(errorText(e)); } }}>
                <b>Add images and clips…</b><span>One per empty shot, in order{sel?.kind === "shot" ? `, from ${sel.id}` : ""}. Free.</span></button>
              <button role="menuitem" onClick={() => { setMediaMenu(false); setFrameOpen(true); }}>
                <b>Insert a frame…</b><span>A card, picture, clip or generated shot of your own length{sel?.kind === "shot" ? `, next to ${sel.id}` : ""}.</span></button>
              <button role="menuitem" disabled={!night?.ready || !!night?.active} onClick={async () => { setMediaMenu(false);
                try {
                  let r = await api.overnight<{ keyframes_queued?: number; needs_confirm?: boolean; keyframes?: number; label?: string; provider?: string; usd?: number }>(project.dir, "start");
                  if (r.needs_confirm) {
                    if (!await ask(`Hybrid overnight: ${r.keyframes} keyframes on ${r.label} (${r.provider}) for about $${(r.usd ?? 0).toFixed(2)}, then every video free on your ComfyUI, then the export. Start?`)) return;
                    r = await api.overnight(project.dir, "start", true);
                  }
                  setNight(await api.overnight(project.dir, "status"));
                  setMediaNote(`Overnight started: ${r.keyframes_queued ?? 0} keyframes first, then videos on ComfyUI, then an export. Leave FilmCrafter and ComfyUI running.`); }
                catch (e) { setMediaNote(errorText(e)); } }}>
                <b>Render overnight on ComfyUI</b><span>{!night?.ready ? "Needs ComfyUI with a video workflow (Settings → Find ComfyUI)."
                  : (night as { keyframes_from?: string }).keyframes_from === "comfyui" ? "Keyframes, videos and the final cut on your own computer, while you sleep. Free."
                  : "Hybrid: keyframes on Kie (price shown first), videos free on ComfyUI, then the final cut."}</span></button>
              <button role="menuitem" disabled={stillable === 0} onClick={async () => { setMediaMenu(false);
                try { const r = await api.media<{ made: string[] }>(project.dir, "stills"); mediaChanged();
                  setMediaNote(`${r.made.length} moving stills made. Export any time; render video later only where you want it.`); } catch (e) { setMediaNote(errorText(e)); } }}>
                <b>Moving stills from keyframes ({stillable})</b><span>Shots with a keyframe but no video get a slow camera move. Free.</span></button>
            </div>}
          </div>}
          {plan && <button className="btn ghost cmd-btn" onClick={() => setCommanding(true)} title="Tell the Director what to change, in plain words (Ctrl+K)">Ask the Director <kbd>Ctrl K</kbd></button>}
          {narrowBar ? <div className="menu-wrap"><button className="btn ghost" onClick={() => setMoreOpen((v) => !v)} aria-expanded={moreOpen} aria-haspopup="menu">More ▾</button>
            {moreOpen && <div className="menu glass tb-more" role="menu" onClick={() => setMoreOpen(false)} onMouseLeave={() => setMoreOpen(false)}>
          <button className="btn" role="menuitem" onClick={() => setAutopilot(true)} title="Song to finished video, stopping only for your decisions">Autopilot</button>
          {Object.keys(pendingKf).length > 0 && <button className="btn" onClick={() => setApprovingKf(true)}
                      title="Approve the newest keyframe for every shot without one">Approve {Object.keys(pendingKf).length} keyframes</button>}
          {plan && board && <button className="btn" onClick={() => setSelecting(true)}
                  title="Choose shots, approve their keyframes, then pay for video only where the still is right">Select &amp; review</button>}
          {plan && (keys.fal || keys.kie) && toRender.length > 0 && <button className={`btn ${project.directed ? "hero" : ""}`} onClick={() => setConfirmAll(true)}
                                   disabled={toRender.length === 0}>Render {toRender.length === shots.length ? "all" : toRender.length} shots</button>}
            </div>}</div>
            : <>
          <button className="btn" onClick={() => setAutopilot(true)} title="Song to finished video, stopping only for your decisions">Autopilot</button>
          {Object.keys(pendingKf).length > 0 && <button className="btn" onClick={() => setApprovingKf(true)}
                      title="Approve the newest keyframe for every shot without one">Approve {Object.keys(pendingKf).length} keyframes</button>}
          {plan && board && <button className="btn" onClick={() => setSelecting(true)}
                  title="Choose shots, approve their keyframes, then pay for video only where the still is right">Select &amp; review</button>}
          {plan && (keys.fal || keys.kie) && toRender.length > 0 && <button className={`btn ${project.directed ? "hero" : ""}`} onClick={() => setConfirmAll(true)}
                                   disabled={toRender.length === 0}>Render {toRender.length === shots.length ? "all" : toRender.length} shots</button>}
            </>}
          {plan && <button className={`btn ${project.directed && (keys.fal || keys.kie) && toRender.length > 0 ? "ghost" : "hero"}`} onClick={directVideo} disabled={!!job}
                           title={project.directed ? "Plan the shots again from the song (your edits to the plan are asked about first)" : "Plan every shot on the beat of the song (free)"}>
            {project.directed ? "Direct Again" : "Direct My Video"}</button>}
          <button className="icon-btn" onClick={() => setFocusMode(true)} title="Full screen: just the video (F)" aria-label="Full screen">⛶</button>
          <button className="icon-btn" onClick={() => setTimelineOpen((v) => !v)} title={timelineOpen ? "Hide the timeline (Ctrl+J)" : "Show the timeline (Ctrl+J)"} aria-label={timelineOpen ? "Hide the timeline" : "Show the timeline"} aria-pressed={timelineOpen}><I.PanelBottom /></button>
          <button className="icon-btn" onClick={() => setInspector((v) => !v)} title="Inspector" aria-label="Toggle inspector"><I.Panel /></button>
        </header>
        {plan && <GoldenStrip onTour={() => setTourOpen(true)}
          test={pickTestShot(shots.map((x) => ({ id: x.id, start: x.start, end: x.end, framing: x.framing, performers: x.performers, emotion: x.emotion, text: [x.description, x.performance, x.movement].filter(Boolean).join(" ") })),
                             keyframes[planName] ?? {}, new Set([...takes.entries()].filter(([, j]) => j.state === "ready").map(([id]) => id)), map?.lyrics ?? [])} spent={route?.spent_usd ?? null} budget={route?.budget_usd ?? null}
          input={{ hasSong: !!map, shots, keyframes: keyframes[planName] ?? {}, videoReady: new Set([...takes.entries()].filter(([, j]) => j.state === "ready").map(([id]) => id)),
                   pending: Object.keys(pendingKf).length, exported: false,
                   people: (() => { const ppl = (board?.library.items ?? []).filter((i) => i.kind === "character" && !i.sheet); return { total: ppl.length, withPicture: ppl.filter((i) => i.files.length > 0).length }; })() }}
          onGo={(step) => {
            const open = (id: string | undefined, tab: string) => { if (!id) return; setSel({ kind: "shot", id }); setInspector(true); setTimeout(() => window.dispatchEvent(new CustomEvent("pf-open-tab", { detail: tab })), 30); };
            if (step.startsWith("test:")) open(step.slice(5), "video");
            else if (step === "refs") setLibraryOpen(true);
            else if (step === "export") setExporting(true);
            else if (step === "keyframes") open((shots.find((x) => !(keyframes[planName] ?? {})[x.id]) ?? shots[0])?.id, "keyframe");
            else if (step === "video") open((shots.find((x) => (keyframes[planName] ?? {})[x.id] && takes.get(x.id)?.state !== "ready") ?? shots[0])?.id, "video");
          }} />}

        {!plan && onProduce && <div className="pr-callout">
          <span className="pr-callout-ic"><I.Sparkle size={20} /></span>
          <div><b>Want the whole production planned for you?</b>
            <span>The Producer designs the cast, outfits, props, places, movement and every shot from your song. You approve each step, and it makes no pictures or videos until you say so.</span></div>
          <Cta icon={<I.Rocket size={16} />} onClick={onProduce}>Create the production</Cta></div>}
        {!plan && <CreativeDirections project={project} onPlanned={onReload} onSettings={onSettings} />}
        <div className="viewer-wrap" style={plan ? undefined : { display: "none" }}>
          <div className="stage">
          <div className="viewer" style={{ ["--ar" as string]: aspectNum(project.project.aspect_ratio) }}>
            {shown && boardShot.get(shown.id)?.preview && boardShot.get(shown.id)!.preview_kind === "image" ?
              <StillPreview src={api.mediaUrl(`${project.dir}/${boardShot.get(shown.id)!.preview}`)} motion={boardShot.get(shown.id)!.preview_motion} drift={boardShot.get(shown.id)!.preview_drift} playing={playing}
                            duration={shown.end - shown.start} offset={time - shown.start} /> :
             shown && boardShot.get(shown.id)?.preview && /\.(mp4|mov|webm|m4v)$/i.test(boardShot.get(shown.id)!.preview!) ?
              <Clip src={api.mediaUrl(`${project.dir}/${boardShot.get(shown.id)!.preview}`)} offset={time - shown.start} playing={playing} /> :
              shown && boardShot.get(shown.id)?.keyframe ? <img className="clip" alt="" src={api.mediaUrl(`${project.dir}/${boardShot.get(shown.id)!.keyframe}`)} /> : null}
            {shown ? <Storyboard shot={shown} scene={scenes.find((s) => s.number === shown.scene)} job={latest.get(shown.id)}
                                 hidden={!!boardShot.get(shown.id)?.preview || !!boardShot.get(shown.id)?.keyframe} /> :
              <div className="empty">{plan ? "Press play to preview the song map" : "Add a script or press Direct My Video to plan shots"}</div>}
            <PlayerOverlays dir={project.dir} time={time} beat={beatGrid(map)} accents={map?.accents} selected={layersOpen ? layerSel : null} onSelect={layersOpen ? setLayerSel : undefined} />
            <div className="subtitle" style={{ opacity: lyric ? 1 : 0 }}>{lyric?.text ?? ""}</div>
          </div>
          </div>
          {layersOpen && focusLayer && <LayerStrip layer={focusLayer} duration={map?.duration ?? 0} time={time} onSeek={seek} />}
          <div className="transport glass">
            <button className="icon-btn" onClick={() => seek(0)} aria-label="Back to start"><I.SkipBack size={18} /></button>
            <button className="play-btn" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>{playing ? <I.Pause /> : <I.Play />}</button>
            <button className="icon-btn" onClick={() => seek((map?.duration ?? 0))} aria-label="To end"><I.SkipFwd size={18} /></button>
            <div className="time num">{fmtTime(time)} / {fmtTime(map?.duration ?? 0)}</div>
            <button className="btn small ghost" onClick={() => { if (playing) toggle(); setPreviewOpen(true); }} title="A quick small version of the next few seconds, with layers and sound" disabled={!plan}>Preview</button>
            <input className="scrub" type="range" min={0} max={map?.duration ?? 0} step={0.04} value={Math.min(time, map?.duration ?? 0)}
                   aria-label="Scrub through the video" onChange={(e) => seek(Number(e.target.value))}
                   style={{ ["--v" as string]: `${map?.duration ? (time / map.duration) * 100 : 0}%` }} />
            <div className="volume">
              <button className="icon-btn" onClick={() => setMuted((m) => !m)} aria-label={muted ? "Unmute" : "Mute"} title={muted ? "Unmute" : "Mute"}>
                {muted || volume === 0 ? <I.Mute size={18} /> : <I.Volume size={18} />}</button>
              <input type="range" min={0} max={1} step={0.01} value={muted ? 0 : volume} aria-label="Volume"
                     onChange={(e) => { setVolume(Number(e.target.value)); setMuted(false); }}
                     style={{ ["--v" as string]: `${(muted ? 0 : volume) * 100}%` }} />
            </div>
          </div>
        </div>
      </main>

      <aside className={`inspector ${inspector ? "" : "collapsed"}`} aria-label="Inspector" style={inspector ? { width: narrowBar ? Math.min(inspW, Math.max(300, Math.round(window.innerWidth * 0.31))) : inspW } : undefined}>
        {inspector && <div className="insp-resize" onPointerDown={dragInspector} title="Drag to resize" role="separator" aria-orientation="vertical" />}
        {layersOpen && <LayersPanel docked dir={project.dir} time={time} selected={layerSel} onSelect={setLayerSel} onFocus={setFocusLayer} onClose={() => { setLayersOpen(false); setLayerSel(null); setFocusLayer(null); }} />}
        <div className="insp-host" style={layersOpen ? { display: "none" } : { display: "contents" }}>
        <Inspector key={histTick} sel={sel} shots={shots} scenes={scenes} map={map} plan={plan} director={director} project={project}
                   onClose={() => setSel(null)} lookLabel={lookName(styles, look)} onLook={() => setLookOpen(true)}
                   onOpenLibrary={() => setLibraryOpen(true)} onLibraryChanged={reloadBoard}
                   renderPanel={(s: Shot): ShotTabs => {
                     const pj = jobs.filter((j) => j.plan === planName && j.shot_id === s.id && j.state !== "dismissed");
                     const vid = pj.filter((j) => j.kind !== "image");
                     const kfRef = keyframes[planName]?.[s.id] ?? null;
                     return {
                       badges: {
                         keyframe: pj.some((j) => j.kind === "image" && ACTIVE_STATES.includes(j.state)) ? "busy" : kfRef ? "ok" : "",
                         frames: boardShot.get(s.id)?.end_mode && boardShot.get(s.id)?.end_mode !== "none" ? "ok" : "",
                         video: vid.some((j) => ACTIVE_STATES.includes(j.state)) ? "busy" : vid.some((j) => j.state === "ready") ? "ok" : vid.some((j) => j.state === "failed") ? "bad" : "",
                         media: boardShot.get(s.id)?.versions.some((v) => v.provider === "own") ? "ok" : "",
                       },
                       shot: <>
                         {board && <ShotRefs dir={project.dir} shot={boardShot.get(s.id)} library={board.library} thumbs={thumbs} want={want} onChanged={reloadBoard} />}
                         <ShotCamera dir={project.dir} shotId={s.id} sceneShotIds={shots.filter((x) => x.scene === s.scene).map((x) => x.id)} onChanged={mediaChanged} />
                         <ShotPerformance dir={project.dir} shotId={s.id} onChanged={reloadBoard} />
                         <ShotContinuity dir={project.dir} shotId={s.id} onChanged={mediaChanged} />
                       </>,
                       keyframe: (go) => <KeyframePanel dir={project.dir} shot={s} plan={planName} aspect={aspectCss(frame.aspect_ratio)} frame={frame.aspect_ratio} quality={frame.quality}
                                      jobs={jobs.filter((j) => j.plan === planName)} keys={keys} director={director} approved={kfRef} onJobs={mergeJobs} onSettings={onSettings}
                                      onNext={() => go("video")}
                                      onApproved={(ref) => { setKeyframes((k) => ({ ...k, [planName]: { ...(k[planName] ?? {}), [s.id]: ref ?? "" } })); reloadBoard(); }} />,
                       frames: (go) => <ComposeTab dir={project.dir} shot={s.id} keys={keys} onOpenKeyframe={() => go("keyframe")}
                                      refsPanel={board ? <ShotRefs dir={project.dir} shot={boardShot.get(s.id)} library={board.library} thumbs={thumbs} want={want} onChanged={reloadBoard} /> : null}
                                      onChanged={() => { reloadBoard(); api.loadProject(project.dir).then((p) => { if (p.keyframes) setKeyframes(p.keyframes); }).catch(() => {}); }}
                                      onQueued={(j) => { mergeJobs(j); go("video"); }} />,
                       video: (go) => <>
                         <RenderPanel dir={project.dir} shot={s} jobs={jobs.filter((j) => j.plan === planName)}
                                      director={director} keys={keys} onQueued={mergeJobs} onSettings={onSettings} frame={frame.aspect_ratio} quality={frame.quality}
                                      onBack={() => go("keyframe")} lookId={look.style} keyframeKey={kfRef}
                                      approvedTake={boardShot.get(s.id)?.approved ?? null} onTakeChosen={mediaChanged} />
                         <UpgradePanel dir={project.dir} shot={boardShot.get(s.id)} open={rerender === s.id} onDone={() => { setRerender(null); mediaChanged(); }} />
                       </>,
                       media: <OwnMediaPanel dir={project.dir} shot={boardShot.get(s.id)} onChanged={mediaChanged} />,
                     };
                   }} />
        </div>
      </aside>

      {tourOpen && plan && <Tour right={(inspector ? inspW : 0) + 28} onClose={() => setTourOpen(false)} />}
      {!timelineOpen && <button className="tl-restore" onClick={() => setTimelineOpen(true)} aria-label="Show the timeline" title="Show the timeline (Ctrl+J)"><I.PanelBottom size={14} /> Show the timeline <span className="dim num">{fmtTime(time)}{map ? ` / ${fmtTime(map.duration)}` : ""}</span></button>}
      {timelineOpen && <Timeline key={project.dir} compact={tlCompact} onCompact={() => setTlCompact((v) => !v)} map={map} time={time} sel={sel} flagged={flagged} dir={project.dir} board={board?.shots ?? []} thumbs={thumbs} want={want}
                layerSel={layerSel} onLayerSelect={(id) => { setLayerSel(id); if (id) setLayersOpen(true); }} onBoardChanged={reloadBoard}
                onOpen={(id) => setViewing(id)}
                onSeek={seek} onSelect={(s) => { setSel(s); if (s?.kind === "shot") { const sh = shots.find((x) => x.id === s.id); if (sh) seek(sh.start); } }} />}
      {viewing && boardShot.get(viewing) && board && <ShotViewer dir={project.dir} shot={boardShot.get(viewing)!} library={board.library}
                                    onClose={() => setViewing(null)} onChanged={reloadBoard}
                                    onRegenerate={() => { setSel({ kind: "shot", id: viewing }); setInspector(true); setViewing(null); }} />}
      {approvingKf && <ApproveKeyframes dir={project.dir} pending={pendingKf} onClose={() => setApprovingKf(false)}
                                        onDone={() => { setApprovingKf(false); refreshPendingKf(); reloadBoard(); onReload(); }} />}
      {autopilot && <Autopilot project={project} onClose={() => setAutopilot(false)} onReload={onReload} />}
      {perfOpen && <PerformanceSheet dir={project.dir} scenes={scenes.map((s) => ({ number: s.number, heading: s.heading }))}
                                     characters={[...new Set(shots.flatMap((s) => s.performers ?? []))]}
                                     onClose={() => setPerfOpen(false)} onChanged={reloadBoard} />}
      {contOpen && <ContinuitySheet dir={project.dir} onClose={() => setContOpen(false)} onSelectShot={(id) => setSel({ kind: "shot", id })} />}
      {scriptOpen && <ScriptSheet project={project} onClose={() => setScriptOpen(false)} onDone={() => { setScriptOpen(false); onReload(); }} />}
      {libraryOpen && <LibrarySheet dir={project.dir} scenes={scenes.map((s) => ({ number: s.number, heading: s.heading }))}
                                    onClose={() => setLibraryOpen(false)} onChanged={reloadBoard} autoMake={openMake} />}

      {commanding && <DirectorCommand dir={project.dir} selected={sel?.kind === "shot" ? sel.id : null} playhead={time}
                                      onJobs={mergeJobs} onChanged={() => { reloadBoard(); refreshPendingKf(); onReload(); }}
                                      onClose={() => setCommanding(false)} onSettings={onSettings}
                                      onApplied={(r) => { setCommanding(false); setCmdResult(r); if (r.changed.length) onReload(); }} />}
      {cmdResult && <CommandToast result={cmdResult} onDismiss={() => setCmdResult(null)}
                                  onSelect={(id) => { setSel({ kind: "shot", id }); const sh = shots.find((x) => x.id === id); if (sh) seek(sh.start); }}
                                  onUndo={async () => { try { await api.undoCommand(project.dir, cmdResult.id!); setCmdResult(null); onReload(); } catch (e) { setError(errorText(e)); } }} />}
      {upscaling && <UpscaleSheet dir={project.dir} req={upscaling} onClose={() => setUpscaling(null)} onChanged={() => { reloadBoard(); onReload(); window.dispatchEvent(new Event("pf-media-changed")); }} />}
      {lightOpen && <LightingSheet dir={project.dir} onClose={() => setLightOpen(false)} onChanged={mediaChanged}
                                   onSelect={(id) => { setSel({ kind: "shot", id }); const sh = shots.find((x) => x.id === id); if (sh) seek(sh.start); }} />}
      {queueOpen && <RenderQueueSheet dir={project.dir} jobs={jobs} shots={shots} onJob={(j) => mergeJobs([j])} onClose={() => setQueueOpen(false)} onReview={() => setReviewing(true)}
                                      onShow={(id) => { setSel({ kind: "shot", id }); const sh = shots.find((x) => x.id === id); if (sh) seek(sh.start); }} />}
      {batch && !reviewing && !queueOpen && <div className="toast glass batch-toast" role="status">
        <div className="t">{batch.failed ? "Renders finished, with problems" : "Renders finished"}</div>
        <div className="s">{batch.text}{batch.failed ? " The failed ones are listed in the queue with the reason." : " Each take is being checked; Review shows what needs a second look."}</div>
        <div className="cmd-changed"><button className="btn small primary" onClick={() => { setBatch(null); setReviewing(true); }}>Open Review</button>
          <button className="btn small ghost" onClick={() => { setBatch(null); setQueueOpen(true); }}>See the queue</button>
          <button className="btn small ghost" onClick={() => setBatch(null)}>Dismiss</button></div>
      </div>}
      {reviewing && <ReviewSheet dir={project.dir} shots={shots} jobs={jobs.filter((j) => j.plan === planName)} inUse={Object.fromEntries((board?.shots ?? []).map((b) => [b.id, b.approved]))} keys={keys} onJobs={mergeJobs} onQueue={() => setQueueOpen(true)}
                                 onChanged={() => { reloadBoard(); mediaChanged(); }}
                                 onOpen={(id) => { setReviewing(false); setViewing(id); }}
                                 onSelect={(id) => { setSel({ kind: "shot", id }); const sh = shots.find((x) => x.id === id); if (sh) seek(sh.start); }}
                                 onClose={() => setReviewing(false)} />}
      {lookOpen && <LookPicker value={look} director={director} onCancel={() => setLookOpen(false)} onSave={saveLook} />}
      {exporting && <ExportSheet dir={project.dir} projectAspect={project.project.aspect_ratio} shots={shots.length}
                                 rendered={shots.filter((s) => latest.get(s.id)?.state === "ready").length}
                                 onClose={() => setExporting(false)} />}
      {selecting && board && <SelectReview dir={project.dir} shots={board.shots} sections={map?.sections ?? []}
                                           initial={sel?.kind === "shot" ? [sel.id] : []} onClose={() => { setSelecting(false); reloadBoard(); refreshPendingKf(); }}
                                           onQueued={(js) => { mergeJobs(js); reloadBoard(); }} />}
      {confirmAll && <ConfirmRender count={toRender.length} seconds={0} provider={route?.video.provider ?? defaultProvider(keys)}
                                    model={route?.video.provider ? route.video.label! : AUTO_MODEL[defaultProvider(keys)]} onCancel={() => setConfirmAll(false)} onConfirm={renderAll}
                                    dir={project.dir} shots={toRender.map((s) => s.id)} modelId={route?.video.provider ? route.video.model! : AUTO_MODEL[defaultProvider(keys)]} />}
      {colourOpen && <ColourMatchSheet dir={project.dir} onClose={() => setColourOpen(false)} />}
      {previewOpen && <PreviewSheet dir={project.dir} from={time} duration={map?.duration ?? 0} onClose={() => setPreviewOpen(false)} />}
      {frameOpen && <InsertFrameSheet dir={project.dir} shot={sel?.kind === "shot" ? sel.id : undefined} onClose={() => setFrameOpen(false)}
                                      onDone={(id) => { setFrameOpen(false); onReload(); if (id) setSel({ kind: "shot", id }); }} />}
      {cleanOpen && <CleanupSheet dir={project.dir} onClose={() => setCleanOpen(false)} onChanged={mediaChanged} />}
      {dlOpen && <DirectionLibrarySheet dir={project.dir} onClose={() => setDlOpen(false)} onApplied={onReload} />}
      {supOpen && <SupervisorSheet dir={project.dir} onClose={() => setSupOpen(false)} onChanged={mediaChanged}
                                   onReview={(id) => { setSel({ kind: "shot", id }); setViewing(id); }} />}
      {paletteOpen && <Palette onClose={() => setPaletteOpen(false)}
        shots={shots.map((s) => ({ id: s.id, start: s.start }))}
        onShot={(id) => { const sh = shots.find((x) => x.id === id); setSel({ kind: "shot", id }); setInspector(true); if (sh) seek(sh.start); }}
        commands={([
          plan && { id: "director", label: "Ask the Director", hint: "Change the video in plain words", keys: "Ctrl+K", run: () => setCommanding(true) },
          plan && { id: "direct", label: project.directed ? "Direct again" : "Direct my video", hint: "Plan every shot on the beat (free)", run: directVideo },
          plan && (keys.fal || keys.kie) && toRender.length > 0 && { id: "render", label: `Render ${toRender.length === shots.length ? "all" : toRender.length} shots`, hint: "Shows the price first", run: () => setConfirmAll(true) },
          plan && board && { id: "select", label: "Select & review", hint: "Choose shots, approve keyframes, pay for video where it is right", run: () => setSelecting(true) },
          plan && { id: "preview", label: "Preview the next seconds", hint: "A small quick version with layers and sound", run: () => { if (playing) toggle(); setPreviewOpen(true); } },
          plan && { id: "export", label: "Export the film", keys: "Ctrl+E", run: () => setExporting(true) },
          plan && { id: "layers", label: layersOpen ? "Close the Layers panel" : "Open the Layers panel", hint: "Text, pictures, shapes drawn over the film", keys: "Y", run: () => setLayersOpen((v) => !v) },
          plan && { id: "colour", label: "Colour match", hint: "Even out brightness and colour between shots", run: () => setColourOpen(true) },
          plan && { id: "clean", label: "Clean up unused videos and pictures", run: () => setCleanOpen(true) },
          plan && { id: "frame", label: "Insert a frame", hint: "A card, picture, clip or generated shot", run: () => setFrameOpen(true) },
          plan && { id: "supervisor", label: "Supervisor", hint: "Checks of the whole film", run: () => setSupOpen(true) },
          plan && { id: "acting", label: "Acting", run: () => setPerfOpen(true) },
          plan && { id: "continuity", label: "Continuity", run: () => setContOpen(true) },
          plan && { id: "review", label: "Review", run: () => setReviewing(true) },
          plan && { id: "lighting", label: "Light the story", hint: "Read each shot's mood and plan the light to match (free)", run: () => setLightOpen(true) },
          { id: "library", label: "Reference library", hint: "Characters, places, props", run: () => setLibraryOpen(true) },
          { id: "directions", label: "Directions", run: () => setDlOpen(true) },
          { id: "project", label: "Project page", hint: "Title, tempo, cast, look", run: () => { setSel(null); setInspector(true); } },
          { id: "play", label: playing ? "Pause" : "Play", keys: "Space", run: toggle },
          { id: "mute", label: muted ? "Unmute the player" : "Mute the player", keys: "M", run: () => setMuted((m) => !m) },
          { id: "focus", label: "Full screen: just the video", keys: "F", run: () => setFocusMode(true) },
          { id: "inspector", label: inspector ? "Hide the inspector" : "Show the inspector", keys: "Ctrl+I", run: () => setInspector((v) => !v) },
          { id: "timeline", label: timelineOpen ? "Hide the timeline" : "Show the timeline", keys: "Ctrl+J", run: () => setTimelineOpen((v) => !v) },
          ...(timelineOpen ? [{ id: "timeline-compact", label: tlCompact ? "Full-height timeline" : "Compact timeline", keys: "Ctrl+Shift+J", run: () => setTlCompact((v) => !v) }] : []),
          ...(hist?.undo_count ? [{ id: "undo-shot", label: `Undo: ${hist.undo[0].label}`, keys: "Ctrl+Shift+U", run: () => stepHist("undo") }] : []),
          ...(hist?.redo_count ? [{ id: "redo-shot", label: `Redo: ${hist.redo[0].label}`, keys: "Ctrl+Shift+Y", run: () => stepHist("redo") }] : []),
          { id: "check-hands", label: "Check hands in all keyframes…", hint: "Look at every keyframe's hands before any video is made", run: () => setKfTools(true) },
          { id: "one-model", label: "Redo keyframes on one picture model…", hint: "Keep one look across the cast", run: () => setKfTools(true) },
          { id: "next-flag", label: "Next shot that needs attention", keys: ".", run: () => { const t = stepAttention(attentionStarts(shots, needsLook), time, 1); if (t !== null) seek(t); else say("No later shot needs attention."); } },
          { id: "simple", label: "Simple mode", keys: "Ctrl+1", run: () => setDirector(false) },
          { id: "director-mode", label: "Director Mode", keys: "Ctrl+2", run: () => setDirector(true) },
          { id: "shortcuts", label: "Keyboard shortcuts", keys: "?", run: () => setKeysHelp(true) },
          { id: "settings", label: "Settings", keys: "Ctrl+,", run: onSettings },
          { id: "home", label: "Back to Home", run: onHome },
        ].filter(Boolean)) as Command[]} />}
      {keysHelp && <div className="overlay" onClick={() => setKeysHelp(false)}><div className="sheet glass keys-help" onClick={(e) => e.stopPropagation()}>
        <h2>Keyboard shortcuts</h2>
        <div className="kh-cols">{GROUPS.map((g) => <section key={g}><h3>{g}</h3>
          <dl>{SHORTCUTS.filter((x) => x.group === g).map((x) => <div key={x.id}><dt><kbd>{x.keys}</kbd></dt><dd>{x.label}</dd></div>)}</dl></section>)}</div>
        <div className="sheet-actions"><button className="btn" onClick={() => setKeysHelp(false)}>Close</button></div></div></div>}
      {toastMsg && <div className="toast glass mini" role="status">{toastMsg}</div>}
      {undoOffer && !toastMsg && <div className="toast glass mini undo-toast" role="status">{undoOffer} <button className="btn small" onClick={() => stepHist("undo")}>Undo</button> <span className="dim">Ctrl+Shift+U</span></div>}
      {night && !night.active && night.finished && night.export && (Date.now() / 1000 - night.finished < 86400) &&
        <div className="toast glass" role="status"><div className="t">Overnight render finished</div><div className="s">{night.export.split(/[\\/]/).pop()}</div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}><button className="btn" onClick={() => setNight({ ...night, finished: null })}>OK</button></div></div>}
      {routeOpen && <RoutingSheet dir={project.dir} onClose={() => setRouteOpen(false)} />}
      {kfTools && <KeyframeTools dir={project.dir} onClose={() => setKfTools(false)} onChanged={() => { reloadBoard(); api.loadProject(project.dir).then((p) => { if (p.keyframes) setKeyframes(p.keyframes); }).catch(() => {}); window.dispatchEvent(new Event("pf-shot-changed")); }} />}
      {route && !route.online && <div className="offline-banner" role="status">Offline: cloud renders wait until you are back online. Your own media,
        moving stills, continuity, acting and export all keep working{route.brain.local ? ", and so does the local AI brain" : ""}.</div>}
      {job && (
        <div className="toast glass" role="status">
          <div className="t">{job.title}</div>
          <div className="s">{job.detail}</div>
          <div className="progress indet"><i /></div>
        </div>
      )}
      {songError && <div className="toast glass" role="alert" style={{ borderColor: "rgba(239,107,115,0.4)" }}>
        <div className="t" style={{ color: "var(--error)" }}>Can't play</div><div className="s">{songError}</div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}><button className="btn" onClick={() => setSongError("")}>OK</button></div>
      </div>}
      {mediaNote && <div className="toast glass" role="status">
        <div className="t">Your media</div><div className="s">{mediaNote}</div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}><button className="btn" onClick={() => setMediaNote("")}>OK</button></div>
      </div>}
      {error && (
        <div className="toast glass" role="alert" style={{ borderColor: "rgba(239,107,115,0.4)" }}>
          <div className="t" style={{ color: "var(--error)" }}>Direction stopped</div>
          <div className="s">{error}</div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
            <button className="btn" onClick={() => setError("")}>OK</button></div>
        </div>
      )}
    </div>
  );
}

const aspectNum = (r?: string) => {
  const m = r?.match(/^([\d.]+):([\d.]+)$/);
  return m ? String(Number(m[1]) / Number(m[2])) : String(16 / 9);
};
const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function RailBtn({ icon, label, active, disabled, onClick, badge, why }: {
  icon: React.ReactNode; label: string; active?: boolean; disabled?: boolean; onClick?: () => void; badge?: number; why?: string;
}) {
  return <button className={active ? "active" : ""} data-k={label.toLowerCase()} disabled={disabled} onClick={onClick}
                 title={disabled && why ? `${label}: ${why}` : label} aria-current={active ? "page" : undefined}>
    {icon}<span>{label}</span>{badge ? <i className="rail-badge" aria-label={`${badge} need attention`}>{badge}</i> : null}</button>;
}

export function StateChip({ shot }: { shot: Shot }) {
  if (shot.flags?.length) return <span className="chip review"><I.Alert size={12} /> Needs review</span>;
  const s = shot.state ?? "planned";
  if (s === "ready") return <span className="chip ready"><I.Check size={12} /> Ready</span>;
  if (s === "locked") return <span className="chip"><I.Lock size={12} /> Locked</span>;
  if (s === "failed") return <span className="chip failed"><I.Alert size={12} /> Failed</span>;
  return <span className="chip planned"><I.Circle size={12} /> Planned</span>;
}

/** A rendered take, kept in step with the master audio (the song is the clock). */
function Clip({ src, offset, playing }: { src: string; offset: number; playing: boolean }) {
  const v = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const el = v.current;
    if (!el) return;
    if (Math.abs(el.currentTime - offset) > 0.15) el.currentTime = Math.max(0, offset);
    if (playing && el.paused) el.play().catch(() => {});
    if (!playing && !el.paused) el.pause();
  }, [offset, playing, src]);
  return <video ref={v} className="clip" src={src} muted playsInline preload="auto" />;
}

function Storyboard({ shot, scene, job, hidden }: { shot: Shot; scene?: Scene; job?: Job; hidden?: boolean }) {
  const text = shot.visual_prompt ?? shot.beats.join(" ");
  return (
    <>
      <div className="frame-info">
        <span className="chip num">{shot.id}</span>
        {job ? <JobChip job={job} /> : <StateChip shot={shot} />}
        <span className="chip num">{(shot.end - shot.start).toFixed(1)}s</span>
      </div>
      {!hidden && <div className="board">
        {scene && <div className="scene-head">{scene.heading}</div>}
        <div className="desc">{text}</div>
        <div className="framing">{[shot.framing, shot.camera_movement ?? shot.camera_moves?.join(", ")].filter(Boolean).join(" · ")}</div>
      </div>}
    </>
  );
}

// ---------------- inspector ----------------

function Inspector({ sel, shots, scenes, map, plan, director, project, onClose, renderPanel, lookLabel, onLook, onOpenLibrary, onLibraryChanged }: {
  sel: Selection; shots: Shot[]; scenes: Scene[]; map: SongMap | null; plan: Plan | null; director: boolean;
  project: LoadedProject; onClose: () => void; renderPanel: (s: Shot) => ShotTabs; lookLabel: string; onLook: () => void;
  onOpenLibrary: () => void; onLibraryChanged: () => void;
}) {
  if (sel?.kind === "shot") {
    const s = shots.find((x) => x.id === sel.id);
    if (s) return <ShotInspector shot={s} scene={scenes.find((c) => c.number === s.scene)} director={director} onClose={onClose} project={project}
                                 tabs={renderPanel(s)} />;
  }
  if (sel?.kind === "section" && map) {
    const sec = map.sections[sel.index];
    const lines = map.lyrics.filter((l) => l.start != null && l.start >= sec.start && l.start < sec.end);
    return (
      <>
        <div className="inspector-head"><span className="t">{sec.group || sec.label}</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <div className="inspector-body">
          <div className="insp-section"><div className="kv">
            <span className="k">Time</span><span className="v num">{fmtTime(sec.start)} – {fmtTime(sec.end)}</span>
            <span className="k">Mood</span><span className="v">{sec.mood}</span>
            <span className="k">Energy</span><span className="v"><Meter v={sec.energy} /></span>
          </div></div>
          {lines.length > 0 && <div className="insp-section"><h4>Lyrics</h4>{lines.map((l, i) => <p key={i} className="lyric-q">{l.text}</p>)}</div>}
        </div>
      </>
    );
  }
  return (
    <>
      <div className="inspector-head"><span className="t">Project</span></div>
      <div className="inspector-body">
        <div className="insp-section"><div className="kv">
          <span className="k">Title</span><span className="v">{project.project.title}</span>
          {map && <><span className="k">Tempo</span><span className="v num">{map.bpm.toFixed(1)} BPM</span>
            <span className="k">Length</span><span className="v num">{fmtTime(map.duration)}</span>
            <span className="k">Sections</span><span className="v num">{map.sections.length}</span>
            {map.lyric_match != null && <><span className="k">Lyrics heard</span><span className="v num">{Math.round(map.lyric_match * 100)}%</span></>}</>}
          <span className="k">Shots</span><span className="v num">{shots.length}</span>
          <span className="k">Renderer</span><span className="v">Auto</span>
        </div></div>
        <MaterialsPanel project={project} hasPlan={!!plan} onChanged={onLibraryChanged} onOpenLibrary={onOpenLibrary} />
        <ProjectSettingsRow project={project} />
        <div className="insp-section look-row">
          <h4>Look</h4>
          <div className="file-row"><span className="name">{lookLabel}</span><button className="btn ghost small" onClick={onLook}>Change</button></div>
        </div>
        {plan?.meta?.LOGLINE && <div className="insp-section"><h4>Story</h4><p className="prose">{plan.meta.LOGLINE}</p></div>}
        {plan?.meta?.["VISUAL STYLE"] && <div className="insp-section"><h4>Look</h4><p className="prose">{plan.meta["VISUAL STYLE"]}</p></div>}
        {plan?.characters?.length ? <div className="insp-section"><h4>Cast</h4>
          {plan.characters.map((c) => <p key={c.name} className="prose"><b style={{ color: "var(--frost)" }}>{c.name}</b> — {c.archetype}</p>)}</div> : null}
        {director && scenes.some((s) => s.director_note) && <div className="insp-section"><h4>Director notes</h4>
          {scenes.filter((s) => s.director_note).map((s) => <p key={s.number} className="prose" style={{ marginBottom: 8 }}>
            <b style={{ color: "var(--frost)" }}>Scene {s.number}.</b> {s.director_note}</p>)}</div>}
      </div>
    </>
  );
}

type Tab = "shot" | "keyframe" | "frames" | "video" | "media";
type Badge = "" | "ok" | "busy" | "bad";
export type ShotTabs = {
  badges: { keyframe: Badge; frames: Badge; video: Badge; media: Badge };
  shot: React.ReactNode; media: React.ReactNode;
  keyframe: (go: (t: Tab) => void) => React.ReactNode; frames: (go: (t: Tab) => void) => React.ReactNode; video: (go: (t: Tab) => void) => React.ReactNode;
};
const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "shot", label: "Shot", icon: <I.Camera size={16} /> },
  { id: "keyframe", label: "Keyframe", icon: <I.ImageIcon size={16} /> },
  { id: "frames", label: "Compose", icon: <I.Wand size={16} /> },
  { id: "video", label: "Video", icon: <I.Clapper size={16} /> },
  { id: "media", label: "Media", icon: <I.Upload size={16} /> },
];
const TAB_KEY = "pf-inspector-tab";
const storedTab = (): Tab => { try { const t = localStorage.getItem(TAB_KEY); return TABS.some((x) => x.id === t) ? (t as Tab) : "keyframe"; } catch { return "keyframe"; } };

export function ShotInspector({ shot: s, scene, director, onClose, tabs }: {
  shot: Shot; scene?: Scene; director: boolean; onClose: () => void; tabs: ShotTabs; project: LoadedProject;
}) {
  const [tab, setTabState] = useState<Tab>(storedTab);
  const [dockEl, setDockEl] = useState<HTMLElement | null>(null);
  const setTab = (t: Tab) => { setTabState(t); try { localStorage.setItem(TAB_KEY, t); } catch { /* remembering the tab is a convenience only */ } };
  useEffect(() => {   // the Golden Path strip can open a tab for you
    const h = (e: Event) => { const t = (e as CustomEvent).detail as Tab; if (TABS.some((x) => x.id === t)) setTab(t); };
    window.addEventListener("pf-open-tab", h);
    return () => window.removeEventListener("pf-open-tab", h);
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const row = (k: string, v?: string | number | null) => (v === undefined || v === null || v === "" ? null :
    <><span className="k">{k}</span><span className="v">{v}</span></>);
  return (
    <DockCtx.Provider value={{ el: dockEl, tab }}>
      <div className="inspector-head"><span className="t num">Shot {s.id}</span>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      <div className="insp-tabs" role="tablist" aria-label="Shot sections">
        {TABS.map((t) => {
          const b = t.id === "shot" ? "" : tabs.badges[t.id as "keyframe" | "frames" | "video" | "media"];
          return (
            <button key={t.id} role="tab" data-tab={t.id} aria-selected={tab === t.id} className={`insp-tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
              {t.icon}<span>{t.label}</span>{b ? <i className={`tab-dot ${b}`} title={b === "ok" ? "Done" : b === "busy" ? "Working" : "Needs a look"} /> : null}
            </button>);
        })}
      </div>
      <div className="inspector-body">
        <div hidden={tab !== "shot"}>
          <div className="insp-section" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <StateChip shot={s} /><span className="chip">Renderer: Auto</span>
          </div>
          {s.flags?.map((f) => <div key={f} className="flag"><I.Alert size={14} /> {f}</div>)}
          <div className="insp-section"><div className="kv">
            {row("Time", `${fmtTime(s.start)} → ${fmtTime(s.end)}`)}
            {row("Duration", `${(s.end - s.start).toFixed(2)} s`)}
            {row("Section", s.section)}
            {row("Performers", s.performers.join(", ") || "—")}
            {row("Emotion", s.emotion)}
            {s.performance_intensity != null && <><span className="k">Intensity</span><span className="v"><Meter v={s.performance_intensity} /></span></>}
          </div></div>
          {s.purpose && <div className="insp-section"><h4>Purpose</h4><p className="prose">{s.purpose}</p></div>}
          <div className="insp-section"><h4>{s.beats.length > 1 ? `Story beats (${s.beats.length})` : "Action"}</h4>
            {s.beats.length > 1 ? <ol className="beats">{s.beats.map((b, i) => <li key={i}>{b}</li>)}</ol> : <p className="prose">{s.beats[0]}</p>}</div>
          {s.lyrics?.length ? <div className="insp-section"><h4>Lyrics under this shot</h4>{s.lyrics.map((l, i) => <p key={i} className="lyric-q">{l}</p>)}</div> : null}
          {tabs.shot}
          {(s.performance || s.expression || s.movement) && <div className="insp-section"><h4>Performance</h4><div className="kv">
            {row("Acting", s.performance)}{row("Expression", s.expression)}{row("Movement", s.movement)}</div></div>}
          {director && <>
            {(s.environment || s.wardrobe || s.continuity) && <div className="insp-section"><h4>Set & continuity</h4><div className="kv">
              {row("Set", s.environment)}{row("Wardrobe", s.wardrobe)}{row("Continuity", s.continuity)}{row("Sync", s.sync_event)}</div></div>}
            {s.visual_prompt && <div className="insp-section"><h4>Visual description</h4><p className="prose">{s.visual_prompt}</p></div>}
            {s.dropped_beats?.length ? <div className="insp-section"><h4>Dropped beats</h4><ul className="beats">{s.dropped_beats.map((b, i) => <li key={i}>{b}</li>)}</ul></div> : null}
            <div className="insp-section"><h4>Script source</h4><p className="prose num">{s.source_shots.join(", ")}</p></div>
            {scene && <div className="insp-section"><h4>Scene notes</h4><div className="kv">
              {Object.entries(scene.notes).map(([k, v]) => <Fragment key={k}><span className="k">{k.split("/")[0].toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</span><span className="v">{v}</span></Fragment>)}</div></div>}
          </>}
          {!director && <p className="prose" style={{ fontSize: 12.5, color: "var(--smoke)" }}>Switch to Director Mode to see the set, wardrobe, continuity and every scene note.</p>}
        </div>
        <div hidden={tab !== "keyframe"}>{tabs.keyframe(setTab)}</div>
        <div hidden={tab !== "frames"}>{tabs.frames(setTab)}</div>
        <div hidden={tab !== "video"}>{tabs.video(setTab)}</div>
        <div hidden={tab !== "media"}>{tabs.media}</div>
      </div>
      <div className="insp-dock" ref={setDockEl} />
    </DockCtx.Provider>
  );
}

const Meter = ({ v }: { v: number }) => <span className="meter" aria-label={`${v} of 10`}>{Array.from({ length: 10 }, (_, i) => <i key={i} className={i < v ? "on" : ""} />)}</span>;

// ---------------- timeline ----------------

/**
 * Whether the top bar has run out of room, measured rather than guessed: the bar's buttons change with the project (an Overnight chip, "Approve 1 keyframes", Director Mode's extras), so a fixed
 * window width cannot say. When the buttons overflow, fold the secondary ones into a menu; unfold again once the bar is wide enough for what it needed. `deps` are what can change the buttons.
 */
function useBarFold(ref: React.RefObject<HTMLElement | null>, deps: unknown[]): boolean {
  const [fold, setFold] = useState(false);
  const need = useRef(0);                                              // how wide the bar needed to be when it was last unfolded and full
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      if (el.clientWidth < 100) return;                                  // hidden or not laid out yet: nothing to measure
      if (!fold && el.scrollWidth > el.clientWidth + 1) { need.current = el.scrollWidth; setFold(true); }
      else if (fold && el.clientWidth >= need.current + 8) setFold(false);
    };
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    window.addEventListener("resize", check);                          // also on the window's own resize: a hidden or throttled view may not report the bar's size
    return () => { ro.disconnect(); window.removeEventListener("resize", check); };
  }, [ref, fold, ...deps]);                                            // eslint-disable-line react-hooks/exhaustive-deps
  return fold;
}

/** True while the window is narrower than `px`: the Studio folds its secondary buttons into a menu then, instead of letting the top bar run under the inspector. */
function useNarrow(px: number): boolean {
  const q = `(max-width: ${px}px)`;
  const [n, setN] = useState(() => !!window.matchMedia?.(q).matches);
  useEffect(() => {
    const m = window.matchMedia?.(q);
    if (!m) return;
    const on = () => setN(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [q]);
  return n;
}

/** How tall a shot's picture is on the timeline at the least, and the height the timeline opens at: tall enough to see what each shot is. */
const CARD_MIN = 96;
const TL_MIN_SAVED = 300;                                   // an older, shorter saved height gave pictures too small to read, so it is not kept
const defaultTimelineHeight = () => Math.max(340, Math.min(480, Math.round(window.innerHeight * 0.42)));

function Timeline({ compact, onCompact, map, time, sel, flagged, dir, board, thumbs, want, layerSel, onLayerSelect, onBoardChanged, onSeek, onSelect, onOpen }: {
  compact: boolean; onCompact: () => void;
  map: SongMap | null; time: number; sel: Selection; flagged: number; dir: string; board: BoardShot[];
  thumbs: Record<string, string | null>; want: (srcs: string[]) => void;
  layerSel: string | null; onLayerSelect: (id: string | null) => void; onBoardChanged: () => void;
  onSeek: (t: number) => void; onSelect: (s: Selection) => void; onOpen: (id: string) => void;
}) {
  const [laneN, setLaneN] = useState(0);
  const [addMenu, setAddMenu] = useState(false);
  const [addErr, setAddErr] = useState("");
  const scroll = useRef<HTMLDivElement>(null);
  const wave = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(1200);
  const [left, setLeft] = useState(0);
  const dur = map?.duration ?? 0;
  // zoom: pixels per second; capped so the waveform canvas stays within browser limits
  const maxPps = Math.max(12, Math.floor(30000 / Math.max(1, dur * (window.devicePixelRatio || 1))));
  const [pps, setPpsState] = useState(() => readLayout(dir).pps ?? 24);                 // zoom and height are remembered for this project
  const setPps = (n: number) => { const v = Math.max(PPS_MIN, Math.min(PPS_MAX, n)); setPpsState(v); writeLayout(dir, { pps: v }); };
  const zoom = (f: number, anchorPx?: number) => {
    const s = scroll.current;
    const next = Math.max(6, Math.min(maxPps, Math.round(pps * f)));
    if (next === pps) return;
    const ax = anchorPx ?? (s ? s.clientWidth / 2 : 0);
    const t = ((s?.scrollLeft ?? 0) + ax) / pps;
    setPps(next);
    requestAnimationFrame(() => { if (s) s.scrollLeft = Math.max(0, t * next - ax); });
  };
  const [sized, setSized] = useState(() => !!readLayout(dir).sized);                 // a height the person chose is kept, however short
  const [fullHeight, setHeight] = useState(() => { const l = readLayout(dir); return l.height && (l.sized || l.height >= TL_MIN_SAVED) ? l.height : defaultTimelineHeight(); });
  const height = compact ? COMPACT_HEIGHT : fullHeight;
  // Ctrl + wheel zooms around the pointer (native listener: React's wheel handler can't stop page zoom); plain wheel scrolls sideways
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  useEffect(() => {
    const el = scroll.current;
    if (!el) return;
    const on = (e: WheelEvent) => {
      if (e.ctrlKey) { e.preventDefault(); zoomRef.current(e.deltaY < 0 ? 1.25 : 0.8, e.clientX - el.getBoundingClientRect().left); }
      else if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); el.scrollLeft += e.deltaY; }
    };
    el.addEventListener("wheel", on, { passive: false });
    return () => el.removeEventListener("wheel", on);
  }, [map]);
  const heightRef = useRef(fullHeight);
  heightRef.current = fullHeight;
  const drag = (e: React.PointerEvent) => {
    const y0 = e.clientY, h0 = height;
    if (compact) onCompact();                                                 // dragging the edge leaves compact mode
    setSized(true);
    const move = (ev: PointerEvent) => setHeight(Math.max(HEIGHT_MIN, Math.min(window.innerHeight * 0.6, h0 + (y0 - ev.clientY))));
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      writeLayout(dir, { height: Math.max(HEIGHT_MIN, Math.min(HEIGHT_MAX, Math.round(heightRef.current))), sized: true });
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const inner = Math.max(width, dur * pps);
  const x = (t: number) => t * pps;
  const addLayer = async (data: Record<string, unknown>) => {
    setAddMenu(false); setAddErr("");
    const at = Math.max(0, Math.floor(time * 10) / 10);
    try {
      const r = await api.overlays(dir, "add", { start: at, end: Math.min(dur || at + 4, at + 4), ...data });
      window.dispatchEvent(new Event("pf-overlays-changed"));
      onLayerSelect(r[r.length - 1]?.id ?? null);
    } catch (e) { setAddErr(errorText(e)); }
  };
  const addPicture = async () => {
    setAddMenu(false);
    const f = await openDialog({ filters: [{ name: "Picture or text sign", extensions: ["png", "jpg", "jpeg", "webp", "svg"] }] });
    if (typeof f === "string") await addLayer({ image: f, y: 0.5, width: 0.3, anim: "zoom_in" });
  };
  const room = Math.round(window.innerHeight * 0.45);                          // the timeline never takes more than this, so the player keeps its room on a small window
  useEffect(() => { if (!compact && !sized && laneN > 0 && fullHeight < Math.min(400, room)) setHeight(Math.min(400, room)); }, [laneN > 0]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    if (scroll.current) ro.observe(scroll.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const c = wave.current;
    if (!c || !map) return;
    const dpr = window.devicePixelRatio || 1;
    const W = dur * pps, H = 54;
    c.width = W * dpr; c.height = H * dpr; c.style.width = `${W}px`; c.style.height = `${H}px`;
    const g = c.getContext("2d")!;
    g.scale(dpr, dpr);
    const p = map.peaks ?? [];
    const bw = W / Math.max(1, p.length);
    g.fillStyle = "rgba(232,180,92,0.5)";
    p.forEach((v, i) => { const h = Math.max(0.5, v * (H / 2 - 2)); g.fillRect(i * bw, H / 2 - h, Math.max(1, bw - 0.3), h * 2); });
    g.fillStyle = "rgba(244,247,250,0.10)";
    for (const d of map.downbeats) g.fillRect(x(d), 0, 1, H);
    g.fillStyle = "#E8B45C";
    for (const a of map.accents) g.fillRect(x(a) - 1, H - 5, 3, 3);
  }, [map, dur, pps]);

  // keep the playhead in view while playing
  useEffect(() => {
    const s = scroll.current;
    if (!s) return;
    const px = x(time);
    if (px < s.scrollLeft + 40 || px > s.scrollLeft + s.clientWidth - 80) s.scrollLeft = Math.max(0, px - s.clientWidth * 0.3);
  }, [time]);

  const clickSeek = (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    onSeek((e.clientX - r.left) / pps);
  };

  if (!map) return <section className="timeline"><div className="tl-head">No song map yet.</div></section>;
  const reserve = 28 + Math.min(Math.max(1, laneN), 3) * LANE_H + 18;      // the transition row and up to three layer lanes fit without scrolling; more lanes scroll
  const shown = Math.max(Math.min(height, Math.round(window.innerHeight * 0.6)), compact || sized ? 0 : 34 + 136 + reserve + CARD_MIN);      // unless the person chose a height, never so short that the shot pictures are slivers
  const cardH = Math.max(compact || sized ? 40 : CARD_MIN, shown - 34 - 136 - reserve);
  // top to bottom: sections, waveform, lyrics, the layer lanes (overlay tracks sit above the video, as in an editor), the shots, the transition handles
  const laneTop = 118, lanesH = Math.max(1, laneN) * LANE_H + 10, shotsTop = laneTop + lanesH, transTop = shotsTop + cardH + 6;
  return (
    <section className="timeline" aria-label="Timeline" style={{ height: shown, ["--card-h" as string]: `${cardH}px` }}>
      <div className="tl-resize" onPointerDown={drag} title="Drag to resize" />
      <div className="tl-head">
        <span>Song Map</span>
        <div className="legend">
          <span><i className="dot" style={{ background: "var(--gold)" }} /> Music</span>
          <span><i className="dot" style={{ background: "var(--signal)" }} /> Playhead</span>
        </div>
        <div style={{ flex: 1 }} />
        {flagged > 0 && <span style={{ color: "var(--warning)", display: "flex", gap: 6, alignItems: "center" }}><I.Alert size={14} /> {flagged} shots may need attention</span>}
        <div className="tl-add">
          <button className="btn small" onClick={() => setAddMenu((v) => !v)} aria-expanded={addMenu} aria-haspopup="menu" title="Add text, a picture, a shape or an icon at the playhead">+ Layer</button>
          {addMenu && <div className="tl-add-menu" role="menu">
            <button role="menuitem" onClick={() => addLayer({ kind: "text", text: "Your text", y: 0.5, anim: "rise" })}>Text</button>
            <button role="menuitem" onClick={addPicture}>Picture…</button>
            <button role="menuitem" onClick={() => addLayer({ kind: "icon", icon: "star", x: 0.5, y: 0.5, width: 0.12, color: "#ffd166", anim: "zoom_in" })}>Icon</button>
            <button role="menuitem" onClick={() => addLayer({ kind: "shape", shape: "rounded", x: 0.5, y: 0.5, width: 0.25, height: 0.25, color: "#ffd166", anim: "fade" })}>Shape</button>
            <button role="menuitem" onClick={() => addLayer({ kind: "fill", color: "#000000", opacity: 0.4, anim: "fade" })}>Colour tint</button>
          </div>}
          {addErr && <span role="alert" style={{ color: "var(--warning)", marginLeft: 8 }}>{addErr}</span>}
        </div>
        <div className="zoom" role="group" aria-label="Zoom">
          <button className="icon-btn" onClick={() => zoom(1 / 1.5)} aria-label="Zoom out" title="Zoom out (Ctrl + scroll)">−</button>
          <button className="btn ghost small" onClick={() => { const s = scroll.current; if (s && dur) setPps(Math.floor(s.clientWidth / dur)); }}>Fit</button>
          <button className="icon-btn" onClick={() => zoom(1.5)} aria-label="Zoom in" title="Zoom in (Ctrl + scroll)">+</button>
          <button className={`btn ghost small ${compact ? "on" : ""}`} onClick={onCompact} aria-pressed={compact} title="Compact timeline: just the song map and the shots (Ctrl+Shift+J)">Compact</button>
        </div>
      </div>
      <div className="tl-scroll" ref={scroll} onScroll={(e) => setLeft((e.currentTarget as HTMLElement).scrollLeft)}>
        <div className="tl-inner" style={{ width: inner, height: Math.max(transTop + 28, 0) }} onClick={clickSeek}>
          <div className="tl-sections">
            {map.sections.map((s, i) => (
              <div key={i} className="tl-section" style={{ left: x(s.start), width: x(s.end - s.start) - 2 }}
                   onClick={(e) => { e.stopPropagation(); onSelect({ kind: "section", index: i }); onSeek(s.start); }}>
                {(s.group && s.group.length > 2 ? s.group : s.label).toUpperCase()}</div>
            ))}
          </div>
          <canvas className="tl-wave" ref={wave} />
          <div className="tl-lyrics">
            {map.lyrics.filter((l) => l.start != null && x(l.end ?? l.start!) >= left - 200 && x(l.start!) <= left + width + 200).map((l, i) => (
              <div key={i} className="tl-lyric" title={l.text} style={{ left: x(l.start!), width: Math.max(18, x((l.end ?? l.start!) - l.start!)) }}>{l.text}</div>
            ))}
          </div>
          <div className="tl-shots" style={{ top: shotsTop }}>
            <StoryCards dir={dir} shots={board} pps={pps} view={[left, left + width]} selected={sel?.kind === "shot" ? sel.id : null}
                        thumbs={thumbs} want={want} onOpen={onOpen} onSelect={(id) => onSelect({ kind: "shot", id })} />
          </div>
          <TransitionHandles dir={dir} shots={board} pps={pps} top={transTop} onChanged={onBoardChanged} />
          <LayerLanes dir={dir} pps={pps} duration={dur} selected={layerSel} onSelect={onLayerSelect} top={laneTop} onCount={setLaneN} time={time} onSeek={onSeek}
                      snap={snapPoints({ downbeats: map.downbeats, lyrics: map.lyrics, shots: board, playhead: time })} />
          <div className="playhead" style={{ left: x(time) }} />
        </div>
      </div>
    </section>
  );
}

/** Aspect, quality and lip-sync for every render in the project. Changes apply to new takes. */
function ProjectSettingsRow({ project }: { project: LoadedProject }) {
  const [s, setS] = useState({
    aspect_ratio: project.project.aspect_ratio ?? "16:9", quality: project.project.quality ?? "standard",
    lip_sync: project.project.lip_sync ?? "auto",
    vocalist: (project.project as { vocalist?: string }).vocalist ?? "onscreen",
  });
  const [err, setErr] = useState("");
  const change = async (k: keyof typeof s, v: string) => {
    const next = { ...s, [k]: v };
    setS(next); setErr("");
    try { if (k === "aspect_ratio" || k === "quality") await saveFrame(project.dir, k, v); else if (k === "vocalist") await api.setProjectSettings(project.dir, { vocalist: v as "onscreen" | "offscreen" }); else await api.setProjectSettings(project.dir, { lip_sync: v as "auto" | "closeups" | "off" }); } catch (e) { setErr(errorText(e)); }
  };
  return (
    <div className="insp-section">
      <h4>Frame & quality</h4>
      <div className="kv settings-kv">
        <span className="k">Aspect</span>
        <select className="text-input" value={s.aspect_ratio} onChange={(e) => change("aspect_ratio", e.target.value)}>
          {ASPECTS.map(([v, l]) => <option key={v} value={v}>{v} · {l}</option>)}
        </select>
        <span className="k">Quality</span>
        <select className="text-input" value={s.quality} onChange={(e) => change("quality", e.target.value)}>
          {QUALITY.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <span className="k">Lip-sync</span>
        <select className="text-input" value={s.lip_sync} onChange={(e) => change("lip_sync", e.target.value)}>
          <option value="auto">Auto · singing shots follow the vocal</option>
          <option value="closeups">Close-ups get a dedicated lip-sync pass</option>
          <option value="off">Off</option>
        </select>
        <span className="k">Who sings</span>
        <select className="text-input" value={s.vocalist} onChange={(e) => change("vocalist", e.target.value)} aria-label="Who sings the vocal">
          <option value="onscreen">The people on screen (the lead, in medium shots and closer)</option>
          <option value="offscreen">A narrator or voice-over: nobody on screen sings</option>
        </select>
      </div>
      <p className="dim" style={{ marginTop: 6 }}>Applies to new takes. Each model uses its closest supported option.</p>
      {err && <div className="error-text">{err}</div>}
    </div>
  );
}
