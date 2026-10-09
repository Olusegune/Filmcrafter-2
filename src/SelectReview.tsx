import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText, fmtTime, type BoardShot, type Estimate, type Job, type Section } from "./api";
import * as I from "./icons";
import { FramesPanel } from "./Frames";
import { ask } from "./ask";

/** Select → keyframes → review → video: pay for video only where the still is already right.
 *  Nothing is deleted: rejected stills are only hidden from automatic picks, and earlier takes stay in each shot's versions. */
type Option = { job: string; image: string; model: string; provider: string; created: number; rejected: boolean; check: boolean | null };
type Options = Record<string, { chosen: string | null; options: Option[]; active: number; failed: number }>;
type Route = { provider: string | null; model?: string; label?: string; free?: boolean; reason?: string };
type Step = "select" | "review" | "video";

const media = (dir: string, rel: string) => api.mediaUrl(`${dir}/${rel}`);
export const money = (e: Estimate | null, provider?: string | null) => !e ? "…" : provider === "comfyui" ? "free"
  : provider === "kie" && e.kie_credits_est != null ? `≈ ${Math.round(e.kie_credits_est)} Kie credits`
  : e.usd != null ? `≈ $${e.usd.toFixed(2)}` : e.usd_known > 0 ? `≈ $${e.usd_known.toFixed(2)} + ${e.unknown} unpriced`
  : "price not known in advance (billed by the provider)";

/** Song sections as the selection chips: neighbours with the same label merged, repeats numbered, empty ones left out. */
/** What the confirmation must say about end frames: which shots switch model, which can't use theirs. */
export const endNote = (e: Estimate | null) => {
  if (!e) return "";
  const sw = (e as Estimate & { end_frame_models?: { shot: string; title: string }[] }).end_frame_models ?? [];
  const no = (e as Estimate & { end_frame_unsupported?: string[] }).end_frame_unsupported ?? [];
  return (sw.length ? `

Shots with an end frame render on the start + end version: ${sw.map((s) => `${s.shot} → ${s.title}`).join(", ")}.` : "")
    + (no.length ? `

This model can't use an end frame, so it won't be sent for: ${no.join(", ")}.` : "");
};

export function sectionGroups(sections: Section[], shots: { start: number; end: number }[]) {
  const merged: { label: string; start: number; end: number }[] = [];
  for (const s of sections) {
    const last = merged[merged.length - 1];
    if (last && last.label === s.label) last.end = s.end; else merged.push({ label: s.label, start: s.start, end: s.end });
  }
  const total: Record<string, number> = {}, seen: Record<string, number> = {};
  merged.forEach((g) => { total[g.label] = (total[g.label] ?? 0) + 1; });
  const nice = (l: string) => l.charAt(0) + l.slice(1).toLowerCase();
  return merged.map((g) => ({ ...g, label: nice(g.label) + (total[g.label] > 1 ? ` ${(seen[g.label] = (seen[g.label] ?? 0) + 1)}` : "") }))
    .filter((g) => shots.some((x) => x.start < g.end - 0.01 && x.end > g.start + 0.01));
}

