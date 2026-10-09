import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, type BudgetStatus, type Concept, type EngineEvent, type Estimate, type Job, type LoadedProject } from "./api";
import { useRouting } from "./Routing";
import { PROVIDER_NAME } from "./Render";
import * as I from "./icons";

/**
 * Autopilot: song → finished video on one screen. Every step is worked out from the project itself (so it resumes
 * after a restart and never repeats paid work); it stops only for your decisions: the direction, and each price.
 *   listen → plan → direct → keyframes (+ keyframe check) → approve → video → review & fix → export
 */
export const openAutopilot = () => window.dispatchEvent(new Event("pf-open-autopilot"));

type StepId = "listen" | "plan" | "direct" | "keyframes" | "approve" | "preview" | "video" | "fix" | "export";
type StepState = "done" | "active" | "waiting" | "blocked" | "todo" | "skipped";
const STEPS: { id: StepId; title: string; what: string }[] = [
  { id: "listen", title: "Listen to the song", what: "Beats, sections, energy and lyric timing. Free, on this computer." },
  { id: "plan", title: "Plan the story", what: "Your script, or one of three creative directions you choose." },
  { id: "direct", title: "Direct every shot", what: "Acting, camera, lighting and intent for each shot (AI)." },
  { id: "keyframes", title: "Make keyframes", what: "A still for every shot. Each is checked; bad ones are re-made once." },
  { id: "approve", title: "Approve keyframes", what: "The best still of each shot becomes where its video starts." },
  { id: "preview", title: "Watch a free preview", what: "Every shot as a moving still from its keyframe, cut to the song. Free. Then choose which shots get real video." },
  { id: "video", title: "Render the video", what: "The shots you choose, animated from their keyframes. The rest stay moving stills." },
  { id: "fix", title: "Review and fix", what: "Takes the reviewer flags as needing attention get one corrected re-render." },
  { id: "export", title: "Export", what: "The finished music video, frame-exact to the song." },
];
const VIDEO_MODELS: Record<string, { label: string; fal?: string; kie?: string }> = {
  hailuo: { label: "Hailuo 2.3 · lowest price", fal: "fal-ai/minimax/hailuo-2.3/standard/image-to-video", kie: "hailuo/2-3-image-to-video-standard" },
  wan: { label: "Wan 3.0 · cheap, good", fal: "alibaba/wan-3.0/image-to-video", kie: "wan/3-0-video" },
  kling: { label: "Kling · stronger motion", fal: "fal-ai/kling-video/v3/turbo/pro/image-to-video", kie: "kling-2.6/image-to-video" },
  seedance: { label: "Seedance 2 · best consistency, priciest", fal: "bytedance/seedance-2.0/reference-to-video", kie: "bytedance/seedance-2" },
};
const IMAGE_MODELS: Record<string, string> = { fal: "fal-ai/nano-banana/edit", kie: "google/nano-banana-edit" };
const ACTIVE = ["queued", "submitting", "submitted"];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Autopilot({ project: initial, onClose, onReload }: { project: LoadedProject; onClose: () => void; onReload: () => void }) {
  const dir = initial.dir;
  const [p, setP] = useState<LoadedProject>(initial);
  const [pending, setPending] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [previewFile, setPreviewFile] = useState(() => { try { return localStorage.getItem(`pf-preview-file:${dir}`) ?? ""; } catch { return ""; } });
  const [splitPlan, setSplitPlan] = useState<null | { kie: string[]; fal: string[]; kie_credits: number; fal_usd: number | null }>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [provider, setProvider] = useState<"fal" | "kie">("kie");
  const [family, setFamily] = useState<keyof typeof VIDEO_MODELS>("wan");
  const { route } = useRouting(dir);
  useEffect(() => {
    if (route?.mode === "premium" && route.chosen) setFamily("seedance");
    else if (route?.mode === "balanced") setFamily("wan");
    else if (route?.mode === "cheapest") {   // the family of whatever the Cheapest mode priced lowest
      const f = (Object.keys(VIDEO_MODELS) as (keyof typeof VIDEO_MODELS)[]).find((k) => Object.values(VIDEO_MODELS[k]).includes(route.video.model ?? ""));
      if (f) setFamily(f);
    }
  }, [route?.mode, route?.chosen, route?.video.model]);
  const [gate, setGate] = useState<null | { step: StepId; shots: string[]; all?: string[]; est: Estimate | null; kind: "image" | "video"; provider: "fal" | "kie" | "comfyui"; pricing?: boolean }>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [concepts, setConcepts] = useState<Concept[]>(initial.concepts?.concepts ?? []);
  const [running, setRunning] = useState(true);
  const [loaded, setLoaded] = useState(false);   // never act on a half-read project (it would look unrendered)
  const runningRef = useRef(true);
  runningRef.current = running;

  // ---- read the project's real state
  const refresh = useCallback(async () => {
    const x = await api.loadProject(dir);
    setP(x);
    const [pk, sb] = await Promise.all([
      api.library<Record<string, string>>(dir, "pending_keyframes").catch(() => ({})),
      api.storyboard(dir).catch(() => null)]);
    setPending(pk);
    if (sb) setChosen(Object.fromEntries(sb.shots.map((s) => [s.id, !!s.preview && s.preview_kind !== "image"])));   // a moving still isn't video yet
    if (sb || !(x.directed ?? x.production)) setLoaded(true);
    return x;
  }, [dir]);
  useEffect(() => { refresh(); api.budget(dir).then(setBudget).catch(() => {}); }, [refresh, dir]);
  useEffect(() => {  // default provider: the one that can pay
    if (!budget) return;
    const fal = budget.balances.fal, kie = budget.balances.kie;
    setProvider(fal?.known && (fal.amount ?? 0) > 1 ? "fal" : kie?.known && (kie.amount ?? 0) > 100 ? "kie" : fal?.known === false ? "fal" : "kie");
  }, [budget]);
  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => { if (e.stage && ["analysis", "director", "concepts", "treatment", "export"].includes(e.task)) setBusy(cap(e.stage) + "…"); });
    return () => { un.then((f) => f()); };
  }, []);

  const plan = p.directed ?? p.production;
  const shots = plan?.scenes.flatMap((s) => s.shots) ?? [];
  const jobs = p.jobs ?? [];
  const planName = p.directed ? "directed" : "production";
  const kf = (p.keyframes ?? {})[planName] ?? {};
  const active = (kind: "image" | "video") => jobs.filter((j) => j.plan === planName && ACTIVE.includes(j.state) && (kind === "image" ? j.kind === "image" : j.kind !== "image"));
  const paused = jobs.filter((j) => j.state === "queued" && j.error_kind === "credits");
  const needKf = shots.filter((s) => !kf[s.id] && !pending[s.id]).map((s) => s.id);
  const needVideo = shots.filter((s) => !chosen[s.id]).map((s) => s.id);
  const takesInUse = latestReady(jobs, planName);
  const flagged = shots.filter((s) => { const j = takesInUse.get(s.id); return j?.review?.status === "needs_attention" && !j.review.accepted && !j.fix_notes?.length; }).map((s) => s.id);
  const newestTake = Math.max(0, ...jobs.filter((j) => j.state === "ready" && j.kind !== "image").map((j) => j.updated ?? j.created));
  const failedChecks = jobs.filter((j) => j.kind === "image" && j.plan === planName && (j as Job & { still_check?: { ok: boolean | null } }).still_check?.ok === false).length;

  const state = (id: StepId): StepState => {
    switch (id) {
      case "listen": return p.song_map ? "done" : "todo";
      case "plan": return plan ? "done" : p.song_map ? "todo" : "waiting";
      case "direct": return p.directed ? "done" : plan ? "todo" : "waiting";
      case "keyframes": return !p.directed ? "waiting" : active("image").length ? "active" : needKf.length ? "todo" : "done";
      case "approve": return !p.directed || active("image").length || needKf.length ? "waiting" : Object.keys(pending).length ? "todo" : "done";
      case "preview": return !p.directed || Object.keys(kf).length < shots.length ? "waiting" : !needVideo.length || previewFile ? "done" : "todo";
      case "video": return !p.directed || Object.keys(kf).length < shots.length || (needVideo.length && !previewFile) ? "waiting" : paused.length ? "blocked" : active("video").length ? "active" : needVideo.length ? "todo" : "done";
      case "fix": return needVideo.length || active("video").length || !shots.length ? "waiting" : flagged.length ? "todo" : "done";
      case "export": return needVideo.length || active("video").length || !shots.length ? "waiting" : exportedAt(dir) >= newestTake ? "done" : "todo";
    }
  };
  const current = STEPS.find((s) => !["done", "skipped"].includes(state(s.id)));

  // ---- one step at a time; paid steps open a gate and wait for you
  const act = useCallback(async (id: StepId) => {
    setError("");
    try {
      if (id === "listen") { setBusy("Listening…"); await api.analyzeProject(dir); }
      else if (id === "plan") {
        if (!concepts.length) {
          if (!(await api.aiReady())) throw new Error("Choose an AI brain in Settings (OpenAI or a local model) to plan the story.");
          setBusy("Imagining three directions…");
          setConcepts((await api.creativeDirections(dir, p.project.onboarding?.concept_notes ?? "")).concepts);
        }
        setBusy(""); return;   // your choice: the cards below
      }
      else if (id === "direct") {
        if (!(await api.aiReady())) throw new Error("Choose an AI brain in Settings (OpenAI or a local model) to direct the shots.");
        setBusy("Directing…"); await api.directProject(dir);
      }
      else if (id === "preview") {
        setBusy("Making moving stills and cutting a free preview…");
        const r = await api.golden<{ export: { path: string } }>(dir, "preview");
        try { localStorage.setItem(`pf-preview-file:${dir}`, r.export.path); } catch { /* optional */ }
        setPreviewFile(r.export.path); setBusy(""); setRunning(false); await refresh(); onReload();   // stop so you can watch it
        return;
      }
      else if (id === "keyframes" || id === "video" || id === "fix") {
        const ids = id === "keyframes" ? needKf : id === "video" ? needVideo : flagged;
        const kind = id === "keyframes" ? "image" : "video";
        setBusy("Pricing…");
        await priceGate({ step: id, shots: ids, all: ids, est: null, kind, provider }, provider);
        setBusy(""); return;
      }
      else if (id === "approve") { setBusy("Approving the best keyframes…"); await api.library(dir, "approve_keyframes", {}); }
      else if (id === "export") {
        setBusy("Exporting…");
        const preset = p.project.aspect_ratio === "2.39:1" || p.project.aspect_ratio === "21:9" ? "cinema" : p.project.aspect_ratio === "9:16" ? "vertical" : p.project.aspect_ratio === "1:1" ? "square" : "youtube";
        const r = await api.exportProject(dir, preset);
        try { localStorage.setItem(`pf-autopilot-exported:${dir}`, String(newestTake)); } catch { /* optional */ }
        setBusy(""); setError(""); await refresh(); setDoneFile(r.path); return;
      }
      setBusy(""); await refresh(); onReload();
    } catch (e) { setError(errorText(e)); setBusy(""); setRunning(false); }
  }, [dir, concepts.length, p, needKf, needVideo, flagged, provider, family, refresh, onReload]);
  const [doneFile, setDoneFile] = useState("");

  /** Price a gate for one provider (and check it against that provider's balance). Switching provider re-prices. */
  const localVideo = route?.mode === "hybrid" && route.video.provider === "comfyui" ? route.video.model! : null;
  const modelFor = (kind: "image" | "video", prov: "fal" | "kie" | "comfyui") =>
    prov === "comfyui" ? localVideo! : kind === "image" ? IMAGE_MODELS[prov] : VIDEO_MODELS[family][prov]!;
  const priceGate = async (g: NonNullable<typeof gate>, prov: "fal" | "kie" | "comfyui") => {
    if (g.kind === "video" && localVideo) prov = "comfyui";   // Hybrid: videos on your ComfyUI, free
    else if (prov === "comfyui") prov = provider;
    setGate({ ...g, provider: prov, est: null, pricing: true });
    const model = modelFor(g.kind, prov);
    const est = await api.renderEstimate(dir, g.shots, prov, model, g.kind).catch(() => null);
    const need: Record<string, number> = prov === "comfyui" ? {} : prov === "fal" ? { fal: est?.usd ?? est?.usd_known ?? 0 } : { kie: est?.kie_credits_est ?? 0 };
    const b = await api.budget(dir, need).catch(() => null);
    if (b) setBudget(b);
    setGate({ ...g, provider: prov, est, pricing: false });
  };

  const confirmSplit = async () => {
    if (!gate || !splitPlan) return;
    const g = gate, sp = splitPlan; setGate(null); setSplitPlan(null); setBusy("Sending…"); setError("");
    try {
      for (const pv of ["kie", "fal"] as const) {
        const ids = sp[pv]; if (!ids.length) continue;
        const model = g.kind === "image" ? IMAGE_MODELS[pv] : VIDEO_MODELS[family][pv]!;
        await api.queueRender(dir, ids, pv, model, {}, [], g.kind);
      }
      await api.ensureRenderer(dir); setBusy(""); setRunning(true); await refresh();
    } catch (e) { setError(errorText(e)); setBusy(""); }
  };
  const planSplit = async () => {
    if (!gate) return;
    const models = gate.kind === "image" ? { kie: IMAGE_MODELS.kie, fal: IMAGE_MODELS.fal } : { kie: VIDEO_MODELS[family].kie, fal: VIDEO_MODELS[family].fal };
    setBusy("Working out the split…");
    try { setSplitPlan(await api.golden(dir, "split", { shots: gate.shots, kind: gate.kind, models })); } catch (e) { setError(errorText(e)); }
    finally { setBusy(""); }
  };
  const toggleShot = (id: string) => {
    if (!gate) return;
    const shots = gate.shots.includes(id) ? gate.shots.filter((x) => x !== id) : [...gate.shots, id].sort();
    setSplitPlan(null);
    if (shots.length) priceGate({ ...gate, shots }, gate.provider); else setGate({ ...gate, shots, est: null });
  };

  const confirmGate = async () => {
    if (!gate) return;
    const g = gate; setGate(null); setBusy("Sending…"); setError("");
    const provider = g.provider;
    try {
      const model = modelFor(g.kind, provider);
      if (g.step === "fix") {
        for (const id of g.shots) {
          const t = takesInUse.get(id);
          await api.queueRender(dir, [id], provider, model, {}, t?.review?.fixes ?? []);
        }
      } else {
        await api.queueRender(dir, g.shots, provider, model, {}, [], g.kind);
      }
      await api.ensureRenderer(dir);
      setBusy(""); setRunning(true); await refresh();
    } catch (e) { setError(errorText(e)); setBusy(""); }
  };

  // ---- keep moving: free steps run by themselves; renders are watched until they settle
  useEffect(() => {
    if (!loaded || !running || busy || gate || doneFile) return;
    const s = current ? state(current.id) : null;
    let stop = false;
    (async () => {
      if (!current) return;
      if (s === "active" || active("image").length || active("video").length) { await sleep(6000); if (!stop) await refresh(); return; }
      if (s === "blocked") { setRunning(false); return; }
      if (s === "todo") {
        if (current.id === "plan" && concepts.length) return;   // waiting for your pick
        if (current.id === "fix" && flagged.length === 0) return;
        await act(current.id);
      }
    })();
    return () => { stop = true; };
  }, [loaded, running, busy, gate, doneFile, current?.id, p, pending, chosen, concepts.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (gate && state(gate.step) === "done") setGate(null); });   // a gate for work that turned out done is stale

  const pickDirection = async (i: number) => {
    setBusy("Writing the treatment and planning shots…"); setError("");
    try { await api.writeTreatment(dir, i, p.project.onboarding?.concept_notes ?? ""); setBusy(""); await refresh(); onReload(); }
    catch (e) { setError(errorText(e)); setBusy(""); }
  };
  const reroute = async (from: string) => {
    setBusy("Moving unsent renders…");
    try { const r = await api.reroute(dir, from); await api.ensureRenderer(dir); setBusy(""); setRunning(true); await refresh();
      if (r.stuck.length) setError(`No equivalent model for: ${r.stuck.join(", ")}`); }
    catch (e) { setError(errorText(e)); setBusy(""); }
  };

  const spent = budget?.spent;
  const fit = gate && !gate.pricing ? budget?.fits[gate.provider] : null;
  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass autopilot" role="dialog" aria-label="Autopilot" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Make my video</h2><span className="chip gold">Autopilot</span><div style={{ flex: 1 }} />
          {spent && <span className="dim num" title={`fal ≈ $${spent.fal_usd} · Kie ${spent.kie_credits} credits ≈ $${spent.kie_usd}`}>Spent ≈ ${spent.total_usd.toFixed(2)}</span>}
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">PULSEFRAME works through every step and stops only for your decisions: the direction, and each price.
          You can close this; renders continue, and Autopilot picks up where it stopped.</p>

        <div className="ap-balances">
          {(["fal", "kie"] as const).map((pv) => { const b = budget?.balances[pv]; return (
            <button key={pv} className={`ap-bal ${(gate?.provider ?? provider) === pv ? "on" : ""}`} disabled={!!gate?.pricing}
                    onClick={() => { setProvider(pv); if (gate) priceGate(gate, pv); }}>
              <b>{PROVIDER_NAME[pv]}</b>
              <span className={b?.known && (b.amount ?? 0) <= 0 ? "neg" : ""}>{!b ? "…" : !b.known ? "balance unknown" : b.unit === "usd" ? `$${b.amount?.toFixed(2)}` : `${Math.round(b.amount ?? 0).toLocaleString()} credits ≈ $${b.usd}`}</span>
            </button>); })}
          <select className="text-input ap-model" value={family} aria-label="Video model" disabled={!!gate?.pricing}
                  onChange={(e) => { setFamily(e.target.value as keyof typeof VIDEO_MODELS); if (gate?.kind === "video") setTimeout(() => priceGate(gate, gate.provider)); }}>
            {Object.entries(VIDEO_MODELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>

        <ol className="ap-steps">
          {STEPS.map((s, i) => {
            const st = state(s.id);
            const isCur = current?.id === s.id;
            return (
              <li key={s.id} className={`ap-step ${st} ${isCur ? "current" : ""}`}>
                <span className="ap-dot">{st === "done" ? <I.Check size={14} /> : st === "active" ? <span className="spin sm" /> : st === "blocked" ? <I.Alert size={13} /> : i + 1}</span>
                <div className="ap-body">
                  <div className="ap-title">{s.title} <span className="dim">{detail(s.id)}</span></div>
                  {isCur && <div className="dim">{s.what}</div>}
                  {isCur && s.id === "plan" && concepts.length > 0 && !plan && (
                    <div className="ap-concepts">{concepts.map((c, k) => (
                      <button key={k} className="ap-concept" disabled={!!busy} onClick={() => pickDirection(k)}>
                        <b>{c.title}</b><span>{c.premise}</span><em>{c.narrative_level}</em></button>))}</div>)}
                  {isCur && st === "blocked" && paused.length > 0 && (
                    <div className="ap-gate warn">
                      <b>{PROVIDER_NAME[paused[0].provider]} ran out of balance.</b> {paused.length} render{paused.length > 1 ? "s are" : " is"} waiting (not charged).
                      <div className="wiz-row" style={{ marginTop: 8 }}>
                        <button className="btn primary" onClick={() => reroute(paused[0].provider)}>Continue on {PROVIDER_NAME[paused[0].provider === "fal" ? "kie" : "fal"]} with the same model</button>
                        <button className="btn ghost" onClick={async () => { await api.ensureRenderer(dir); setRunning(true); }}>I topped up: retry</button>
                      </div></div>)}
                  {isCur && s.id === "preview" && previewFile && <div className="ap-preview"><video src={api.mediaUrl(previewFile)} controls /></div>}
                  {s.id === "video" && previewFile && st !== "waiting" && !gate && <div className="ap-preview small"><video src={api.mediaUrl(previewFile)} controls /></div>}
                  {gate?.step === s.id && (
                    <div className="ap-gate">
                      {s.id === "video" && (gate.all?.length ?? 0) > 1 && <div className="ap-pick">
                        <div className="dim">Choose the shots that get real video (the rest stay moving stills): {gate.shots.length} of {gate.all!.length}
                          {" "}<button className="link" onClick={() => priceGate({ ...gate, shots: gate.all! }, gate.provider)}>all</button>
                          {" · "}<button className="link" onClick={() => setGate({ ...gate, shots: [], est: null })}>none</button></div>
                        <div className="ap-pick-chips">{gate.all!.map((id) => <button key={id} className={`chip num ${gate.shots.includes(id) ? "on" : ""}`}
                                                                             onClick={() => toggleShot(id)} disabled={!!gate.pricing}>{id}</button>)}</div>
                      </div>}
                      <div><b>{s.id === "keyframes" ? `Make ${gate.shots.length} keyframes` : s.id === "fix" ? `Fix ${gate.shots.length} flagged shots` : `Render ${gate.shots.length} shots`}</b>
                        {" "}on {PROVIDER_NAME[gate.provider]} · {gate.kind === "image" ? "Nano Banana" : VIDEO_MODELS[family].label.split(" ·")[0]}</div>
                      <div className="ap-price">{gate.pricing ? "Pricing…" : gate.est?.usd != null ? `≈ $${gate.est.usd.toFixed(2)}` : gate.est?.kie_credits_est ? `≈ ${gate.est.kie_credits_est.toLocaleString()} Kie credits (≈ $${(gate.est.kie_credits_est * 0.005).toFixed(2)})` : "Price shown after rendering"}
                        {gate.kind === "image" && <span className="dim"> · keyframes that fail the check are re-made once (a few cents more)</span>}</div>
                      {fit && fit.fits === null && fit.reason && <div className="dim" style={{ color: "var(--warning)", fontSize: 12.5 }}>{fit.reason}</div>}
                      {fit && fit.fits === false && <div className="error-text">{fit.reason ?? `Not enough balance (short by ${fit.short}). Top up or choose the other provider above.`}</div>}
                      {fit && fit.fits === false && gate.kind !== undefined && !splitPlan && <button className="btn ghost small" onClick={planSplit}>Split across Kie and fal</button>}
                      {splitPlan && <div className="ap-split">
                        {splitPlan.kie.length} on Kie (≈ {splitPlan.kie_credits.toLocaleString()} credits) · {splitPlan.fal.length} on fal
                        {splitPlan.fal_usd != null ? ` (≈ $${splitPlan.fal_usd.toFixed(2)})` : ""}
                        <button className="btn primary small" onClick={confirmSplit} disabled={!splitPlan.kie.length && !splitPlan.fal.length}>Go · split</button>
                        <button className="btn ghost small" onClick={() => setSplitPlan(null)}>Cancel</button></div>}
                      <div className="wiz-row" style={{ marginTop: 8 }}>
                        <button className="btn primary" onClick={confirmGate} disabled={fit?.fits === false || !!gate.pricing || !gate.shots.length}>Go · {PROVIDER_NAME[gate.provider]}</button>
                        <button className="btn ghost" onClick={() => { setGate(null); setRunning(false); }}>Not now</button>
                        {s.id === "fix" && <button className="btn ghost" onClick={() => { setGate(null); markSkipFix(dir); setRunning(true); refresh(); }}>Skip fixes</button>}
                      </div></div>)}
                </div>
              </li>
            );
          })}
        </ol>

        {busy && <div className="ap-busy" role="status"><span className="spin" /> {busy}</div>}
        {error && <div className="error-text" role="alert">{error}</div>}
        {doneFile && <div className="ap-done"><I.Check size={18} /> Your music video is ready: <span className="num">{doneFile.split(/[\\/]/).pop()}</span></div>}
        <div className="sheet-actions">
          {!running && !doneFile && <button className="btn primary" onClick={() => { setRunning(true); setError(""); }}>{current ? "Continue" : "Start"}</button>}
          {running && !doneFile && <button className="btn ghost" onClick={() => setRunning(false)}>Pause</button>}
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );

  function detail(id: StepId) {
    if (id === "keyframes") return `${shots.length - needKf.length}/${shots.length}${failedChecks ? ` · ${failedChecks} failed the check` : ""}`;
    if (id === "approve") return `${Object.keys(kf).length}/${shots.length} approved`;
    if (id === "preview") return previewFile ? "ready to watch" : "";
    if (id === "video") return `${shots.length - needVideo.length}/${shots.length}${active("video").length ? ` · ${active("video").length} rendering` : ""}`;
    if (id === "fix") return flagged.length ? `${flagged.length} flagged` : "";
    return "";
  }
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
function latestReady(jobs: Job[], plan: string) {
  const m = new Map<string, Job>();
  for (const j of jobs) if (j.plan === plan && j.state === "ready" && j.kind !== "image") {
    const c = m.get(j.shot_id); if (!c || j.created >= c.created) m.set(j.shot_id, j);
  }
  return m;
}
/** "Skip fixes": accept the flagged takes as they are (the Review panel can still fix them later). */
async function markSkipFix(dir: string) {
  const p = await api.loadProject(dir);
  const plan = p.directed ? "directed" : "production";
  for (const [, j] of latestReady(p.jobs ?? [], plan)) {
    if (j.review?.status === "needs_attention" && !j.review.accepted) await api.resolveJob(dir, j.id, "accept").catch(() => {});
  }
}

function exportedAt(dir: string) { try { return Number(localStorage.getItem(`pf-autopilot-exported:${dir}`) || 0); } catch { return 0; } }

/** Top bar: what this project has cost so far (fal estimates + Kie credits), refreshed as renders finish. */
export function SpendChip({ dir, jobsSig }: { dir: string; jobsSig: string }) {
  const [b, setB] = useState<BudgetStatus | null>(null);
  const last = useRef(0);
  useEffect(() => {
    if (Date.now() - last.current < 20000 && b) return;
    last.current = Date.now();
    api.budget(dir).then(setB).catch(() => {});
  }, [dir, jobsSig]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!b?.spent) return null;
  const fal = b.balances.fal, kie = b.balances.kie;
  const low = (fal?.known && (fal.amount ?? 0) <= 0) || (kie?.known && (kie.amount ?? 0) < 200);
  return (
    <span className={`spend-chip ${low ? "low" : ""}`} title={`Spent on this project: fal ≈ $${b.spent.fal_usd} (estimates) · Kie ${b.spent.kie_credits} credits ≈ $${b.spent.kie_usd}
` +
      `Balances: fal ${fal?.known ? "$" + fal.amount : "unknown"} · Kie ${kie?.known ? Math.round(kie.amount ?? 0) + " credits" : "unknown"}`}>
      <span className="num">${b.spent.total_usd.toFixed(2)}</span> spent{low && <I.Alert size={12} />}
    </span>
  );
}
