import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, type ExportResult, type MakeShot, type MakeStatus } from "./api";
import { ask } from "./ask";

export type MakeTab = "storyboard" | "keyframe" | "video" | "deliver";
const TABS: { id: MakeTab; label: string; blurb: string }[] = [
  { id: "storyboard", label: "Storyboard", blurb: "A picture of each shot's framing. Choose one, then lock it: the composition is fixed from here on." },
  { id: "keyframe", label: "Keyframes", blurb: "The hero frame of each shot, made from the approved storyboard. Choose one, then lock it: it is where the video starts." },
  { id: "video", label: "Video", blurb: "Each shot brought to life from its locked keyframe. Compare takes and approve the one to use." },
  { id: "deliver", label: "Sound & export", blurb: "The soundtrack, then the finished film." },
];
const NOUN = { storyboard: "storyboard panel", keyframe: "keyframe", video: "video" } as const;
const PRESETS: [string, string][] = [["youtube", "YouTube 16:9"], ["cinema", "Cinema 2.39:1"], ["vertical", "Vertical 9:16"], ["square", "Square 1:1"], ["preview", "Quick preview"]];

type Pick = { provider?: string; model?: string; label?: string; price_usd?: number | null; reason?: string };

/**
 * Making the film: storyboard, hero keyframes, video, then sound and export. Every step that costs money shows the price first and waits for a yes.
 * Chosen and locked work is never replaced by a new generation.
 */
