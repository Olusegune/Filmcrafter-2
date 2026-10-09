import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { api, errorText, type Estimate, type Job } from "./api";
import * as I from "./icons";
import { ask } from "./ask";
import { ConfirmRender } from "./Render";

/** Start and end frames for one shot. A model that takes both animates between them, so the filmmaker sets exactly
 *  where a shot starts and where it lands. Shown honestly: which model will use the end frame, or that it can't. */
export type ShotFrames = { start: string | null; start_mode: "keyframe" | "previous"; end: string | null; end_mode: EndMode;
  end_state: string; next: string | null; prev: string | null; next_has_start: boolean };
export type EndMode = "none" | "own" | "next";
type EndOption = { job: string; image: string; model: string; created: number; rejected: boolean };
type Support = { shots: Record<string, { model: string; swapped: boolean; supports_end: boolean | null; proven?: boolean; end: string | null }>; title: string };
type Route = { provider: string | null; model?: string; label?: string; reason?: string };

const media = (dir: string, rel: string) => api.mediaUrl(`${dir}/${rel.replace(/^project:/, "")}`);
const short = (m: string) => m.split("/").slice(-3).join("/");
const IMAGE = /\.(png|jpe?g|webp)$/i;

/** Ways a shot can end, in plain words: tap one to start the sentence. The transformations come first because they are what end frames make possible. */
export const END_IDEAS = [
  "the same pose, now decades older",
  "the face has changed completely: same person, a different age",
  "the character has turned to face the camera",
  "the camera has pushed in to a close-up of the face",
  "the room is empty; the light has changed",
  "the action has just finished and everything is still",
];

/** What the shot needs before it can render start → end, in the order the screen asks for it. Pure. */
export function framesStep(f: Pick<ShotFrames, "start" | "end" | "end_mode">): { step: "start" | "end" | "ready"; text: string } {
  if (!f.start) return { step: "start", text: "Give the shot a start frame: make a keyframe, bring your own image, or continue from the shot before." };
  if (f.end_mode === "none") return { step: "end", text: "Choose where the shot lands. Without an end frame the model decides." };
  if (!f.end) return { step: "end", text: f.end_mode === "next" ? "The next shot has no start frame yet, so there is nothing to flow into." : "Make or bring an end frame." };
  return { step: "ready", text: "Both ends are set. The model will animate from the start to the end." };
}

