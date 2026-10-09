import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "./api";
import { ask } from "./ask";
import * as I from "./icons";
import { HandFix } from "./HandFix";

export type Flagged = { shot: string; image: string; state: "fail" | "look"; locked: boolean; detail: string };
export type CheckPlan = { flagged: Flagged[]; shots: string[]; already: string[]; skipped: { shot: string; reason: string }[]; usd_est: number; can_check: boolean; unavailable: string };
export type CheckSummary = { checked: number; passed: number; failed: { shot: string; kinds: string[]; detail: string }[]; look: { shot: string; detail: string }[]; errors: { shot: string; error: string }[] };
export type RemakePlan = { shots: string[]; skipped: { shot: string; reason: string }[]; usd_est: number };
export type RemodelPlan = { target: { provider: string; model: string; label: string; price_usd: number | null }; shots: string[]; from: { shot: string; from: string }[]; skipped: { shot: string; reason: string }[];
  used: { provider: string; model: string; count: number }[]; usd_est: number };
export type SwapStatus = { making: number; ready: number; failed: number; shots_ready: string[]; reasons: Record<string, { making: number; ready: number; failed: number }> };

const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
/** Pure: a price in dollars for the screen. */
export const dollars = (n: number): string => (n <= 0 ? "free" : n < 0.1 ? `about $${n.toFixed(3)}` : `about $${n.toFixed(2)}`);

/** Pure: what the hands check found, in a sentence. */
export function checkSentence(s: CheckSummary): string {
  if (!s.checked && !s.errors.length) return "Nothing needed checking.";
  const bits = [`Looked at ${plural(s.checked, "keyframe")}.`];
  if (s.failed.length) bits.push(`${plural(s.failed.length, "has", "have")} hands or limbs that look wrong (${s.failed.map((f) => f.shot).join(", ")}).`);
  if (s.look.length) bits.push(`${plural(s.look.length, "is", "are")} worth a look (${s.look.map((f) => f.shot).join(", ")}).`);
  if (!s.failed.length && !s.look.length && s.checked) bits.push("No problems found.");
  if (s.errors.length) bits.push(`${plural(s.errors.length, "picture")} could not be checked.`);
  return bits.join(" ");
}

/** Pure: where the new keyframes are, in a sentence. Empty when there are none. */
export function swapSentence(s: SwapStatus | null): string {
  if (!s || (!s.making && !s.ready && !s.failed)) return "";
  return [s.making ? `${plural(s.making, "new keyframe is", "new keyframes are")} being made.` : "", s.ready ? `${plural(s.ready, "new keyframe is", "new keyframes are")} ready to use.` : "",
    s.failed ? `${plural(s.failed, "did", "did")} not come out (failed or failed the check).` : ""].filter(Boolean).join(" ");
}

/** Pure: how the model choice for redoing is described. */
export function remodelLine(p: RemodelPlan): string {
  if (!p.shots.length) return `Every keyframe that can be redone is already on ${p.target.label}.`;
  return `${plural(p.shots.length, "keyframe")} ${p.shots.length === 1 ? "was" : "were"} made by a different model. Redo ${p.shots.length === 1 ? "it" : "them"} on ${p.target.label}: ${dollars(p.usd_est)}.`;
}

/**
 * Keyframe tools: look at every keyframe's hands before any video is made, redo the ones that failed, and redo the keyframes that came from a different picture model so the whole cast is
 * drawn the same way. New pictures wait beside the old ones; nothing is replaced until you press Use the new keyframes, and that can be undone.
 */
