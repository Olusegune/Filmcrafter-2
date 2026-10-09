import { listPrice } from "./price";
import { useCallback, useEffect, useState } from "react";
import { api, errorText, type EngineEvent } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

export type Pick = { provider: string | null; model?: string; label?: string; free: boolean; mode: string; reason?: string; verified?: boolean; price_usd?: number | null; pinned?: boolean };
type ModelRow = { label: string; provider: string; model: string; price_usd: number | null; verified: boolean; strength?: string; consider?: string; watch?: string };
export type RouteStatus = { mode: "cheapest" | "hybrid" | "local" | "balanced" | "premium"; budget_usd: number | null; chosen: boolean; spent_usd: number;
  remaining_usd: number | null; online: boolean; modes: { id: string; label: string; blurb: string }[];
  video: Pick; image: Pick; brain: { provider: string; local: boolean }; works_offline: string[];
  auto_retry?: boolean;
  consistency?: { image_models: { provider: string; model: string; label: string; count: number }[]; mixed: boolean; pinned: boolean; advice: string } };

const cache = new Map<string, RouteStatus>();
const listeners = new Set<() => void>();

/** Routing status for a project, shared by every panel (one engine call, refreshed when changed). */
export function useRouting(dir: string) {
  const [s, setS] = useState<RouteStatus | null>(cache.get(dir) ?? null);
  const load = useCallback(() => api.routing<RouteStatus>(dir, "status").then((r) => { cache.set(dir, r); listeners.forEach((f) => f()); }).catch(() => {}), [dir]);
  useEffect(() => {
    const f = () => setS(cache.get(dir) ?? null);
    listeners.add(f);
    if (!cache.has(dir)) load();
    return () => { listeners.delete(f); };
  }, [dir, load]);
  return { route: s, reloadRoute: load };
}

const fmt = (n: number) => `$${n.toFixed(2)}`;

/** Plan & budget: Local First / Balanced / Premium, the project budget, and what works offline. */
export function RoutingSheet({ dir, onClose }: { dir: string; onClose: () => void }) {
  const { route, reloadRoute } = useRouting(dir);
  const [budget, setBudget] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { if (route) setBudget(route.budget_usd ? String(route.budget_usd) : ""); }, [route?.budget_usd]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = async (data: Record<string, unknown>) => {
    setErr("");
    try { const r = await api.routing<RouteStatus>(dir, "set", data); cache.set(dir, r); await reloadRoute(); } catch (e) { setErr(errorText(e)); }
  };
  if (!route) return null;
  const pct = route.budget_usd ? Math.min(100, (route.spent_usd / route.budget_usd) * 100) : 0;
  const pickText = (p: Pick) => p.provider ? `${p.label} on ${p.provider === "comfyui" ? "your ComfyUI" : p.provider}${p.free ? " (free)" : p.price_usd != null ? ` · about $${p.price_usd.toFixed(2)} per ${p === route.image ? "still" : "5-second shot"}` : ""}` : p.reason;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass route-sheet" role="dialog" aria-label="Plan and budget" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Plan & budget</h2><div style={{ flex: 1 }} />
          <span className={`net-pill ${route.online ? "on" : "off"}`}>{route.online ? "Online" : "Offline"}</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Where this project's work runs, and the most it may spend. Auto renders follow the mode; you can still pick any
          model for a shot in Director Mode (the budget still applies).</p>
        {err && <div className="error-text">{err}</div>}
        <div className="route-modes" role="radiogroup">{route.modes.map((m) => (
          <button key={m.id} role="radio" aria-checked={route.mode === m.id} className={`perf-card ${route.mode === m.id ? "on" : ""}`}
                  onClick={() => set({ mode: m.id })}><b>{m.label}</b><span>{m.blurb}</span></button>))}</div>
        <div className="kv settings-kv route-kv">
          <span className="k">Videos render with</span><span>{pickText(route.video)}</span>
          <span className="k">Keyframes render with</span><span>{pickText(route.image)}</span>
          <span className="k">AI brain</span><span>{route.brain.local ? "A local model on this computer (free)" : "OpenAI (small cost per plan or check)"}</span>
        </div>
        <ModelPicker dir={dir} route={route} onChanged={reloadRoute} />
        <AutoRetry dir={dir} route={route} onChanged={reloadRoute} />
        <h3 className="perf-h">Project budget</h3>
        <div className="wiz-row route-budget">
          <span>$</span>
          <input className="text-input" inputMode="decimal" placeholder="No limit" value={budget} onChange={(e) => setBudget(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && set({ budget_usd: budget })} />
          <button className="btn" onClick={() => set({ budget_usd: budget })} disabled={budget === (route.budget_usd ? String(route.budget_usd) : "")}>Save</button>
          <span className="dim">Spent so far {fmt(route.spent_usd)}{route.remaining_usd !== null ? ` · ${fmt(Math.max(0, route.remaining_usd))} left` : ""}</span>
        </div>
        {route.budget_usd && <div className={`route-bar ${pct >= 90 ? "hot" : ""}`}><i style={{ width: `${pct}%` }} /></div>}
        <p className="dim">A batch that would go past the budget is refused before anything is sent. Kie credits count at $0.005 each;
          models without a published price count high ($1 per video, $0.25 per still) so the budget is never under-counted.</p>
        <h3 className="perf-h">Works without internet</h3>
        <ul className="route-offline">{route.works_offline.map((w) => <li key={w}><I.Check size={12} /> {w}</li>)}</ul>
      </div>
    </div>
  );
}