/** Everything a frames screen needs: the shot's frames, what the video model can do with them, and the actions. */
function useShotFrames(dir: string, shot: string, onChanged?: () => void, pick?: { provider: string; model: string; label: string } | null) {
  const [f, setF] = useState<ShotFrames | null>(null);
  const [opts, setOpts] = useState<{ chosen: string | null; options: EndOption[]; active: number } | null>(null);
  const [sup, setSup] = useState<Support["shots"][string] & { title?: string } | null>(null);
  const [video, setVideo] = useState<Route | null>(null);
  const [state, setState] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    const g = await api.frames<Record<string, ShotFrames>>(dir, "get", { shots: [shot] });
    setF(g[shot]); setState(g[shot].end_state);
    const o = await api.frames<Record<string, { chosen: string | null; options: EndOption[]; active: number }>>(dir, "options", { shots: [shot] });
    setOpts(o[shot]);
    const v: Route = pick ?? await api.routing<Route>(dir, "pick", { kind: "video" });
    setVideo(v);
    if (v.provider && v.model) {
      const s = await api.frames<Support>(dir, "support", { provider: v.provider, model: v.model, shots: [shot] });
      setSup({ ...s.shots[shot], title: s.title });
    }
  }, [dir, shot, pick?.provider, pick?.model]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setF(null); load().catch((e) => setErr(errorText(e))); }, [load]);
  useEffect(() => {   // end stills rendering: keep the options current
    if (!opts?.active) return;
    const t = setInterval(() => load().catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [opts?.active, load]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setErr("");
    try { await fn(); await load(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const setEnd = (mode: EndMode) => act("mode", () => api.frames(dir, "set", { shot, end_mode: mode }));
  const saveState = () => f && state !== f.end_state && act("state", () => api.frames(dir, "set", { shot, end_state: state }));
  const pickImage = async () => {
    const p = await open({ filters: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "webp"] }] });
    return typeof p === "string" ? p : null;
  };
  const bringEnd = async (path?: string | null) => { const p = path ?? await pickImage(); if (p) await act("image", () => api.frames(dir, "use_image", { shot, path: p })); };
  const bringStart = async (path?: string | null) => { const p = path ?? await pickImage(); if (p) await act("start-image", () => api.frames(dir, "use_start", { shot, path: p })); };
  const makeStills = async (n: number) => {
    const img = await api.routing<Route>(dir, "pick", { kind: "image" });
    if (!img.provider) { setErr(img.reason ?? "No image model is set up."); return; }
    if (state !== f?.end_state) await api.frames(dir, "set", { shot, end_state: state });
    let price = "";
    try {
      const e: Estimate = await api.renderEstimate(dir, [shot], img.provider, img.model ?? null, "image");
      price = img.provider === "comfyui" ? "free" : img.provider === "kie" && e.kie_credits_est != null ? `≈ ${Math.round(e.kie_credits_est * n)} Kie credits`
        : e.usd != null ? `≈ $${(e.usd * n).toFixed(2)}` : "price not known in advance";
    } catch { price = "price not known in advance"; }
    if (!await ask(`Make ${n} end-frame still${n === 1 ? "" : "s"} for ${shot} on ${img.label ?? img.model}.\n\nCost: ${price}. Start?`)) return;
    await act("stills", async () => {
      const jobs = await api.queueRender(dir, [shot], img.provider!, img.model ?? null, { _variants: n, _frame: "end" }, [], "image");
      await api.ensureRenderer(dir);
      return jobs;
    });
  };
  return { f, opts, sup, video, state, setState, busy, err, setErr, load, act, setEnd, saveState, bringEnd, bringStart, makeStills };
}

type ProofCheck = { ok: boolean; reason?: string; verdict?: "landed" | "missed" | "unclear"; start_diff?: number; end_diff?: number; provider?: string; model?: string; proven?: boolean; text?: string };
type ProofReport = { built_in: { provider: string; model: string }[]; yours: { provider: string; model: string; date?: string; end_diff?: number; start_diff?: number }[] };

/** Pure: the line under a check, and whether the model can be marked as proven from it. */
export function proofAdvice(c: Pick<ProofCheck, "ok" | "verdict" | "proven">): { canMark: boolean; text: string } {
  if (!c.ok) return { canMark: false, text: "" };
  if (c.verdict === "landed") return c.proven ? { canMark: false, text: "This model is already marked as proven." } : { canMark: true, text: "If you are happy with the take, mark this model as proven: shots on it will stop showing the “not yet proven” warning." };
  if (c.verdict === "missed") return { canMark: false, text: "Try the shot again or pick another model. A model that misses is not marked as proven." };
  return { canMark: false, text: "Use a start and end picture that look different from each other to test a model." };
}

/** Free check of a finished take: did its last frame land on the end picture? Lets you prove a model with a render you already paid for. */
function ProofBox({ dir, shot, onChanged }: { dir: string; shot: string; onChanged?: () => void }) {
  const [res, setRes] = useState<ProofCheck | null>(null);
  const [rep, setRep] = useState<ProofReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { setRes(null); setErr(""); }, [dir, shot]);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setErr(""); try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  const check = () => run(async () => setRes(await api.proof<ProofCheck>(dir, "check", { shot })));
  const mark = () => run(async () => { setRep(await api.proof<ProofReport>(dir, "record", { shot })); setRes(await api.proof<ProofCheck>(dir, "check", { shot })); onChanged?.(); });
  const forget = (p: string, m: string) => run(async () => { setRep(await api.proof<ProofReport>(dir, "forget", { provider: p, model: m })); });
  const loadList = () => run(async () => setRep(await api.proof<ProofReport>(dir, "report")));
  const adv = res ? proofAdvice(res) : null;
  return (
    <div className="fr-proof">
      <div className="fr-proof-bar">
        <button className="btn ghost small" disabled={busy} onClick={check} title="Measure how close the take's last frame is to your end picture. Free; nothing is sent anywhere.">Check where the take landed</button>
        <details onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && !rep) loadList(); }}><summary className="dim">Proven models</summary>
          {rep && <ul className="fr-proof-list">
            {rep.built_in.map((r) => <li key={`${r.provider}/${r.model}`}>{r.provider}: {short(r.model)} <span className="dim">proven in testing</span></li>)}
            {rep.yours.map((r) => <li key={`y${r.provider}/${r.model}`}>{r.provider}: {short(r.model)} <span className="dim">you proved it {r.date ?? ""}{r.end_diff != null ? ` (${r.end_diff} against ${r.start_diff})` : ""}</span>
              <button className="link" disabled={busy} onClick={() => forget(r.provider, r.model)} aria-label={`Forget ${short(r.model)}`}>Forget</button></li>)}
          </ul>}
        </details>
      </div>
      {res && (res.ok
        ? <p className={`fr-note ${res.verdict === "landed" ? "ok" : "warn"}`} role="status">{res.text} {adv?.text}
          {adv?.canMark && <> <button className="btn small" disabled={busy} onClick={mark}>Mark this model as proven</button></>}</p>
        : <p className="dim" role="status">{res.reason}</p>)}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