export function KeyframeTools({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged?: () => void }) {
  const [check, setCheck] = useState<CheckPlan | null>(null);
  const [summary, setSummary] = useState<CheckSummary | null>(null);
  const [remake, setRemake] = useState<RemakePlan | null>(null);
  const [remodel, setRemodel] = useState<RemodelPlan | null>(null);
  const [remodelErr, setRemodelErr] = useState("");
  const [swap, setSwap] = useState<SwapStatus | null>(null);
  const [target, setTarget] = useState<string>("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [fixing, setFixing] = useState<Flagged | null>(null);

  const loadPlans = useCallback(async (model?: string) => {
    api.keyframeSet<CheckPlan>(dir, "check_plan").then(setCheck).catch((e) => setErr(errorText(e)));
    api.keyframeSet<RemakePlan>(dir, "remake_plan").then(setRemake).catch(() => setRemake(null));
    const [provider, name] = (model ?? "").split("|");
    api.keyframeSet<RemodelPlan>(dir, "remodel_plan", provider && name ? { provider, model: name } : {})
      .then((p) => { setRemodel(p); setRemodelErr(""); if (!model) setTarget(`${p.target.provider}|${p.target.model}`); })
      .catch((e) => { setRemodel(null); setRemodelErr(errorText(e)); });
  }, [dir]);
  const loadSwap = useCallback(() => api.keyframeSet<SwapStatus>(dir, "swap_status").then(setSwap).catch(() => {}), [dir]);
  useEffect(() => { loadPlans(); loadSwap(); }, [loadPlans, loadSwap]);
  useEffect(() => {                                              // new keyframes being made: look again every few seconds
    if (!swap?.making) return;
    const t = setInterval(loadSwap, 4000);
    return () => clearInterval(t);
  }, [swap?.making, loadSwap]);

  const run = async (what: string, fn: () => Promise<void>) => { setBusy(what); setErr(""); setNote(""); try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };

  const runCheck = (again: boolean) => run("check", async () => {
    if (!check) return;
    if (!(await ask(`Look at the hands and bodies in ${plural(again ? check.shots.length + check.already.length : check.shots.length, "keyframe")}.\n\nCost: ${dollars(again ? (check.shots.length + check.already.length) * 0.02 : check.usd_est)} (a few cents a picture, with your AI brain's vision model). Nothing is changed.\n\nStart?`))) return;
    setSummary(await api.keyframeSet<CheckSummary>(dir, "check_run", { again }));
    onChanged?.(); await loadPlans(target);
  });
  const runRemake = () => run("remake", async () => {
    if (!remake?.shots.length) return;
    if (!(await ask(`Make new keyframes for ${plural(remake.shots.length, "shot")} that failed (${remake.shots.join(", ")}), on the model that made them, with the correction.\n\nCost: ${dollars(remake.usd_est)}. The old keyframes stay until you choose to use the new ones.\n\nStart?`))) return;
    const r = await api.keyframeSet<{ queued: number }>(dir, "remake_run", {});
    setNote(`Making ${plural(r.queued, "new keyframe")}.`); await loadSwap();
  });
  const runRemodel = () => run("remodel", async () => {
    if (!remodel?.shots.length) return;
    if (!(await ask(`Make ${plural(remodel.shots.length, "new keyframe")} on ${remodel.target.label} (${remodel.shots.join(", ")}).\n\nCost: ${dollars(remodel.usd_est)}. ${remodel.target.label} is also chosen for the rest of this project, so new keyframes match. The old keyframes stay until you choose to use the new ones, and videos already made from them are not changed.\n\nStart?`))) return;
    const r = await api.keyframeSet<{ queued: number }>(dir, "remodel_run", { provider: remodel.target.provider, model: remodel.target.model });
    setNote(`Making ${plural(r.queued, "new keyframe")} on ${remodel.target.label}.`); await loadSwap(); onChanged?.();
  });
  const apply = () => run("apply", async () => {
    if (!swap?.ready) return;
    const r = await api.keyframeSet<{ applied: string[]; skipped: { shot: string; reason: string }[] }>(dir, "swap_apply", {});
    setNote(`Now using the new keyframe for ${plural(r.applied.length, "shot")}${r.skipped.length ? `. Not changed: ${r.skipped.map((s) => `${s.shot} (${s.reason})`).join("; ")}` : ""}. Undo with Ctrl+Shift+U. Videos made from the old keyframes are unchanged: render them again if you want them to match.`);
    onChanged?.(); await loadSwap(); await loadPlans(target);
  });

  const flagged = check?.flagged ?? [];
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass kt-sheet" role="dialog" aria-label="Keyframe tools" onClick={(e) => e.stopPropagation()}>
        <div className="rv-head"><div><h2>Keyframe tools</h2><p className="sub">Check hands before any video is made, and keep one look across the cast.</p></div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>

        {swapSentence(swap) && <div className="kt-swap" role="status">
          <span>{swapSentence(swap)}</span>
          {swap!.ready > 0 && <button className="btn primary small" disabled={!!busy} onClick={apply}>Use {plural(swap!.ready, "new keyframe")}</button>}
        </div>}

        <section className="kt-sec">
          <h3>Check the hands</h3>
          <p className="kt-lead">Looks closely at every approved keyframe with people in it. It only looks; nothing changes.</p>
          {!check && <span className="dim"><span className="spin sm" /> Reading the keyframes…</span>}
          {check && !check.can_check && <p className="warn-text" role="alert">{check.unavailable}</p>}
          {check && check.can_check && <p className="kt-fact">{check.shots.length ? <><b>{plural(check.shots.length, "keyframe")}</b> to check · {dollars(check.usd_est)}</> : <b>Every keyframe with people in it has been checked.</b>}
            {check.already.length > 0 && <span className="dim"> · {check.already.length} already done</span>}</p>}
          <div className="kt-actions">
            <button className="btn primary" disabled={!!busy || !check?.can_check || !check?.shots.length} onClick={() => runCheck(false)}>{busy === "check" ? "Looking…" : `Check ${check?.shots.length ?? 0} keyframe${check?.shots.length === 1 ? "" : "s"}`}</button>
            {check && check.can_check && check.already.length > 0 && <button className="btn ghost small" disabled={!!busy} onClick={() => runCheck(true)}>Check them all again</button>}
          </div>
          {busy === "check" && <p className="dim" role="status"><span className="spin sm" /> Looking at the pictures. This takes a few seconds for each one.</p>}
          {summary && <p className="kt-lead" role="status">{checkSentence(summary)}</p>}
          {flagged.length > 0 && <div className="kt-flagged">
            <h4>Worth a look <span className="rv-count">{flagged.length}</span></h4>
            <ul>{flagged.map((f) => (
              <li key={f.shot} className={f.state}>
                <i aria-hidden="true" />
                <span><b className="num">{f.shot}</b> {f.detail || (f.state === "fail" ? "Hands or limbs look wrong." : "Worth a look.")}</span>
                <button className="btn small" disabled={!!busy || f.locked} title={f.locked ? "This shot is locked" : "Redraw only the hand, and leave the rest of the picture alone"} onClick={() => setFixing(f)}>Fix the hand…</button>
              </li>))}</ul>
            {remake && remake.shots.length > 0 && <div className="kt-actions"><button className="btn ghost small" disabled={!!busy} onClick={runRemake}>Or redo the whole picture for the {remake.shots.length} that failed ({dollars(remake.usd_est)})</button></div>}
          </div>}
        </section>

        <section className="kt-sec">
          <h3>Keep one picture model</h3>
          <p className="kt-lead">Mixing picture models can change how a character looks from shot to shot.</p>
          {remodelErr && <p className="dim">{remodelErr}</p>}
          {remodel && <>
            <p className="kt-fact">Made by <b>{remodel.used.map((u) => `${u.model.split("/").slice(-1)[0]} ×${u.count}`).join(", ") || "nothing yet"}</b></p>
            {remodel.used.length > 1 && <label className="kt-pick">Bring everything to <select value={target} onChange={(e) => { setTarget(e.target.value); loadPlans(e.target.value); }} aria-label="Picture model to bring everything to">
              {remodel.used.map((u) => <option key={u.provider + u.model} value={`${u.provider}|${u.model}`}>{u.model.split("/").slice(-1)[0]} ({u.provider})</option>)}</select></label>}
            <p className="kt-fact">{remodelLine(remodel)}</p>
            {remodel.skipped.length > 0 && <p className="dim">Left alone: {remodel.skipped.map((s) => `${s.shot} (${s.reason})`).join("; ")}</p>}
            <div className="kt-actions"><button className="btn" disabled={!!busy || !remodel.shots.length} onClick={runRemodel}>{busy === "remodel" ? "Starting…" : `Redo ${remodel.shots.length} on ${remodel.target.label}`}</button></div></>}
        </section>

        {note && <p className="status-ok" role="status">{note}</p>}
        {err && <p className="error-text" role="alert">{err}</p>}
        {fixing && <HandFix dir={dir} shot={fixing.shot} image={fixing.image} onClose={() => setFixing(null)} onQueued={() => { loadSwap(); setNote(`Fixing the hand in ${fixing.shot}. The new versions appear here when they are ready.`); }} />}
      </div>
    </div>
  );
}