export function MakeFilm({ dir, tab, onTab }: { dir: string; tab: MakeTab; onTab: (t: MakeTab) => void }) {
  const [st, setSt] = useState<MakeStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ExportResult | null>(null);
  const [preset, setPreset] = useState("youtube");

  const load = useCallback(() => api.make("status", dir).then(setSt).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => {
    let live = true;
    api.make("sync", dir).then(() => { if (live) void load(); }).catch((e) => live && setErr(errorText(e)));
    return () => { live = false; };
  }, [dir, load]);
  useEffect(() => {                                                       // while pictures or video are being made, look again
    if (!st || st.active === 0) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [st, load]);
  useEffect(() => { const un = api.onRenderIdle(() => void load()); return () => { un.then((f) => f()); }; }, [load]);

  const rd = st?.render_dir ?? "";
  const call = async (what: string, fn: () => Promise<MakeStatus>) => { setBusy(what); setErr(""); try { setSt(await fn()); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };

  /** Ask which model, show the price, and queue only after a yes. */
  const generate = async (stage: "storyboard" | "keyframe" | "video", ids: string[], variants = 2) => {
    if (!st || !ids.length) return;
    setErr(""); setNote("");
    try {
      const kind = stage === "video" ? "video" : "image";
      const pick = await api.routing<Pick>(rd, "pick", { kind });
      if (!pick?.provider || !pick.model) { setErr(pick?.reason || "Choose a model first: open Settings, then Plan & budget."); return; }
      const n = stage === "video" ? 1 : variants;
      const est = await api.renderEstimate(rd, ids, pick.provider, pick.model, kind).catch(() => null);
      const each = est?.usd != null ? est.usd : null;
      const price = each != null ? `about $${(each * n).toFixed(2)}` : "a price isn't published for this model, so it can't be shown";
      const what = `${ids.length} ${NOUN[stage]}${ids.length === 1 ? "" : "s"}${stage === "video" ? "" : `, ${n} to choose from each`}`;
      if (!await ask(`Make ${what} with ${pick.label || pick.model}?\n\nPrice: ${price}.\nThis is billed by the provider and can't be undone. Nothing is made until you press Make.`, { ok: "Make" })) return;
      setBusy("make");
      const made = await api.queueRender(rd, ids, pick.provider, pick.model, stage === "video" ? {} : { _variants: n }, [], kind);
      if (stage !== "video") {
        await api.make("tag", dir, { jobs: made.map((j) => j.id), purpose: stage });
        if (stage === "keyframe") for (const id of ids) await api.make("reference", dir, { shot: id }).catch(() => {});
      }
      setNote(`Started ${made.length} ${made.length === 1 ? "job" : "jobs"}. They appear here as they finish.`);
      await load();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  const bring = async (shot: string, stage: MakeTab) => {
    const video = stage === "video";
    const f = await open({ multiple: false, filters: [{ name: video ? "Video" : "Picture", extensions: video ? ["mp4", "mov", "webm", "m4v"] : ["png", "jpg", "jpeg", "webp"] }] });
    if (typeof f === "string") await call("import", () => api.make("import", dir, { shot, stage, file: f }));
  };
  const soundtrack = async () => {
    const f = await open({ multiple: false, filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "aac", "ogg"] }] });
    if (typeof f === "string") await call("sound", () => api.make("soundtrack", dir, { file: f }));
  };
  const doExport = async () => {
    setBusy("export"); setErr(""); setResult(null);
    try { setResult(await api.exportProject(rd, preset)); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  if (!st) return <div className="mk"><div className="film-load dim">{err || "Getting the film ready…"}</div></div>;
  const t = TABS.find((x) => x.id === tab)!;
  const stage = tab === "deliver" ? null : tab;

  return (
    <div className="mk">
      <div className="mk-head">
        <div className="cw-tabs" role="tablist">{TABS.map((x) => <button key={x.id} role="tab" aria-selected={tab === x.id} className={tab === x.id ? "on" : ""} onClick={() => onTab(x.id)}>{x.label}
          {x.id !== "deliver" && <span className="dim"> {st.counts[x.id]}/{st.counts.shots}</span>}</button>)}</div>
        <div style={{ flex: 1 }} />
        {st.active > 0 && <span className="mk-active" role="status">Making {st.active}…</span>}
      </div>
      <p className="dim mk-blurb">{t.blurb}</p>
      {note && <p className="cw-note" role="status">{note} <button className="link" onClick={() => setNote("")}>OK</button></p>}
      {err && <p className="error-text" role="alert">{err}</p>}

      {stage && <>
        <div className="mk-bar">
          <button className="btn" disabled={!!busy} onClick={() => generate(stage, st.shots.filter((s) => ready(s, stage) && (stage === "video" || !s[stage].locked) && !done(s, stage)).map((s) => s.id))}>
            Make all that are missing</button>
          <span className="dim">Each one shows its price first. Locked and chosen work is never replaced.</span>
        </div>
        <div className="mk-grid">{st.shots.map((s) => <Card key={s.id} dir={dir} rd={rd} stage={stage} s={s} busy={!!busy}
          onMake={(n) => generate(stage, [s.id], n)} onBring={() => bring(s.id, stage)}
          onChoose={(job) => call("choose", () => api.make("choose", dir, { shot: s.id, stage, job }))}
          onLock={(on) => call("lock", () => api.make("lock", dir, { shot: s.id, stage, on }))} />)}</div></>}

      {tab === "deliver" && <div className="mk-deliver">
        <section><h3>Soundtrack</h3>
          <p>{st.soundtrack.kind === "file" ? <>Using <b>{st.soundtrack.name ?? st.soundtrack.file}</b>.</> : "Silence, the length of the film."}</p>
          <div className="film-actions"><button className="btn" disabled={!!busy} onClick={soundtrack}>Choose a soundtrack…</button>
            {st.soundtrack.kind === "file" && <button className="btn ghost" disabled={!!busy} onClick={() => call("sound", () => api.make("soundtrack", dir, { file: null }))}>Use silence</button>}</div>
          <p className="dim">Music, a dialogue mix or an ADR track you made elsewhere. It is copied in untouched and laid under the film.</p></section>
        <section><h3>Export</h3>
          <p className="dim">{st.counts.video} of {st.counts.shots} shots have a take. Shots without one appear as storyboard cards, so the film is marked as a draft.</p>
          <div className="film-actions"><select className="text-input" value={preset} onChange={(e) => setPreset(e.target.value)} aria-label="Format">{PRESETS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select>
            <button className="btn primary" disabled={!!busy || st.counts.video === 0} onClick={doExport}>{busy === "export" ? "Exporting…" : "Export the film"}</button></div>
          {result && <div className="mk-result"><b>{result.draft ? "Draft exported" : "Exported"}</b> · {result.width}×{result.height} · {result.duration.toFixed(1)}s<br />
            <span className="dim">{result.path}</span><br /><button className="link" onClick={() => revealItemInDir(result.path)}>Show in folder</button></div>}</section>
      </div>}
    </div>
  );
}

const done = (s: MakeShot, stage: "storyboard" | "keyframe" | "video") => stage === "video" ? !!s.video.takes.find((x) => x.ok) : !!s[stage].chosen || s[stage].options.some((o) => o.ok || ["queued", "submitting", "submitted"].includes(o.state));
/** A stage is open for a shot once the one before it has a choice. */
const ready = (s: MakeShot, stage: "storyboard" | "keyframe" | "video") => stage === "storyboard" ? true : stage === "keyframe" ? !!s.storyboard.chosen : !!s.keyframe.chosen;

function Card({ dir, rd, stage, s, busy, onMake, onBring, onChoose, onLock }: { dir: string; rd: string; stage: "storyboard" | "keyframe" | "video"; s: MakeShot; busy: boolean;
  onMake: (variants: number) => void; onBring: () => void; onChoose: (job: string) => void; onLock: (on: boolean) => void }) {
  void dir;
  const url = (rel: string | null) => (rel ? api.mediaUrl(`${rd}/${rel}`) : "");
  const open_ = stage === "video" ? s.video.takes.some((t) => ["queued", "submitting", "submitted"].includes(t.state)) : s[stage].options.some((o) => ["queued", "submitting", "submitted"].includes(o.state));
  const gate = !ready(s, stage) ? (stage === "keyframe" ? "Choose a storyboard panel first." : "Choose a keyframe first.") : "";
  const locked = stage !== "video" && s[stage].locked;
  const chosenVideo = s.video.takes.find((t) => t.approved && t.ok) ?? s.video.takes.find((t) => t.ok);
  const preview = stage === "video" ? chosenVideo?.video ?? null : s[stage].chosen;
  const options = stage === "video" ? [] : s[stage].options.filter((o) => o.ok);
  return (
    <article className={`mk-card ${locked ? "locked" : ""}`}>
      <div className="mk-pic">
        {preview ? (stage === "video" ? <video src={url(preview)} controls preload="metadata" /> : <img src={url(preview)} alt={`${s.id}`} />) : <span className="dim">{open_ ? "Making…" : "Nothing yet"}</span>}
        <span className="mk-id num">{s.id}</span>{locked && <span className="mk-lock">locked</span>}
      </div>
      <div className="mk-meta"><b>{s.title || s.id}</b><span className="dim">{s.framing || "—"} · {s.duration}s</span></div>
      {stage === "video" && s.video.takes.length > 1 && <div className="mk-opts">{s.video.takes.filter((t) => t.ok).map((t, i) => (
        <button key={t.job} className={t.approved ? "on" : ""} onClick={() => onChoose(t.job)} title={`${t.model}${t.approved ? " (approved)" : ""}`}>Take {i + 1}{t.approved ? " ✓" : ""}</button>))}</div>}
      {options.length > 0 && <div className="mk-opts">{options.map((o) => (
        <button key={o.job} className={s[stage as "storyboard" | "keyframe"].chosen === o.image ? "on" : ""} disabled={locked} onClick={() => onChoose(o.job)} title={o.model}>
          <img src={url(o.image)} alt="option" /></button>))}</div>}
      {s[stage === "video" ? "keyframe" : stage].options.some((o) => o.state === "failed") && <p className="error-text mk-fail">One failed: {s[stage === "video" ? "keyframe" : stage].options.find((o) => o.state === "failed")?.error ?? "try again"}</p>}
      {gate && <p className="dim mk-gate">{gate}</p>}
      <div className="mk-actions">
        <button className="btn sm" disabled={busy || !!gate || locked || open_} onClick={() => onMake(2)}>{preview ? "Make more" : "Make"}</button>
        {stage !== "video" && <button className="btn ghost sm" disabled={busy || locked} onClick={onBring}>Use mine…</button>}
        {stage === "video" && <button className="btn ghost sm" disabled={busy} onClick={onBring}>Use my video…</button>}
        {stage !== "video" && (locked ? <button className="link" disabled={busy} onClick={() => onLock(false)}>Unlock</button>
          : <button className="link" disabled={busy || !s[stage].chosen} onClick={() => onLock(true)}>Lock</button>)}
      </div>
    </article>
  );
}