/** Top-bar chip: the mode and spend; opens Plan & budget. */
export function RouteChip({ dir, onOpen, sig }: { dir: string; onOpen: () => void; sig: string }) {
  const { route, reloadRoute } = useRouting(dir);
  useEffect(() => { reloadRoute(); }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!route) return null;
  const label = route.modes.find((m) => m.id === route.mode)?.label ?? route.mode;
  const over = route.remaining_usd !== null && route.remaining_usd <= 0;
  return (
    <button className={`spend-chip route-chip ${over ? "low" : ""}`} onClick={onOpen} title="Plan & budget">
      <span className={`rc-dot ${route.online ? "" : "off"}`} title={route.online ? "Online" : "Offline"} />
      <span className="rc-mode">{label}</span>
      <span className="rc-sep" />
      <span className="num">{fmt(route.spent_usd)}</span>
      {route.budget_usd ? <span className="rc-dim">/ {fmt(route.budget_usd)}</span> : <span className="rc-dim">spent</span>}
    </button>
  );
}

/** Settings: models on this computer. Download and remove Ollama models, choose what plans and what sees. */
type Fit = "great" | "slow" | "too_big" | "unknown";
export type Hardware = { summary: string; ram_gb: number | null; disk_free_gb: number | null; model_gb: number; kind: "gpu" | "unified" | "cpu" };
type TestResult = { ok: boolean; model: string; seconds: number; answer: string; vision: boolean; saw?: boolean; note?: string };
export const FIT_LABEL: Record<Fit, string> = { great: "Runs fast", slow: "Runs slowly", too_big: "Too big for this computer", unknown: "" };
type LocalStatus = { hardware?: Hardware; ollama_loaded?: { name: string; gb: number; gpu_gb: number }[]; installed?: { ollama: string | null; lmstudio: string | null; lms: string | null }; ollama: { running: boolean; models: { name: string; size_gb: number; vision: boolean; params?: string; fit?: Fit }[] };
  lmstudio: { running: boolean; models: { name: string; vision: boolean }[] }; comfyui: { connected: boolean; device?: string; workflows: { title: string; kind: string }[] };
  brain: { provider: string; model: string; vision_model: string }; recommended: { name: string; role: string; size_gb: number; why: string; installed: boolean; fit?: Fit; fit_note?: string }[] };