export function SelectReview({ dir, shots, sections, initial, onClose, onQueued }: {
  dir: string; shots: BoardShot[]; sections: Section[]; initial: string[]; onClose: () => void; onQueued: (jobs: Job[]) => void;
}) {
  const [step, setStep] = useState<Step>("select");
  const [sel, setSel] = useState<Set<string>>(new Set(initial));
  const [variants, setVariants] = useState(2);
  const [route, setRoute] = useState<{ image: Route; video: Route } | null>(null);
  const [est, setEst] = useState<Estimate | null>(null);
  const [opts, setOpts] = useState<Options>({});
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const ids = useMemo(() => shots.filter((s) => sel.has(s.id)).map((s) => s.id), [shots, sel]);
  const editable = (s: BoardShot) => !s.locked;

  useEffect(() => {
    Promise.all([api.routing<Route>(dir, "pick", { kind: "image" }), api.routing<Route>(dir, "pick", { kind: "video" })])
      .then(([image, video]) => setRoute({ image, video })).catch((e) => setErr(errorText(e)));
  }, [dir]);

  const refresh = useCallback(async () => {
    if (!ids.length) return;
    const o = await api.library<Options>(dir, "keyframe_options", { shots: ids });
    setOpts(o);
    const imgs = Object.values(o).flatMap((x) => x.options.map((p) => p.image));
    if (imgs.length) setThumbs(await api.thumbs(dir, imgs));
  }, [dir, ids]);
  useEffect(() => { if (step !== "select") refresh().catch(() => {}); }, [step]);   // eslint-disable-line react-hooks/exhaustive-deps
  const working = Object.values(opts).some((o) => o.active > 0);
  useEffect(() => {   // while stills are rendering, keep the grid current
    if (!working) return;
    const t = setInterval(() => refresh().catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [working, refresh]);

  const kind: "image" | "video" = step === "video" ? "video" : "image";
  const r = route?.[kind];
  const target = step === "video" ? ids.filter((id) => opts[id]?.chosen) : ids.filter((id) => !opts[id]?.chosen);   // what the next button renders
  const perShot = kind === "image" ? variants : 1;
  useEffect(() => {   // live price for what the next button will do
    setEst(null);
    if (!r?.provider || !target.length) return;
    let live = true;
    const t = setTimeout(() => api.renderEstimate(dir, target, r.provider!, r.model ?? null, kind)
      .then((e) => live && setEst(perShot > 1 ? { ...e, usd: e.usd == null ? null : e.usd * perShot, usd_known: e.usd_known * perShot,
        kie_credits_est: e.kie_credits_est == null ? undefined : e.kie_credits_est * perShot } : e)).catch(() => {}), 250);
    return () => { live = false; clearTimeout(t); };
  }, [dir, r?.provider, r?.model, kind, target.join(","), perShot]);   // eslint-disable-line react-hooks/exhaustive-deps

  const queue = async (shotIds: string[], k: "image" | "video", n: number, fix: string[] = []) => {
    const rr = route?.[k];
    if (!rr?.provider) { setErr(rr?.reason ?? "No renderer is set up for this. Settings → Keys, or ComfyUI."); return false; }
    setBusy(k); setErr("");
    try {
      const jobs = await api.queueRender(dir, shotIds, rr.provider, rr.model ?? null, n > 1 ? { _variants: n } : {}, fix, k);
      await api.ensureRenderer(dir);
      onQueued(jobs);
      if (!jobs.length) setErr("Nothing was queued: those shots are locked, undescribed, or already rendering.");
      await refresh();
      return jobs.length > 0;
    } catch (e) { setErr(errorText(e)); return false; } finally { setBusy(""); }
  };
  const act = async (f: () => Promise<unknown>) => { setErr(""); try { await f(); await refresh(); } catch (e) { setErr(errorText(e)); } };

  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const groups = useMemo(() => sectionGroups(sections, shots), [sections, shots]);
  const pickSection = (sec: { start: number; end: number }) => setSel((s) => {
    const inside = shots.filter((x) => editable(x) && x.start < sec.end - 0.01 && x.end > sec.start + 0.01).map((x) => x.id);
    const all = inside.every((id) => s.has(id));
    const n = new Set(s); inside.forEach((id) => (all ? n.delete(id) : n.add(id))); return n;
  });
  const needKf = ids.filter((id) => !opts[id]?.chosen);
  const chosenN = ids.filter((id) => opts[id]?.chosen).length;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass sr-sheet" role="dialog" aria-label="Select and review" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head">
          <h2>Select &amp; review</h2>
          <ol className="sr-steps" aria-label="Steps">
            {(["select", "review", "video"] as Step[]).map((s, i) => (
              <li key={s}><button className={step === s ? "on" : ""} disabled={s !== "select" && !ids.length} onClick={() => setStep(s)}>
                <span className="num">{i + 1}</span> {s === "select" ? "Select shots" : s === "review" ? "Keyframes" : "Video"}</button></li>))}
          </ol>
          <div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button>
        </div>

        {step === "select" && <>
          <p className="sub">Pick only the shots you want to work on. Stills come first and cost a few cents; video is only made for the keyframes you approve.</p>
          {groups.length > 0 && <div className="sr-sections">
            {groups.map((s, i) => <button key={i} className="chip" onClick={() => pickSection(s)}>{s.label}</button>)}
            <button className="link" onClick={() => setSel(new Set(shots.filter(editable).map((s) => s.id)))}>All</button>
            <button className="link" onClick={() => setSel(new Set())}>None</button>
          </div>}
          <div className="sr-grid">
            {shots.map((s) => (
              <button key={s.id} className={`sr-cell ${sel.has(s.id) ? "on" : ""}`} disabled={s.locked} aria-pressed={sel.has(s.id)}
                      title={s.locked ? "Locked" : s.beat} onClick={() => toggle(s.id)}>
                <span className="sr-img" style={{ backgroundImage: s.keyframe ? `url("${media(dir, s.keyframe)}")` : undefined }} />
                <span className="sr-meta"><b className="num">{s.id}</b><span className="dim num">{fmtTime(s.start)}</span>
                  {sel.has(s.id) && <I.Check size={12} />}</span>
              </button>))}
          </div>
          <div className="sheet-actions">
            <span className="dim">{ids.length} selected</span>
            <button className="btn primary" disabled={!ids.length} onClick={() => setStep("review")}>Next: keyframes</button>
          </div>
        </>}

        {step === "review" && <>
          <p className="sub">Click the still you want for each shot; it becomes the first frame of its video. Re-roll one shot with a note, or reject a still.
            Every still is kept.</p>
          <div className="sr-rows">
            {ids.map((id) => {
              const o = opts[id];
              return (
                <div key={id} className="sr-row">
                  <div className="sr-row-head"><b className="num">{id}</b>
                    {o?.chosen ? <span className="chip ready"><I.Check size={10} /> keyframe chosen</span> : <span className="chip planned">choose one</span>}
                    {o?.active ? <span className="chip gen"><span className="spin sm" /> {o.active} rendering</span> : null}
                    {o?.failed ? <span className="dim">{o.failed} failed</span> : null}
                    <div style={{ flex: 1 }} />
                    <input className="sr-note" placeholder="Note for a re-roll, e.g. closer, warmer light" value={note[id] ?? ""}
                           onChange={(e) => setNote((n) => ({ ...n, [id]: e.target.value }))} aria-label={`Note for ${id}`} />
                    <button className="btn ghost sm" disabled={!!busy} onClick={() => queue([id], "image", 1, note[id]?.trim() ? [note[id].trim()] : [])}>Re-roll</button>
                  </div>
                  <details className="sr-endframe">
                    <summary>Start &amp; end frames</summary>
                    <FramesPanel dir={dir} shot={id} compact onQueued={onQueued} />
                  </details>
                  <div className="sr-options">
                    {(o?.options ?? []).map((p) => (
                      <div key={p.job} className={`sr-opt ${o.chosen === p.image ? "on" : ""} ${p.rejected ? "off" : ""}`}>
                        <button className="sr-opt-img" style={{ backgroundImage: thumbs[p.image] ? `url("${media(dir, thumbs[p.image]!)}")` : undefined }}
                                onClick={() => act(() => api.library(dir, "choose_keyframe", { shot: id, job: p.job }))}
                                aria-label={`Use this still for ${id}`} title={p.model} />
                        <button className="sr-x" title={p.rejected ? "Restore" : "Reject"} aria-label={p.rejected ? "Restore" : "Reject"}
                                onClick={() => act(() => api.library(dir, "reject_keyframe", { job: p.job, on: !p.rejected }))}>{p.rejected ? "↺" : "×"}</button>
                        {o.chosen === p.image && <span className="sr-badge"><I.Check size={11} /></span>}
                      </div>))}
                    {!o?.options.length && !o?.active && <span className="dim">No stills yet.</span>}
                  </div>
                </div>);
            })}
          </div>
          <div className="sheet-actions sr-foot">
            {ids.length > 1 && <button className="btn ghost sm" disabled={!!busy} title="Each selected shot ends exactly on the next shot's start frame: they play as one continuous move"
              onClick={async () => { setErr(""); try { const r = await api.frames<{ chained: string[]; skipped: { shot: string; reason: string }[] }>(dir, "chain", { shots: ids });
                setErr(r.skipped.length ? `Flowing ${r.chained.length} shots together. Not changed: ${r.skipped.map((s) => `${s.shot} (${s.reason})`).join("; ")}` : ""); await refresh(); }
                catch (e) { setErr(errorText(e)); } }}>Flow selected shots together</button>}
            <label className="dim">Options per shot <select value={variants} onChange={(e) => setVariants(Number(e.target.value))}>
              {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
            <span className="dim">{r?.label ?? r?.model ?? "…"} · {money(est, r?.provider)}</span>
            <div style={{ flex: 1 }} />
            <button className="btn" disabled={!!busy || !needKf.length || !r?.provider}
                    onClick={async () => await ask(`Make ${needKf.length * variants} stills (${variants} per shot) on ${r?.label ?? r?.model}.

Cost: ${money(est, r?.provider)}. Start?`) && queue(needKf, "image", variants)}>
              {busy === "image" ? "Queuing…" : `Make stills for ${needKf.length} shot${needKf.length === 1 ? "" : "s"}`}</button>
            <button className="btn primary" disabled={!chosenN} onClick={() => setStep("video")}>Next: video ({chosenN})</button>
          </div>
        </>}

        {step === "video" && <>
          <p className="sub">Video is made only for the {chosenN} shot{chosenN === 1 ? "" : "s"} with a chosen keyframe. Takes you already have are kept;
            compare them in each shot's viewer and choose the one that goes in the video.</p>
          <div className="sr-grid">
            {ids.filter((id) => opts[id]?.chosen).map((id) => (
              <div key={id} className="sr-cell on static">
                <span className="sr-img" style={{ backgroundImage: `url("${media(dir, opts[id].chosen!)}")` }} />
                <span className="sr-meta"><b className="num">{id}</b></span>
              </div>))}
          </div>
          {ids.length > chosenN && <p className="dim">{ids.length - chosenN} selected shot(s) have no keyframe yet and are left out.</p>}
          <div className="sheet-actions">
            <span className="dim">{r?.label ?? r?.model ?? "…"} · {money(est, r?.provider)}</span>
            <div style={{ flex: 1 }} />
            <button className="btn ghost" onClick={() => setStep("review")}>Back</button>
            <button className="btn primary" disabled={!!busy || !chosenN || !r?.provider}
                    onClick={async () => await ask(`Render ${chosenN} video${chosenN === 1 ? "" : "s"} on ${r?.label ?? r?.model}.${endNote(est)}

Cost: ${money(est, r?.provider)}${r?.provider === "comfyui" ? " (runs on your computer)" : ""}. Start?`)
                      && queue(target, "video", 1).then((ok) => ok && onClose())}>
              {busy === "video" ? "Queuing…" : `Render ${chosenN} video${chosenN === 1 ? "" : "s"}`}</button>
          </div>
        </>}
        {!route?.[kind]?.provider && route && <p className="error-text">{route[kind].reason ?? "No renderer is set up."}</p>}
        {err && <div className="error-text" role="alert">{err}</div>}
      </div>
    </div>
  );
}