/** The honest line about what the video model will do with the end frame. */
function supportNote(f: ShotFrames, sup: ReturnType<typeof useShotFrames>["sup"], video: Route | null) {
  if (!f.end || !sup) return null;
  const untested = sup.supports_end && !sup.proven ? " Not yet proven on this model with a real render: check the result." : "";
  return sup.supports_end === false
    ? { cls: "warn", text: `${video?.label ?? sup.title} can't use an end frame, so it won't be sent. Pick a model that can (Wan, Kling, Veo, Seedance, Vidu, Hailuo, LTX) in the route chip.` }
    : sup.swapped ? { cls: untested ? "warn" : "ok", text: `This shot will render on ${short(sup.model)}, the start + end version of ${video?.label ?? sup.title}.${untested}` }
      : { cls: untested ? "warn" : "ok", text: `${video?.label ?? sup.title} will animate from the start frame to the end frame.${untested}` };
}

export function FramesPanel({ dir, shot, compact, onChanged, onQueued }: {
  dir: string; shot: string; compact?: boolean; onChanged?: () => void; onQueued?: (jobs: Job[]) => void;
}) {
  const { f, opts, sup, video, state, setState, busy, err, act, setEnd, saveState, bringEnd, makeStills } = useShotFrames(dir, shot, onChanged);
  void onQueued;
  if (!f) return <div className="fr-panel dim">{err || "Loading frames…"}</div>;
  const endImg = f.end;
  const note = supportNote(f, sup, video);

  return (
    <div className={`fr-panel ${compact ? "compact" : ""}`}>
      {!compact && <h4>Start &amp; end frames</h4>}
      <div className="fr-pair">
        <figure className="fr-frame">
          <div className="fr-img" style={{ backgroundImage: f.start ? `url("${media(dir, f.start)}")` : undefined }}>{!f.start && <span>No start frame yet</span>}</div>
          <figcaption>
            <b>Start</b>
            {f.prev && <select value={f.start_mode} disabled={!!busy} aria-label="Start frame"
                                onChange={(e) => act("start", () => api.frames(dir, "start", { shot, mode: e.target.value }))}>
              <option value="keyframe">Its keyframe</option>
              <option value="previous">Continue from {f.prev}'s last frame</option>
            </select>}
          </figcaption>
        </figure>
        <div className="fr-arrow" aria-hidden>→</div>
        <figure className="fr-frame">
          <div className={`fr-img ${f.end_mode === "none" ? "empty" : ""}`} style={{ backgroundImage: endImg ? `url("${media(dir, endImg)}")` : undefined }}>
            {!endImg && <span>{f.end_mode === "none" ? "No end frame: the model decides" : f.end_mode === "next" ? `${f.next} has no start frame yet` : "Choose or make an end frame"}</span>}
          </div>
          <figcaption>
            <b>End</b>
            <div className="fr-modes" role="radiogroup" aria-label="End frame">
              {(["none", "own", "next"] as EndMode[]).map((m) => (
                <button key={m} role="radio" aria-checked={f.end_mode === m} className={f.end_mode === m ? "on" : ""}
                        disabled={!!busy || (m === "next" && !f.next)} onClick={() => setEnd(m)}
                        title={m === "next" ? "End exactly on the next shot's start frame: the two shots flow together with no visible cut" : undefined}>
                  {m === "none" ? "None" : m === "own" ? "Its own" : f.next ? `Flow into ${f.next}` : "Flow into next"}</button>))}
            </div>
          </figcaption>
        </figure>
      </div>

      {f.end_mode === "own" && <div className="fr-own">
        <textarea className="text-input" rows={compact ? 1 : 2} value={state} onChange={(e) => setState(e.target.value)} onBlur={saveState}
                  placeholder="How the shot ends, e.g. she has turned to camera, hand on the door, the light now behind her" aria-label="How the shot ends" />
        <div className="fr-own-actions">
          <button className="btn sm" disabled={!!busy} onClick={() => makeStills(2)}>{busy === "stills" ? "Queuing…" : "Make 2 end stills"}</button>
          <button className="btn ghost sm" disabled={!!busy} onClick={() => bringEnd()}>Use an image…</button>
          {opts?.active ? <span className="dim"><span className="spin sm" /> {opts.active} rendering</span> : null}
        </div>
        <EndOptions dir={dir} shot={shot} opts={opts} act={act} />
      </div>}
      {note && <p className={`fr-note ${note.cls}`}>{note.text}</p>}
      {f.end && <ProofBox dir={dir} shot={shot} onChanged={onChanged} />}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

function EndOptions({ dir, shot, opts, act }: { dir: string; shot: string; opts: ReturnType<typeof useShotFrames>["opts"]; act: ReturnType<typeof useShotFrames>["act"] }) {
  if (!opts?.options.length) return null;
  return (
    <div className="sr-options">
      {opts.options.map((o) => (
        <div key={o.job} className={`sr-opt ${opts.chosen === o.image ? "on" : ""} ${o.rejected ? "off" : ""}`}>
          <button className="sr-opt-img" style={{ backgroundImage: `url("${media(dir, o.image)}")` }} aria-label={`Use this end frame for ${shot}`}
                  title={o.model} onClick={() => act("choose", () => api.frames(dir, "choose", { shot, job: o.job }))} />
          <button className="sr-x" title={o.rejected ? "Restore" : "Reject"} aria-label={o.rejected ? "Restore" : "Reject"}
                  onClick={() => act("reject", () => api.library(dir, "reject_keyframe", { job: o.job, on: !o.rejected }))}>{o.rejected ? "↺" : "×"}</button>
          {opts.chosen === o.image && <span className="sr-badge"><I.Check size={11} /></span>}
        </div>))}
    </div>
  );
}

/** The Frames tab: the shot's two ends as one big stage. Bring a picture from Midjourney or anywhere by dropping it on either side. */
export type ModelPick = { provider: string; model: string; label: string };
export function FramesStage({ dir, shot, hasKey, onChanged, onQueued, onOpenKeyframe, pick, overrides: take, children }: {
  dir: string; shot: string; hasKey: boolean; onChanged?: () => void; onQueued?: (jobs: Job[]) => void; onOpenKeyframe?: () => void;
  pick?: ModelPick | null; overrides?: Record<string, unknown>; children?: React.ReactNode;     // the model chosen in the Compose tab, and the prompt settings for this take
}) {
  const { f, opts, sup, video, state, setState, busy, err, setErr, act, setEnd, saveState, bringEnd, bringStart, makeStills } = useShotFrames(dir, shot, onChanged, pick);
  const startRef = useRef<HTMLDivElement>(null), endRef = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState<"start" | "end" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const live = useRef({ bringStart, bringEnd, f });
  live.current = { bringStart, bringEnd, f };

  useEffect(() => {   // dropping an image file on either side of the stage
    const hit = (x: number, y: number) => {
      const px = x / (window.devicePixelRatio || 1), py = y / (window.devicePixelRatio || 1);
      const inside = (el: HTMLElement | null) => { const r = el?.getBoundingClientRect(); return !!r && px >= r.left && px <= r.right && py >= r.top && py <= r.bottom; };
      return inside(startRef.current) ? "start" : inside(endRef.current) ? "end" : null;
    };
    let un: (() => void) | undefined, dead = false;
    getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "leave") { setOver(null); return; }
      const side = hit(p.position.x, p.position.y);
      if (p.type === "over") { setOver(side); return; }
      setOver(null);
      if (p.type !== "drop" || !side) return;
      const img = p.paths.find((x) => IMAGE.test(x));
      if (!img) { setErr("Drop a PNG, JPG or WebP picture."); return; }
      side === "start" ? live.current.bringStart(img) : live.current.bringEnd(img);
    }).then((u) => { if (dead) u(); else un = u; }).catch(() => {});
    return () => { dead = true; un?.(); };
  }, [shot]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!f) return <div className="fr-panel dim">{err || "Loading frames…"}</div>;
  const step = framesStep(f);
  const note = supportNote(f, sup, video);
  const using = pick ?? (video?.provider ? { provider: video.provider, model: video.model ?? "", label: video.label ?? video.model ?? "" } : null);
  const canRender = step.step === "ready" && hasKey && !!using && !busy;
  const render = async () => {
    setConfirm(false);
    try {
      const jobs = await api.queueRender(dir, [shot], using!.provider, using!.model || null, take ?? {}, []);
      await api.ensureRenderer(dir);
      onQueued?.(jobs);
    } catch (e) { setErr(errorText(e)); }
  };

  return (
    <div className="fr-stage">
      <div className="fr-stage-head">
        <span className="dim">Make the two ends here, or drop a picture from Midjourney, Photoshop or anywhere onto either side.</span>
      </div>
      <ol className="fr-steps" aria-label="Steps">
        {(["start", "end", "ready"] as const).map((s, i) => (
          <li key={s} className={step.step === s ? "now" : (["start", "end", "ready"].indexOf(step.step) > i ? "done" : "")}>
            <i>{["start", "end", "ready"].indexOf(step.step) > i ? <I.Check size={11} /> : i + 1}</i>{s === "start" ? "Start frame" : s === "end" ? "End frame" : "Render"}</li>))}
      </ol>
      <p className="fr-guide" role="status">{step.text}</p>

      <div className="fr-pair big">
        <figure className="fr-frame">
          <div ref={startRef} className={`fr-img ${over === "start" ? "drop" : ""} ${f.start ? "" : "empty"}`} style={{ backgroundImage: f.start ? `url("${media(dir, f.start)}")` : undefined }}>
            <em className="fr-tag">START</em>{!f.start && <span>Drop a picture here</span>}
          </div>
          <figcaption>
            <div className="fr-actions">
              <button className="btn sm" disabled={!!busy} onClick={() => onOpenKeyframe?.()}>{f.start ? "Remake the keyframe" : "Make a keyframe"}</button>
              <button className="btn ghost sm" disabled={!!busy} onClick={() => bringStart()}>Use my image…</button>
            </div>
            {f.prev && <select value={f.start_mode} disabled={!!busy} aria-label="Start frame"
                                onChange={(e) => act("start", () => api.frames(dir, "start", { shot, mode: e.target.value }))}>
              <option value="keyframe">Start on its keyframe</option>
              <option value="previous">Continue from {f.prev}'s last frame</option>
            </select>}
            {f.prev && f.start_mode === "previous" && <span className="dim fr-exact">Uses the exact last frame of {f.prev}'s take when the provider returns one (Kie's Seedance models do when asked, and PULSEFRAME asks automatically); otherwise it is read from the video.</span>}
          </figcaption>
        </figure>
        <div className="fr-arrow" aria-hidden>→</div>
        <figure className="fr-frame">
          <div ref={endRef} className={`fr-img ${over === "end" ? "drop" : ""} ${f.end ? "" : "empty"}`} style={{ backgroundImage: f.end ? `url("${media(dir, f.end)}")` : undefined }}>
            <em className="fr-tag">END</em>
            {!f.end && <span>{f.end_mode === "none" ? "No end frame: the model decides" : f.end_mode === "next" ? `${f.next} has no start frame yet` : "Drop a picture here"}</span>}
          </div>
          <figcaption>
            <div className="fr-modes" role="radiogroup" aria-label="End frame">
              {(["none", "own", "next"] as EndMode[]).map((m) => (
                <button key={m} role="radio" aria-checked={f.end_mode === m} className={f.end_mode === m ? "on" : ""}
                        disabled={!!busy || (m === "next" && !f.next)} onClick={() => setEnd(m)}
                        title={m === "next" ? "End exactly on the next shot's start frame: the two shots flow together with no visible cut" : m === "own" ? "Make or bring a picture of how this shot ends" : "The model decides how the shot ends"}>
                  {m === "none" ? "Let the model decide" : m === "own" ? "My own end frame" : f.next ? `Flow into ${f.next}` : "Flow into next"}</button>))}
            </div>
          </figcaption>
        </figure>
      </div>

      {f.end_mode === "own" && <div className="fr-own">
        <label className="fr-label" htmlFor={`end-${shot}`}>How does this shot end?</label>
        <textarea id={`end-${shot}`} className="text-input" rows={2} value={state} onChange={(e) => setState(e.target.value)} onBlur={saveState}
                  placeholder="e.g. the same man, now old, standing where the boy stood" />
        <details className="fr-ideas-more"><summary>Need an idea?</summary>
          <div className="fr-ideas" aria-label="Ideas">
            {END_IDEAS.map((t) => <button key={t} className="chip" onClick={() => { setState(t); act("state", () => api.frames(dir, "set", { shot, end_state: t })); }}>{t}</button>)}
          </div>
        </details>
        <div className="fr-own-actions">
          <button className="btn sm" disabled={!!busy} onClick={() => makeStills(2)}>{busy === "stills" ? "Queuing…" : "Make 2 end stills with AI"}</button>
          <button className="btn ghost sm" disabled={!!busy} onClick={() => bringEnd()}>Use my image…</button>
          {opts?.active ? <span className="dim"><span className="spin sm" /> {opts.active} rendering</span> : null}
        </div>
        <EndOptions dir={dir} shot={shot} opts={opts} act={act} />
      </div>}

      {note && <p className={`fr-note ${note.cls}`}>{note.text}</p>}
      {f.end && <ProofBox dir={dir} shot={shot} onChanged={onChanged} />}
      {err && <p className="error-text" role="alert">{err}</p>}
      {children}
      <div className="fr-cta">
        <button className="btn primary" disabled={!canRender} onClick={() => setConfirm(true)}
                title={step.step !== "ready" ? step.text : !hasKey ? "Add a provider key in Settings first" : undefined}>
          Render start → end</button>
        {step.step !== "ready" && <span className="dim">{step.step === "start" ? "Set the start frame first." : "Set the end frame to render both ends."}</span>}
      </div>
      {confirm && using && <ConfirmRender count={1} seconds={0} provider={using.provider} model={`${using.label}, animating from the start frame to the end frame`}
        onCancel={() => setConfirm(false)} onConfirm={render} dir={dir} shots={[shot]} modelId={using.model || null} />}
    </div>
  );
}