export function LocalModelsPanel() {
  const [s, setS] = useState<LocalStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [custom, setCustom] = useState("");
  const load = useCallback(() => api.localModels<LocalStatus>("status").then(setS).catch((e) => setErr(errorText(e))), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => { if (e.task === "localmodels" && e.stage) setBusy(`${e.stage[0].toUpperCase()}${e.stage.slice(1)}${typeof e.progress === "number" ? ` ${Math.round(e.progress * 100)}%` : ""}`); });
    return () => { un.then((f) => f()); };
  }, []);
  const [tested, setTested] = useState<TestResult | null>(null);
  const runTest = async (data: Record<string, unknown>, label: string) => {
    setBusy(label); setErr(""); setTested(null);
    try { setTested(await api.localModels<TestResult>("test", data)); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const act = async (action: "pull" | "delete" | "use" | "start" | "lms_get" | "unload", data: Record<string, unknown>, label: string) => {
    setBusy(label); setErr("");
    try { setS(await api.localModels<LocalStatus>(action, data)); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  if (!s) return null;
  const role = (n: string) => [s.brain.model === n && s.brain.provider !== "openai" ? "plans" : "", s.brain.vision_model === n && s.brain.provider !== "openai" ? "sees" : ""].filter(Boolean).join(" & ");
  return (
    <div className="field local-models">
      <div className="wiz-row" style={{ justifyContent: "space-between" }}><label>Models on this computer</label>
        <button className="btn ghost small" onClick={load} disabled={!!busy}>Refresh</button></div>
      {s.hardware && <div className="lm-hw" role="note"><b>This computer:</b> {s.hardware.summary}.
        {s.hardware.disk_free_gb != null && <> {s.hardware.disk_free_gb} GB free on disk.</>}
        {" "}Models are marked <span className="fit fit-great">Runs fast</span> <span className="fit fit-slow">Runs slowly</span> <span className="fit fit-too_big">Too big</span> for it.</div>}
      {!!s.ollama_loaded?.length && <div className="lm-row"><span className="dim">In memory now: {s.ollama_loaded.map((m) => `${m.name} (${m.gb} GB)`).join(", ")}. ComfyUI needs that memory to render.</span>
        <button className="btn ghost small" disabled={!!busy} onClick={async () => { for (const m of s.ollama_loaded!) await act("unload", { name: m.name }, "Freeing memory…"); }}>Free memory</button></div>}
      <div className="lm-grid">
        <div className={`diag ${s.ollama.running ? "diag-verified" : "diag-unavailable"}`}><div className="diag-head"><b>Ollama</b>
          <span className="diag-pill">{s.ollama.running ? `${s.ollama.models.length} models` : "Not running"}</span></div>
          {!s.ollama.running && (s.installed?.ollama
            ? <div className="lm-row"><span className="dim">Installed but not running.</span><button className="btn small" disabled={!!busy} onClick={() => act("start", { which: "ollama" }, "Starting Ollama…")}>Start Ollama</button></div>
            : <div className="dim">Install from ollama.com (free), then models can be downloaded here.</div>)}
          {s.ollama.models.map((m) => <div key={m.name} className="lm-row"><span><b>{m.name}</b> <span className="dim">{m.size_gb} GB{m.vision ? " · sees images" : ""}</span>{m.fit && m.fit !== "unknown" && <span className={`fit fit-${m.fit}`}>{FIT_LABEL[m.fit]}</span>}
            {role(m.name) && <span className="chip">{role(m.name)}</span>}</span>
            <span className="lm-actions">
              <button className="btn ghost small" disabled={!!busy} onClick={() => act("use", { name: m.name, role: m.vision ? "both" : "planning" }, "Saving…")}>Use</button>
              <button className="btn ghost small" disabled={!!busy} onClick={async () => { if (await ask(`Remove ${m.name} from this computer (frees ${m.size_gb} GB)? You can download it again later.`)) act("delete", { name: m.name }, "Removing…"); }}>Remove</button>
            </span></div>)}
        </div>
        <div className={`diag ${s.lmstudio.running ? "diag-verified" : "diag-unavailable"}`}><div className="diag-head"><b>LM Studio</b>
          <span className="diag-pill">{s.lmstudio.running ? `${s.lmstudio.models.length} loaded` : "Server off"}</span></div>
          {s.lmstudio.models.filter((m) => !/embed/i.test(m.name)).map((m) => <div key={m.name} className="lm-row"><span><b>{m.name}</b>{m.vision ? <span className="dim"> · sees images</span> : null}</span>
            <button className="btn ghost small" disabled={!!busy} onClick={() => act("use", { name: m.name, role: m.vision ? "both" : "planning", server: "lmstudio" }, "Saving…")}>Use</button></div>)}
          {!s.lmstudio.running && (s.installed?.lmstudio || s.installed?.lms
            ? <div className="lm-row"><span className="dim">Installed; its local server is off.</span><button className="btn small" disabled={!!busy} onClick={() => act("start", { which: "lmstudio" }, "Starting LM Studio's server…")}>Start the server</button></div>
            : <div className="dim">Install from lmstudio.ai (free).</div>)}
          {s.installed?.lms && <div className="lm-row"><span className="dim">qwen2.5-vl-7b-instruct · 6 GB · plans and sees</span>
            <button className="btn small ghost" disabled={!!busy} onClick={() => act("lms_get", { name: "qwen2.5-vl-7b-instruct" }, "LM Studio is downloading qwen2.5-vl-7b-instruct (about 6 GB)…")}>Download into LM Studio</button></div>}
        </div>
        <div className={`diag ${s.comfyui.connected ? "diag-verified" : "diag-unavailable"}`}><div className="diag-head"><b>ComfyUI</b>
          <span className="diag-pill">{s.comfyui.connected ? s.comfyui.device ?? "Connected" : "Not running"}</span></div>
          <div className="dim">{s.comfyui.workflows.length ? s.comfyui.workflows.map((w) => `${w.title} (${w.kind})`).join(" · ") : "No workflows yet (see ComfyUI above)."}</div>
        </div>
      </div>
      <div className="lm-test">
        <button className="btn small" disabled={!!busy || !s.brain.model || s.brain.provider === "openai" || s.brain.provider === "openrouter"} onClick={() => runTest({ server: s.brain.provider }, "Asking the planning model a small question…")}>Test the planning model</button>
        <button className="btn small" disabled={!!busy || !s.brain.vision_model || s.brain.provider === "openai" || s.brain.provider === "openrouter"} onClick={() => runTest({ server: s.brain.provider, vision: true }, "Showing the vision model a small picture…")}>Test the vision model</button>
        <span className="dim">Proves the whole path works before you rely on it. Nothing is charged.</span>
        {tested && <div className={tested.ok && tested.saw !== false ? "status-ok" : "error-text"} role="status">
          {tested.ok ? `${tested.model} answered in ${tested.seconds} s: “${tested.answer}”` : "No answer."}{tested.note ? ` ${tested.note}` : ""}</div>}
      </div>
      <label style={{ marginTop: 12 }}>Recommended for this computer (free, through Ollama)</label>
      <div className="lm-rec">{s.recommended.map((r) => <div key={r.name} className="lm-row"><span><b>{r.name}</b> <span className="dim">{r.size_gb} GB · {r.why}</span> {r.fit && r.fit !== "unknown" && <span className={`fit fit-${r.fit}`}>{FIT_LABEL[r.fit]}</span>}</span>
        {r.installed ? <span className="status-ok">Installed</span> :
          <button className="btn small" disabled={!!busy || !s.ollama.running || r.fit === "too_big"} title={r.fit === "too_big" ? "Too big for this computer's memory" : undefined}
            onClick={() => act("pull", { name: r.name }, `Downloading ${r.name}…`)}>Download</button>}</div>)}</div>
      <div className="wiz-row" style={{ marginTop: 8 }}>
        <input className="text-input" placeholder="Other Ollama model, e.g. mistral-small3.1" value={custom} onChange={(e) => setCustom(e.target.value)} />
        <button className="btn" disabled={!custom.trim() || !!busy || !s.ollama.running} onClick={() => act("pull", { name: custom.trim() }, `Downloading ${custom.trim()}…`)}>Download</button>
      </div>
      {busy && <div className="dim" style={{ marginTop: 6 }}><span className="spin sm" /> {busy}</div>}
      {err && <div className="error-text">{err}</div>}
    </div>
  );
}

/** Off by default. When a video fails during a render, FilmCrafter can send that shot once to the cheapest proven model that costs less, inside the budget. */
function AutoRetry({ dir, route, onChanged }: { dir: string; route: RouteStatus; onChanged: () => Promise<void> }) {
  const [err, setErr] = useState("");
  if (route.mode === "local") return null;
  const on = !!route.auto_retry;
  const set = async (v: boolean) => { setErr(""); try { await api.routing(dir, "set", { auto_retry: v }); await onChanged(); } catch (e) { setErr(errorText(e)); } };
  return (
    <div className="mc-auto-retry">
      <label><input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} /> Retry failed videos on a cheaper model automatically</label>
      <p className="dim">If a video fails mid-render, retry that shot once on a cheaper proven model. Never for pictures, never past the budget. You can also do it by hand from the Render queue.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

/** Every model on your providers with its real price per shot; pin one to use it whatever the mode. */
function ModelPicker({ dir, route, onChanged }: { dir: string; route: RouteStatus; onChanged: () => Promise<void> }) {
  const [m, setM] = useState<{ video: ModelRow[]; image: ModelRow[] } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.routing<{ video: ModelRow[]; image: ModelRow[] }>(dir, "models").then(setM).catch(() => {}); }, [dir]);
  const pin = async (kind: "video" | "image", row: ModelRow | null) => {
    setErr("");
    try { await api.routing(dir, "set", { pin: row ? { kind, provider: row.provider, model: row.model } : { kind, clear: true } }); await onChanged(); }
    catch (e) { setErr(errorText(e)); }
  };
  if (!m || route.mode === "local") return null;
  const section = (kind: "video" | "image", rows: ModelRow[]) => {
    const cur = kind === "video" ? route.video : route.image;
    return (
      <div className="mp-col">
        <div className="mp-head"><b>{kind === "video" ? "Video models" : "Keyframe models"}</b>
          {cur.pinned ? <button className="link" onClick={() => pin(kind, null)}>Back to the mode's choice</button> : <span className="dim">using the mode's choice</span>}</div>
        <div className="mp-list">{rows.map((r) => {
          const on = cur.provider === r.provider && cur.model === r.model;
          return (
            <button key={r.provider + r.model} className={`mp-row ${on ? "on" : ""}`} onClick={() => pin(kind, r)} title={[r.model, r.strength, r.consider ? `Consider it: ${r.consider}` : "", r.watch ? `Keep in mind: ${r.watch}` : ""].filter(Boolean).join(" — ")}>
              <span className="mp-name">{r.label} <span className="dim">· {r.provider}</span></span>
              <span className="mp-price">{kind === "video" ? listPrice(r.price_usd) : r.price_usd != null ? `$${r.price_usd.toFixed(r.price_usd < 0.1 ? 3 : 2)}` : "price after first render"}</span>
              <span className={`mp-tag ${r.verified ? "ok" : ""}`}>{r.verified ? "proven" : "untested"}</span>
            </button>);
        })}</div>
      </div>);
  };
  return (
    <>
      <div className="perf-head">
        <h3 className="perf-h">Models <span className="dim">price per 5-second shot or still · click one to use it in this project</span></h3>
        <button className="btn ghost small" onClick={() => window.dispatchEvent(new Event("pf-open-keyframe-tools"))} title="Check hands in every keyframe, or redo keyframes on one picture model">Keyframe tools…</button>
      </div>
      {route.consistency?.mixed && !route.consistency.pinned && <div className="mc-advice" role="status">
        <b>Your keyframes come from {route.consistency.image_models.length} picture models</b>
        <span className="dim"> ({route.consistency.image_models.map((x) => `${x.label} ×${x.count}`).join(", ")})</span>
        <p>Mixing models can make a character look different from shot to shot.</p>
        <button className="btn small" onClick={() => window.dispatchEvent(new Event("pf-open-keyframe-tools"))}>Keep one model…</button>
      </div>}
      <div className="mp-grid">{section("video", m.video)}{section("image", m.image)}</div>
      {err && <div className="error-text">{err}</div>}
    </>
  );
}
