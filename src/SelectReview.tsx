import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, fmtTime, type BoardShot, type Estimate, type Job, type Section } from "./api";
import * as I from "./icons";
import { FramesPanel } from "./Frames";
import { ask } from "./ask";
import { aspectCss } from "./frame";

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

/** The shots grouped by scene, in order: [scene number, heading, its shots]. */
export function groupByScene(shots: BoardShot[]): [number, string, BoardShot[]][] {
  const out: [number, string, BoardShot[]][] = [];
  for (const s of shots) {
    const last = out[out.length - 1];
    if (last && last[0] === s.scene) last[2].push(s);
    else out.push([s.scene, s.heading ?? "", [s]]);
  }
  return out;
}

export type PreviewItem = { key: string; src: string | null; title: string; sub: string; detail?: string; on?: boolean; action?: { label: string; run: () => void; disabled?: boolean } };

/**
 * A big look at one picture, over the sheet: the picture as large as the window allows, what it is, and one action (select it, or use it). Arrow keys move between pictures, Escape closes only this,
 * and focus goes back to where it was.
 */
export function Preview({ items, index, onIndex, onClose }: { items: PreviewItem[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const it = items[index];
  const box = useRef<HTMLDivElement | null>(null);
  useEffect(() => { const back = document.activeElement as HTMLElement | null; box.current?.focus(); return () => back?.focus?.(); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); onClose(); }
      else if (e.key === "ArrowRight" && index < items.length - 1) { e.preventDefault(); e.stopImmediatePropagation(); onIndex(index + 1); }
      else if (e.key === "ArrowLeft" && index > 0) { e.preventDefault(); e.stopImmediatePropagation(); onIndex(index - 1); }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, [index, items.length, onClose, onIndex]);
  if (!it) return null;
  return (
    <div className="sr-pv" role="dialog" aria-modal="true" aria-label={`Larger view of ${it.title}`} tabIndex={-1} ref={box} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <button className="sr-pv-nav" disabled={index === 0} onClick={() => onIndex(index - 1)} aria-label="Previous picture"><I.ArrowLeft size={20} /></button>
      <figure className="sr-pv-fig">
        {it.src ? <img src={it.src} alt={`${it.title}: ${it.sub}`} /> : <div className="sr-pv-none">No picture yet</div>}
        <figcaption><b className="num">{it.title}</b><span>{it.sub}</span>{it.detail && <p>{it.detail}</p>}</figcaption>
      </figure>
      <button className="sr-pv-nav" disabled={index >= items.length - 1} onClick={() => onIndex(index + 1)} aria-label="Next picture"><I.ArrowRight size={20} /></button>
      <div className="sr-pv-bar">
        <span className="dim">{index + 1} of {items.length} · ← → to move · Esc to close</span>
        <div style={{ flex: 1 }} />
        {it.action && <button className={`btn sm ${it.on ? "" : "primary"}`} disabled={it.action.disabled} onClick={it.action.run}>{it.action.label}</button>}
        <button className="btn ghost sm" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

const SIZES = [["s", "Small"], ["m", "Medium"], ["l", "Large"]] as const;
type TileSize = (typeof SIZES)[number][0];
const SIZE_KEY = "fc-select-size";
const storedSize = (): TileSize => { try { const v = localStorage.getItem(SIZE_KEY); return v === "s" || v === "l" ? v : "m"; } catch { return "m"; } };

export function SelectReview({ dir, shots, sections, initial, aspect, onClose, onQueued }: {
  dir: string; shots: BoardShot[]; sections: Section[]; initial: string[]; aspect?: string; onClose: () => void; onQueued: (jobs: Job[]) => void;
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
  const [size, setSizeState] = useState<TileSize>(storedSize);
  const setSize = (v: TileSize) => { setSizeState(v); try { localStorage.setItem(SIZE_KEY, v); } catch { /* remembering the size is a convenience only */ } };
  const [pv, setPv] = useState<{ items: PreviewItem[]; i: number } | null>(null);          // the larger view, when open
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
  useEffect(() => {                                                                  // small pictures for the tiles of the select step (the larger view uses the full one)
    if (step !== "select") return;
    const srcs = shots.map((x) => x.keyframe ?? x.thumb_src).filter((x): x is string => !!x && thumbs[x] === undefined);
    if (srcs.length) api.thumbs(dir, srcs).then((t) => setThumbs((cur) => ({ ...cur, ...t }))).catch(() => {});
  }, [step, shots, dir]);   // eslint-disable-line react-hooks/exhaustive-deps
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
          <div className="sr-tools">
            <div className="sr-sections">
              {groups.map((g, i) => <button key={i} className="chip" onClick={() => pickSection(g)}>{g.label}</button>)}
              <button className="link" onClick={() => setSel(new Set(shots.filter(editable).map((x) => x.id)))}>All</button>
              <button className="link" onClick={() => setSel(new Set(shots.filter((x) => editable(x) && !x.keyframe).map((x) => x.id)))} title="Select only the shots that have no picture yet">Without a picture ({shots.filter((x) => editable(x) && !x.keyframe).length})</button>
              <button className="link" onClick={() => setSel(new Set())}>None</button>
            </div>
            <div className="mode-toggle sr-size" role="group" aria-label="Picture size">
              {SIZES.map(([k, label]) => <button key={k} className={size === k ? "on" : ""} aria-pressed={size === k} onClick={() => setSize(k)}>{label}</button>)}</div>
          </div>
          <div className="sr-scroll" data-size={size} style={{ ["--ar" as string]: aspectCss(aspect) }}>
            {groupByScene(shots).map(([scene, heading, list]) => {
              const free = list.filter(editable);
              const all = free.length > 0 && free.every((x) => sel.has(x.id));
              return (
                <section key={scene} className="sr-scene" aria-label={`Scene ${scene}`}>
                  <h3><span>Scene {scene}</span>{heading && <em>{heading}</em>}<span className="dim">{list.length} shot{list.length === 1 ? "" : "s"}</span>
                    {free.length > 0 && <button className="link" onClick={() => setSel((cur) => { const n = new Set(cur); free.forEach((x) => (all ? n.delete(x.id) : n.add(x.id))); return n; })}>{all ? "Clear scene" : "Select scene"}</button>}</h3>
                  <div className="sr2">
                    {list.map((x) => {
                      const on = sel.has(x.id);
                      const src = x.keyframe ?? x.thumb_src;
                      const small = src ? thumbs[src] : null;
                      const open = () => setPv({ items: shots.map((y) => ({ key: y.id, src: y.keyframe ? media(dir, y.keyframe) : null, title: y.id, sub: `${fmtTime(y.start)}${y.framing ? ` · ${y.framing}` : ""}`,
                        detail: [y.heading, y.beat].filter(Boolean).join(" · "), on: sel.has(y.id),
                        action: y.locked ? { label: "Locked", run: () => {}, disabled: true } : { label: sel.has(y.id) ? "Deselect this shot" : "Select this shot", run: () => toggle(y.id) } })), i: shots.findIndex((y) => y.id === x.id) });
                      return (
                        <div key={x.id} className={`sr2-cell ${on ? "on" : ""} ${x.locked ? "locked" : ""}`}>
                          <button className="sr2-pick" disabled={x.locked} aria-pressed={on}
                                  title={x.locked ? "Locked: it cannot be changed here" : `${x.beat || x.id}\nClick to ${on ? "deselect" : "select"} · Z to enlarge`}
                                  onClick={() => toggle(x.id)} onKeyDown={(e) => { if (e.key === "z" || e.key === "Z") { e.preventDefault(); open(); } }}>
                            <span className="sr2-img" style={{ backgroundImage: small ? `url("${media(dir, small)}")` : undefined }}>
                              {!src && <span className="sr2-none">No picture yet</span>}</span>
                            <span className="sr2-check" aria-hidden="true">{on && <I.Check size={13} />}</span>
                            {x.locked && <span className="sr2-lock"><I.Lock size={11} /> Locked</span>}
                            {!x.locked && x.keyframe_check === "fail" && <span className="sr2-flag fail" title="The keyframe's hands or body look wrong">check</span>}
                            <span className="sr2-meta"><b className="num">{x.id}</b><span className="num dim">{fmtTime(x.start)}</span>{x.framing && <span className="sr2-fr">{x.framing}</span>}</span>
                          </button>
                          <button className="sr2-zoom" onClick={open} aria-label={`Enlarge ${x.id}`} title="Enlarge (Z)"><I.Search size={14} /></button>
                        </div>);
                    })}
                  </div>
                </section>);
            })}
          </div>
          <div className="sheet-actions sr-foot2">
            <span className="dim sr-hint">Click a picture to select it. The magnifier, or Z, enlarges it.</span>
            <div style={{ flex: 1 }} />
            <span className="dim" aria-live="polite">{ids.length} selected</span>
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
                        <button className="sr-zoomo" aria-label={`Enlarge this still for ${id}`} title="Enlarge"
                                onClick={() => setPv({ items: (o?.options ?? []).map((q) => ({ key: q.job, src: media(dir, q.image), title: id, sub: q.model, detail: o.chosen === q.image ? "The keyframe chosen for this shot" : undefined,
                                  on: o.chosen === q.image, action: { label: o.chosen === q.image ? "Chosen" : "Use this still", disabled: o.chosen === q.image, run: () => { void act(() => api.library(dir, "choose_keyframe", { shot: id, job: q.job })); setPv(null); } } })),
                                  i: (o?.options ?? []).findIndex((q) => q.job === p.job) })}><I.Search size={12} /></button>
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
          <div className="sr-scroll" data-size={size} style={{ ["--ar" as string]: aspectCss(aspect) }}>
            <div className="sr2">
              {ids.filter((id) => opts[id]?.chosen).map((id) => (
                <div key={id} className="sr2-cell on static">
                  <span className="sr2-img" style={{ backgroundImage: `url("${media(dir, opts[id].chosen!)}")` }} />
                  <span className="sr2-meta"><b className="num">{id}</b><span className="dim">keyframe chosen</span></span>
                  <button className="sr2-zoom" aria-label={`Enlarge ${id}`} title="Enlarge"
                          onClick={() => { const list = ids.filter((q) => opts[q]?.chosen); setPv({ items: list.map((q) => ({ key: q, src: media(dir, opts[q].chosen!), title: q, sub: "the keyframe its video starts from" })), i: list.indexOf(id) }); }}><I.Search size={14} /></button>
                </div>))}
            </div>
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
        {pv && <Preview items={pv.items} index={pv.i} onIndex={(i) => setPv((c) => c && { ...c, i })} onClose={() => setPv(null)} />}
        {!route?.[kind]?.provider && route && <p className="error-text">{route[kind].reason ?? "No renderer is set up."}</p>}
        {err && <div className="error-text" role="alert">{err}</div>}
      </div>
    </div>
  );
}
