import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, type ExportResult, type InterchangeResult, type MakeShot, type MakeStatus } from "./api";
import { ask } from "./ask";
import { FilmStrip } from "./FilmStrip";
import { EXPORT_FORMATS, formatFor } from "./exportFormats";
import { VoiceoverSheet } from "./VoiceoverSheet";
import { VoiceChip } from "./VoiceChip";
import { useVoiceDrop } from "./VoiceDrop";
import type { VoiceStatus } from "./api";
import * as I from "./icons";

export type MakeTab = "storyboard" | "keyframe" | "video" | "deliver";
const TABS: { id: MakeTab; label: string; blurb: string }[] = [
  { id: "keyframe", label: "Pictures", blurb: "The picture each shot starts from. Make a few, choose one and lock it: it is where the video starts. Or use your own." },
  { id: "video", label: "Video", blurb: "Each shot brought to life from its locked picture. Compare takes and approve the one to use." },
  { id: "storyboard", label: "Panels (optional)", blurb: "A cheaper first pass: a quick picture of each shot's composition. Choose one and lock it, and the picture is then made from it. Skip this if you like." },
  { id: "deliver", label: "Export", blurb: "The soundtrack, then the finished film or a hand-off to an editor." },
];
const NOUN = { storyboard: "storyboard panel", keyframe: "keyframe", video: "video" } as const;
const PRESETS: [string, string][] = [...EXPORT_FORMATS.map((f): [string, string] => [f.id, `${f.label} ${f.sub.split(" · ")[0]}`]), ["preview", "Quick preview"]];

type HandCheck = { flagged: { shot: string; state: "fail" | "look"; detail: string }[]; shots: string[]; usd_est: number; can_check: boolean; unavailable: string };
type CheckRun = { checked: number; passed: number; failed: { shot: string; detail: string }[]; look: { shot: string; detail: string }[]; errors: { shot: string; error: string }[] };
type Pick = { provider?: string; model?: string; label?: string; price_usd?: number | null; reason?: string };

/**
 * Making the film: storyboard, hero keyframes, video, then sound and export. Every step that costs money shows the price first and waits for a yes.
 * Chosen and locked work is never replaced by a new generation.
 */
export function MakeFilm({ dir, tab, onTab, autoBreakdown }: { dir: string; tab: MakeTab; onTab: (t: MakeTab) => void; autoBreakdown?: boolean }) {
  const [st, setSt] = useState<MakeStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ExportResult | null>(null);
  const [preset, setPreset] = useState("youtube");
  const [voiceOpen, setVoiceOpen] = useState(false);
  const dropped = useVoiceDrop(dir, !voiceOpen);                                  // drop a recording on a card
  const [voices, setVoices] = useState<VoiceStatus | null>(null);                 // how many of the film's voices are your own recordings
  useEffect(() => { if (!voiceOpen) api.voice("status", dir).then(setVoices).catch(() => {}); }, [dir, voiceOpen, tab]);
  const aspect = st?.aspect_ratio;
  const [presetTouched, setPresetTouched] = useState(false);
  useEffect(() => { if (aspect && !presetTouched) setPreset(formatFor(aspect)); }, [aspect, presetTouched]);   // the film's own shape, until you choose another
  const [handoff, setHandoff] = useState<InterchangeResult | null>(null);
  const [picked, setPicked] = useState<string | null>(null);                 // the shot chosen on the strip: its card is brought into view

  const load = useCallback(() => api.make("status", dir).then(setSt).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        try { await api.make("sync", dir); }
        catch (e) {                                          // Simple mode: no shots yet means the director's first pass is made now, then the film is ready
          if (autoBreakdown && /no shots yet/i.test(errorText(e))) { await api.shots("breakdown", dir); await api.make("sync", dir); } else throw e;
        }
        if (live) void load();
      } catch (e) { if (live) setErr(errorText(e) + (/no shots yet/i.test(errorText(e)) ? " Open Shots (Pro mode) and break the story down." : "")); }
    })();
    return () => { live = false; };
  }, [dir, load, autoBreakdown]);
  useEffect(() => {                                                       // while pictures or video are being made, look again
    if (!st || st.active === 0) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [st, load]);
  useEffect(() => { const un = api.onRenderIdle(() => void load()); return () => { un.then((f) => f()); }; }, [load]);

  const rd = st?.render_dir ?? "";
  const [hc, setHc] = useState<HandCheck | null>(null);                      // what the hands, bodies and faces check found, and what is still unchecked
  const loadChecks = useCallback(() => { if (rd) api.keyframeSet<HandCheck>(rd, "check_plan").then(setHc).catch(() => setHc(null)); }, [rd]);
  const chosenN = st?.counts.keyframe ?? 0;
  useEffect(() => { if (tab === "keyframe" || tab === "video") loadChecks(); }, [tab, loadChecks, chosenN]);
  const flagFor = (id: string) => hc?.flagged.find((f) => f.shot === id);
  const checkHands = async () => {
    if (!hc) return;
    if (!hc.can_check) { setErr(hc.unavailable); return; }
    if (!hc.shots.length) { setNote("Every chosen picture has been checked already."); return; }
    if (!await ask(`Look at the hands, bodies and faces in ${hc.shots.length} chosen picture${hc.shots.length === 1 ? "" : "s"}?\n\nAbout $${hc.usd_est.toFixed(2)} (one AI look each). It only looks; nothing is changed or re-made.`, { ok: "Check" })) return;
    setBusy("check"); setErr(""); setNote("");
    try {
      const res = await api.keyframeSet<CheckRun>(rd, "check_run", { shots: hc.shots });
      const bits = [`${res.passed} fine`];
      if (res.failed.length) bits.push(`${res.failed.length} need a new picture (${res.failed.map((f) => f.shot).join(", ")})`);
      if (res.look.length) bits.push(`${res.look.length} worth a closer look (${res.look.map((f) => f.shot).join(", ")})`);
      setNote(`Checked ${res.checked}: ${bits.join("; ")}.`);
      if (res.errors.length) setErr(res.errors.map((e) => `${e.shot}: ${e.error}`).join(" "));
      loadChecks();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
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
      const bad = stage === "video" ? ids.filter((id) => flagFor(id)?.state === "fail") : [];
      const warn = bad.length ? `\n\nHeads up: the picture for ${bad.join(", ")} was flagged for hands, body or face. The video will inherit it. Consider a new picture first.` : "";
      if (!await ask(`Make ${what} with ${pick.label || pick.model}?${warn}\n\nPrice: ${price}.\nThis is billed by the provider and can't be undone. Nothing is made until you press Make.`, { ok: "Make" })) return;
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

  const doHandoff = async () => {
    setBusy("handoff"); setErr(""); setHandoff(null);
    try { const r = await api.interchange(dir); setHandoff(r); await revealItemInDir(r.dir).catch(() => {}); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  if (!st) return <div className="mk"><div className="film-load dim">{err || "Getting the film ready…"}</div></div>;
  const t = TABS.find((x) => x.id === tab)!;
  const stage = tab === "deliver" ? null : tab;

  return (
    <div className="mk">
      {voiceOpen && <VoiceoverSheet dir={dir} onClose={() => setVoiceOpen(false)} />}
      {dropped}
      <div className="mk-head">
        {tab !== "deliver" ? <div className="cw-tabs" role="tablist">{TABS.filter((x) => x.id !== "deliver").map((x) => <button key={x.id} role="tab" aria-selected={tab === x.id} className={tab === x.id ? "on" : ""} onClick={() => onTab(x.id)}>{x.label}
          <span className="dim"> {st.counts[x.id as "storyboard" | "keyframe" | "video"]}/{st.counts.shots}</span></button>)}</div> : <h2 className="mk-title">Export</h2>}
        <div style={{ flex: 1 }} />
        {st.active > 0 && <span className="mk-active" role="status">Making {st.active}…</span>}
      </div>
      {tab !== "deliver" && <FilmStrip dir={dir} rd={rd} shots={st.shots} selected={picked} onChanged={() => void load()}
                 onSelect={(id) => { setPicked(id); document.getElementById(`mk-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }} />}
      <p className="dim mk-blurb">{t.blurb}</p>
      {stage && <GoldenNotes stage={stage} shots={st.shots} voices={voices} onVoices={() => setVoiceOpen(true)} />}
      {note && <p className="cw-note" role="status">{note} <button className="link" onClick={() => setNote("")}>OK</button></p>}
      {err && <p className="error-text" role="alert">{err}</p>}

      {stage && <>
        <div className="mk-bar">
          <button className="btn primary" disabled={!!busy} onClick={() => generate(stage, st.shots.filter((s) => ready(s, stage) && (stage === "video" || !s[stage].locked) && !done(s, stage)).map((s) => s.id))}>
            Make all that are missing</button>
          {stage === "keyframe" && <button className="btn" disabled={!!busy || !hc || st.counts.keyframe === 0} onClick={checkHands}
            title="One AI look at each chosen picture for wrong hands, bodies and faces, before any video is made from it. About two cents each.">{busy === "check" ? "Checking…" : `Check hands & faces${hc?.shots.length ? ` (${hc.shots.length})` : ""}`}</button>}
          <span className="mk-sum num">{st.counts[stage]} of {st.counts.shots} done</span><span className="dim">Each one shows its price first. Locked and chosen work is never replaced.</span>
        </div>
        <div className="mk-grid">{st.shots.map((s) => <Card key={s.id} dir={dir} rd={rd} stage={stage} s={s} busy={!!busy}
          onMake={(n) => generate(stage, [s.id], n)} onBring={() => bring(s.id, stage)}
          onChoose={(job) => call("choose", () => api.make("choose", dir, { shot: s.id, stage, job }))}
          flag={flagFor(s.id)}
          onLock={async (on) => { const f = flagFor(s.id); if (on && stage === "keyframe" && f?.state === "fail" && !await ask(`The check found a problem in this picture: ${f.detail || "hands, body or face look wrong"}.\n\nLock it anyway?`, { ok: "Lock anyway" })) return; await call("lock", () => api.make("lock", dir, { shot: s.id, stage, on })); }} />)}</div></>}

      {tab === "deliver" && <div className="mk-deliver">
        <div className="mk-ready" role="status">
          <div><b className="num">{st.counts.video}</b><span>of {st.counts.shots} shots have a take</span></div>
          <div className="mk-meter" aria-hidden="true"><i style={{ width: `${st.counts.shots ? Math.round((100 * st.counts.video) / st.counts.shots) : 0}%` }} /></div>
          <span className={st.counts.video === st.counts.shots && st.counts.shots > 0 ? "mk-flag ok" : "mk-flag"}>{st.counts.video === st.counts.shots && st.counts.shots > 0 ? "Complete" : "Draft: missing shots show as pictures"}</span>
        </div>
        <div className="mk-panels">
          <section className="mk-panel"><span className="mk-n num">1</span><h3>Soundtrack</h3>
            <p className="mk-big">{st.soundtrack.kind === "file" ? <>Using <b>{st.soundtrack.name ?? st.soundtrack.file}</b></> : "Silence, the length of the film"}</p>
            <p className="dim">Music, a dialogue mix or an ADR track you made elsewhere. It is copied in untouched and laid under the film.</p>
            <p className="dim mk-voices">{voices ? (voices.people === 0 ? "Nobody speaks in this film yet." : `Your own voices: ${voices.recorded} of ${voices.people} recorded.`) : ""} <button className="link" onClick={() => setVoiceOpen(true)}>Voiceover…</button></p>
            <div className="film-actions"><button className="btn" disabled={!!busy} onClick={soundtrack}>Choose a soundtrack…</button>
              {st.soundtrack.kind === "file" && <button className="btn ghost" disabled={!!busy} onClick={() => call("sound", () => api.make("soundtrack", dir, { file: null }))}>Use silence</button>}</div></section>
          <section className="mk-panel"><span className="mk-n num">2</span><h3>Export the film</h3>
            <p className="mk-big">One video file</p>
            <p className="dim">Shots without a take appear as picture cards, so the film is marked as a draft until every shot has one.</p>
            <div className="film-actions"><select className="text-input" value={preset} onChange={(e) => { setPresetTouched(true); setPreset(e.target.value); }} aria-label="Format">{PRESETS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select>
              <button className="btn primary" disabled={!!busy || st.counts.video === 0} onClick={doExport}>{busy === "export" ? "Exporting…" : "Export the film"}</button></div>
            {st.counts.video === 0 && <p className="dim mk-gate">Make at least one video first.</p>}
            {result && <div className="mk-result"><b>{result.draft ? "Draft exported" : "Exported"}</b> · {result.width}×{result.height} · {result.duration.toFixed(1)}s<br />
              <span className="dim">{result.path}</span><br /><button className="link" onClick={() => revealItemInDir(result.path)}>Show in folder</button></div>}</section>
          <section className="mk-panel"><span className="mk-n num">3</span><h3>Hand off to an editor</h3>
            <p className="mk-big">Your film is never trapped here</p>
            <p className="dim">One folder: the cut as an EDL (Premiere Pro, Resolve, Avid), OpenTimelineIO and Final Cut Pro XML, a shot manifest, subtitles, and copies of the takes and soundtrack.</p>
            <div className="film-actions"><button className="btn" disabled={!!busy || st.counts.video === 0} onClick={doHandoff}>{busy === "handoff" ? "Writing…" : "Write the hand-off folder"}</button></div>
            {handoff && <div className="mk-result"><b>Written</b> · {handoff.placed} of {handoff.shots} shots placed{handoff.missing.length ? `; no take yet: ${handoff.missing.join(", ")}` : ""}<br /><span className="dim">{handoff.dir}</span></div>}</section>
        </div>
      </div>}
    </div>
  );
}

const done = (s: MakeShot, stage: "storyboard" | "keyframe" | "video") => stage === "video" ? !!s.video.takes.find((x) => x.ok) : !!s[stage].chosen || s[stage].options.some((o) => o.ok || ["queued", "submitting", "submitted"].includes(o.state));
/** Two nudges that keep the production in order: test one shot before making them all, and attach the voices before the video (the mouth follows a recording only if it is there when the video is made). */
export function goldenNotes(stage: "storyboard" | "keyframe" | "video", shots: MakeShot[], voices: VoiceStatus | null): { test: MakeShot | null; voices: boolean } {
  const made = shots.filter((s) => (stage === "video" ? s.video.takes.some((t) => t.ok) : s[stage].options.length > 0 || !!s[stage].chosen)).length;
  const ok = (s: MakeShot) => (stage === "video" ? !!s.keyframe.chosen : true);
  const talky = new Set((voices?.shots ?? []).filter((v) => v.people.some((p) => (p.lines ?? []).length > 0)).map((v) => v.id));
  const test = shots.length >= 4 && made === 0 ? shots.find((s) => ok(s) && talky.has(s.id)) ?? shots.find(ok) ?? null : null;
  return { test, voices: stage === "video" && !!voices && voices.people > 0 && voices.missing > 0 && shots.some((s) => talky.has(s.id)) };
}

function GoldenNotes({ stage, shots, voices, onVoices }: { stage: "storyboard" | "keyframe" | "video"; shots: MakeShot[]; voices: VoiceStatus | null; onVoices: () => void }) {
  const g = goldenNotes(stage, shots, voices);
  if (stage === "storyboard" || (!g.test && !g.voices)) return null;
  return (
    <div className="mk-golden">
      {g.voices && <p role="note"><I.Mic size={13} /> <b>{voices!.missing} of {voices!.people} voices have no recording yet.</b> Attach them before you make the video, so each mouth follows its voice. <button className="link" onClick={onVoices}>Voiceover…</button></p>}
      {g.test && <p role="note"><I.Clapper size={13} /> Before you make all {shots.length}, <b>test one shot</b>: {g.test.id}. If it looks right, make the rest. <button className="link" onClick={() => document.getElementById(`mk-${g.test!.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" })}>Show {g.test.id}</button></p>}
    </div>
  );
}

/** A stage is open for a shot once the one before it has a choice. */
const ready = (s: MakeShot, stage: "storyboard" | "keyframe" | "video") => stage === "video" ? !!s.keyframe.chosen : true;      // a video needs its picture; a picture needs nothing (panels are optional)

function Card({ dir, rd, stage, s, busy, flag, onMake, onBring, onChoose, onLock }: { dir: string; rd: string; stage: "storyboard" | "keyframe" | "video"; s: MakeShot; busy: boolean; flag?: { state: "fail" | "look"; detail: string };
  onMake: (variants: number) => void; onBring: () => void; onChoose: (job: string) => void; onLock: (on: boolean) => void }) {
  void dir;
  const url = (rel: string | null) => (rel ? api.mediaUrl(`${rd}/${rel}`) : "");
  const open_ = stage === "video" ? s.video.takes.some((t) => ["queued", "submitting", "submitted"].includes(t.state)) : s[stage].options.some((o) => ["queued", "submitting", "submitted"].includes(o.state));
  const gate = !ready(s, stage) ? "Choose a picture first." : "";
  const locked = stage !== "video" && s[stage].locked;
  const chosenVideo = s.video.takes.find((t) => t.approved && t.ok) ?? s.video.takes.find((t) => t.ok);
  const preview = stage === "video" ? chosenVideo?.video ?? null : s[stage].chosen;
  const options = stage === "video" ? [] : s[stage].options.filter((o) => o.ok);
  return (
    <article id={`mk-${s.id}`} data-shot-id={s.id} className={`mk-card ${locked ? "locked" : ""}`}>
      <div className="mk-pic">
        {preview ? (stage === "video" ? <video src={url(preview)} controls preload="metadata" /> : <img src={url(preview)} alt={`${s.id}`} />) : <span className="dim">{open_ ? "Making…" : "Nothing yet"}</span>}
        <span className="mk-id num">{s.id}</span>{flag && stage !== "storyboard" && <span className={`mk-check ${flag.state}`} title={flag.detail}>{flag.state === "fail" ? "hands or face?" : "look closely"}</span>}{open_ && <span className="mk-busy">making</span>}{locked && <span className="mk-lock">locked</span>}
      </div>
      <div className="mk-meta"><b>{s.title || s.id}</b><span className="dim">{s.framing || "—"} · {s.duration}s</span></div>
      <VoiceChip dir={dir} shotId={s.id} compact />
      {stage === "video" && s.video.takes.length > 1 && <div className="mk-opts">{s.video.takes.filter((t) => t.ok).map((t, i) => (
        <button key={t.job} className={t.approved ? "on" : ""} onClick={() => onChoose(t.job)} title={`${t.model}${t.approved ? " (approved)" : ""}`}>Take {i + 1}{t.approved ? " ✓" : ""}</button>))}</div>}
      {options.length > 0 && <div className="mk-opts">{options.map((o) => (
        <button key={o.job} className={s[stage as "storyboard" | "keyframe"].chosen === o.image ? "on" : ""} disabled={locked} onClick={() => onChoose(o.job)} title={o.model}>
          <img src={url(o.image)} alt="option" /></button>))}</div>}
      {s[stage === "video" ? "keyframe" : stage].options.some((o) => o.state === "failed") && <p className="error-text mk-fail">One failed: {s[stage === "video" ? "keyframe" : stage].options.find((o) => o.state === "failed")?.error ?? "try again"}</p>}
      {flag && stage === "keyframe" && flag.detail && <p className={`mk-flagtext ${flag.state}`}>{flag.detail} <span className="dim">Make more, or fix the hand in the Timeline view.</span></p>}
      {gate && <p className="dim mk-gate">{gate}</p>}
      <div className="mk-actions">
        <button className="btn primary sm" disabled={busy || !!gate || locked || open_} onClick={() => onMake(2)}>{preview ? "Make more" : "Make"}</button>
        {stage !== "video" && <button className="btn ghost sm" disabled={busy || locked} onClick={onBring}>Use mine…</button>}
        {stage === "video" && <button className="btn ghost sm" disabled={busy} onClick={onBring}>Use my video…</button>}
        {stage !== "video" && (locked ? <button className="link" disabled={busy} onClick={() => onLock(false)}>Unlock</button>
          : <button className="link" disabled={busy || !s[stage].chosen} onClick={() => onLock(true)}>Lock</button>)}
      </div>
    </article>
  );
}
