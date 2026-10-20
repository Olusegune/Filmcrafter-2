import { useEffect, useMemo, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, fmtTime, type Job, type KeyStatus, type Shot } from "./api";
import { ConfirmRender, PROVIDER_NAME } from "./Render";
import * as I from "./icons";
import { QueueBanner, useQueue } from "./RenderQueue";
import { reviewHeadline, splitIssues, swapHeadline, upgradesFor, VERDICT_WORDS, inUseTake } from "./reviewSwap";

/** A ready take whose review found something and the user hasn't accepted it. */
export const needsAttention = (j?: Job) =>
  !!j && j.state === "ready" && !!j.review?.reviewed && !j.review.accepted &&
  (j.review.status === "needs_attention" || j.review.status === "minor");

const KIND: Record<string, string> = {
  character: "Character", wardrobe: "Wardrobe", environment: "Setting", look: "Look", action: "Action",
  artifact: "Artifact", anatomy: "Hands and body", text: "On-screen text", framing: "Framing", performance: "Acting", technical: "Technical",
};

/** Where a fix is rendered. "same" = the flagged take's own model. */
const FIX_TARGETS: { id: string; label: string; provider?: string; model?: string }[] = [
  { id: "same", label: "Same model as the take" },
  { id: "kie-kling3", label: "Kling 3.0 · Kie.ai", provider: "kie", model: "kling/kling-3-0" },
  { id: "kie-kling3-turbo", label: "Kling V3 Turbo · Kie.ai", provider: "kie", model: "kling/v3-turbo-image-to-video" },
  { id: "kie-seedance25", label: "Seedance 2.5 · Kie.ai", provider: "kie", model: "bytedance/seedance-2-5" },
  { id: "kie-wan", label: "Wan 3.0 · Kie.ai", provider: "kie", model: "wan/3-0-video" },
  { id: "kie-minimax", label: "MiniMax H3 · Kie.ai", provider: "kie", model: "minimax-h3/image-to-video" },
  { id: "fal-kling", label: "Kling V3 Turbo Pro · fal.ai", provider: "fal", model: "fal-ai/kling-video/v3/turbo/pro/image-to-video" },
  { id: "fal-wan", label: "Wan 3.0 · fal.ai", provider: "fal", model: "alibaba/wan-3.0/image-to-video" },
];

type Filter = "new" | "major" | "minor" | "all";

/**
 * The take a fix must re-render. A flagged take is often a lip-synced version (kind "lipsync", made by a lip-sync model that can only re-time a mouth on a video that exists), and the faults the
 * reviewer found (framing, wardrobe, action, setting) belong to the video under it. So "same model" means the model that drew the video, found by following source_job; a lip-sync model is never
 * asked to draw a shot. Falls back to the shot's newest finished video take.
 */
export function videoBehind(job: Job, jobs: Job[]): Job {
  let cur = job;
  for (let i = 0; i < 6 && cur.kind === "lipsync" && cur.source_job; i++) {
    const next = jobs.find((x) => x.id === cur.source_job);
    if (!next) break;
    cur = next;
  }
  if (cur.kind === "lipsync" || cur.kind === "image") {
    const same = jobs.filter((x) => x.shot_id === job.shot_id && x.plan === job.plan && x.state === "ready" && (x.kind ?? "video") === "video" && x.output).sort((a, b) => b.created - a.created)[0];
    if (same) return same;
  }
  return cur;
}

/** PRD §27: only useful feedback, one action per problem. Every take is visible before you decide. */
export function ReviewSheet({ dir, shots, jobs = [], inUse = {}, keys, onSelect, onJobs, onClose, onOpen, onQueue, onChanged }: {
  dir: string; shots: Shot[]; jobs?: Job[]; inUse?: Record<string, string | null>; keys: KeyStatus; onChanged?: () => void;
  onSelect: (id: string) => void; onJobs: (j: Job[]) => void; onClose: () => void; onOpen?: (id: string) => void; onQueue?: () => void;
}) {
  const queue = useQueue(jobs);
  // The take in each shot's video (approved, else newest) and the new versions waiting to replace it. A swap is remembered here at once, before the board reloads.
  const [pinned, setPinned] = useState<Record<string, string>>({});
  const [declined, setDeclined] = useState<Set<string>>(new Set());
  const inUseNow = { ...inUse, ...pinned };
  const latest = useMemo(() => new Map(shots.flatMap((s) => { const t = inUseTake(s.id, jobs, inUseNow[s.id]); return t ? [[s.id, t] as [string, Job]] : []; })), [shots, jobs, pinned, inUse]); // eslint-disable-line react-hooks/exhaustive-deps
  const upgrades = upgradesFor(shots, jobs, inUseNow, declined);
  const upgradeOf = new Map(upgrades.map((u) => [u.shot.id, u]));
  const [swapping, setSwapping] = useState(false);
  const [confirm, setConfirm] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("major");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("same");
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});

  const rendered = shots.filter((s) => latest.get(s.id)?.state === "ready");
  const flagged = shots.map((s) => ({ shot: s, job: latest.get(s.id)! })).filter((x) => needsAttention(x.job));
  const major = flagged.filter((x) => x.job.review!.status === "needs_attention");
  const minor = flagged.filter((x) => x.job.review!.status === "minor");
  const unchecked = rendered.filter((s) => latest.get(s.id)?.review?.status === "unchecked" && !latest.get(s.id)?.review?.accepted);
  const good = rendered.length - flagged.length - unchecked.length;
  const shown = filter === "new" ? [] : filter === "major" ? major : filter === "minor" ? minor : flagged;
  useEffect(() => { if (filter === "major" && !major.length && minor.length) setFilter("minor"); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [seenUp, setSeenUp] = useState(0);
  useEffect(() => { if (upgrades.length > seenUp) { if (!seenUp) setFilter("new"); setSeenUp(upgrades.length); } else if (!upgrades.length) { setSeenUp(0); if (filter === "new") setFilter("major"); } }, [upgrades.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const outputs = useMemo(() => [...flagged.map((x) => x.job.output!), ...upgrades.flatMap((u) => [u.cur.output!, u.next.output!])].filter(Boolean), [flagged.map((x) => x.job.id).join(), upgrades.map((u) => u.next.id).join()]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (outputs.length) api.thumbs(dir, outputs).then(setThumbs).catch(() => {}); }, [dir, outputs]);

  const [localEyes, setLocalEyes] = useState(false);
  useEffect(() => { api.aiBrain("get").then((b) => setLocalEyes(b.provider !== "openai" && !!b.vision_model && (b.provider !== "openrouter" || !!keys.openrouter))).catch(() => {}); }, [keys.openrouter]);
  const visualOff = !keys.openai && !localEyes;
  const tgt = FIX_TARGETS.find((t) => t.id === target)!;
  const fixing = (id: string) => queue.rows.some((r) => r.job.shot_id === id && (r.job.kind ?? "video") === "video");
  const base = (id: string) => videoBehind(latest.get(id)!, jobs);
  const tgtProvider = (id: string) => tgt.provider ?? base(id).provider ?? "fal";
  const tgtModel = (id: string) => tgt.model ?? base(id).model ?? null;
  const canFix = (id: string) => (tgt.model ? true : (base(id).kind ?? "video") === "video");
  const [queued, setQueued] = useState("");
  const tgtBlocked = tgt.provider && !keys[tgt.provider as keyof KeyStatus];

  const fix = async (ids: string[]) => {
    setConfirm(null); setError(""); setQueued("");
    try {
      const made: Job[] = [];
      for (const id of ids) {
        const j = latest.get(id)!;
        const from = base(id);
        if (inUseNow[id] !== j.id) {   // keep the flagged take in the video until you swap the new one in
          try { await api.library(dir, "approve", { shot: id, job: j.id }); setPinned((p) => ({ ...p, [id]: j.id })); } catch { /* a locked shot is skipped by the render below */ }
        }
        // The reviewer's corrections travel with the re-render; same-model fixes keep the pinned settings of the video that was drawn.
        made.push(...await api.queueRender(dir, [id], tgtProvider(id), tgtModel(id), target === "same" ? from.overrides ?? {} : {}, j.review?.fixes ?? []));
      }
      onJobs(made);
      setPicked(new Set());
      setQueued(made.length
        ? `Queued ${made.length} re-render${made.length === 1 ? "" : "s"} with the reviewer's corrections. You can wait here: when each finishes, a button appears to swap it in (or swap them all at once). Your current takes stay in the video until you do.`
        : "Nothing was queued: those shots are already being rendered, are locked, or have no description yet.");
    } catch (e) { setError(errorText(e)); }
  };
  const accept = async (ids: string[]) => {
    try { for (const id of ids) onJobs([await api.resolveJob(dir, latest.get(id)!.id, "accept")]); setPicked(new Set()); }
    catch (e) { setError(errorText(e)); }
  };
  const swap = async (ups: typeof upgrades) => {
    setSwapping(true); setError("");
    try {
      for (const u of ups) { await api.library(dir, "approve", { shot: u.shot.id, job: u.next.id }); setPinned((p) => ({ ...p, [u.shot.id]: u.next.id })); }
      setQueued(`${ups.length === 1 ? "Swapped in the new version of " + ups[0].shot.id : `Swapped in ${ups.length} new versions`}. ${ups.length === 1 ? "It is" : "They are"} in your video now; the old ${ups.length === 1 ? "take is" : "takes are"} still in each shot's takes if you want ${ups.length === 1 ? "it" : "them"} back.`);
      onChanged?.();
    } catch (e) { setError(errorText(e)); } finally { setSwapping(false); }
  };
  const keepOld = async (u: (typeof upgrades)[number]) => {
    setDeclined((d) => new Set(d).add(u.next.id));
    try { if (needsAttention(u.cur)) onJobs([await api.resolveJob(dir, u.cur.id, "accept")]); } catch (e) { setError(errorText(e)); }
  };
  const goodOnes = upgrades.filter((u) => u.verdict === "good");
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const sel = shown.filter((x) => picked.has(x.shot.id)).map((x) => x.shot.id);
  const actOn = sel.length ? sel : shown.map((x) => x.shot.id);

  return (
    <Sheet label="Review" className="review-sheet" onDismiss={onClose}>
        <div className="rv-head">
          <div>
            <h2>Review</h2>
            <p className="sub">{reviewHeadline({ rendered: rendered.length, shots: shots.length, good, minor: minor.length, major: major.length, unchecked: unchecked.length, rendering: queue.active })}</p>
            {visualOff && <p className="rv-hint">Add an OpenAI key, or a local model that sees images, in Settings to also check characters, wardrobe, look and hands.</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close /></button>
        </div>

        <QueueBanner q={queue} onOpen={() => onQueue?.()} />
        {flagged.length === 0 && upgrades.length === 0 ? (
          <div className="review-empty"><I.Check size={20} /> {rendered.length ? "Every take looks usable." : queue.active ? "Nothing has finished yet. Takes show up here as they do." : "Nothing rendered yet."}</div>
        ) : <>
          <div className="rv-tabs" role="tablist">
            {([...(upgrades.length ? [["new", "New versions", upgrades.length] as const] : []), ["major", "Needs attention", major.length], ["minor", "Minor", minor.length], ["all", "All flagged", flagged.length]] as const).map(([k, l, n]) => (
              <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? "on" : ""} onClick={() => { setFilter(k); setPicked(new Set()); }}>{l}<span className="rv-count">{n}</span></button>
            ))}
          </div>
          {filter === "new" ? <div className="review-list">
            {upgrades.length > 0 && <div className="rv-listhead">
              <div><b>{swapHeadline(upgrades).title}</b><span className="dim">{swapHeadline(upgrades).detail}</span></div>
              <div className="rv-listhead-actions">
                {goodOnes.length > 0 && goodOnes.length < upgrades.length && <button className="btn small ghost" disabled={swapping} onClick={() => swap(goodOnes)}>Only the {goodOnes.length} that look good</button>}
                <button className="btn primary small" disabled={swapping} onClick={() => swap(upgrades)} title="Swapping replaces the take in your video. Nothing is deleted.">Use all {upgrades.length}</button>
              </div>
            </div>}
            {upgrades.map((u) => (
              <div key={u.shot.id} className={`rv-item up ${u.verdict}`}>
                <div className="up-pair">
                  <figure><RvMedia dir={dir} job={u.cur} thumb={u.cur.output ? thumbs[u.cur.output] : null} onOpen={() => onOpen?.(u.shot.id)} /><figcaption>In your video now</figcaption></figure>
                  <span className="up-arrow" aria-hidden="true">→</span>
                  <figure><RvMedia dir={dir} job={u.next} thumb={u.next.output ? thumbs[u.next.output] : null} onOpen={() => onOpen?.(u.shot.id)} /><figcaption>New version</figcaption></figure>
                </div>
                <div className="rv-body">
                  <div className="rv-meta"><span className="rv-id num">{u.shot.id}</span><span className="dim num">{fmtTime(u.shot.start)}</span>
                    <span className={`rv-sev up-${u.verdict}`}><i />{VERDICT_WORDS[u.verdict]}</span>
                    <span className="dim rv-model">{PROVIDER_NAME[u.next.provider] ?? u.next.provider} · {u.next.model.split("/").slice(-2).join("/")}</span></div>
                  <div className="rv-sum">{u.next.review?.summary ?? (u.verdict === "checking" ? "The new version is being checked now." : "")}</div>
                  {(u.verdict === "minor" || u.verdict === "major") && <Issues issues={u.next.review?.issues} />}
                  <div className="rv-actions">
                    <button className="btn small primary" disabled={swapping} onClick={() => swap([u])}>Use new version</button>
                    <button className="btn small ghost" disabled={swapping} onClick={() => keepOld(u)}>Keep the old one</button>
                    <button className="btn small ghost" onClick={() => { onSelect(u.shot.id); onClose(); }}>Show in timeline</button>
                  </div>
                </div>
              </div>))}
            {!upgrades.length && <div className="dim" style={{ padding: 12 }}>Nothing waiting to be swapped.</div>}
          </div> : <div className="review-list">
            {shown.length === 0 && <div className="dim" style={{ padding: 12 }}>Nothing here.</div>}
            {shown.map(({ shot, job }) => {
              const t = job.output ? thumbs[job.output] : null;
              const isMajor = job.review!.status === "needs_attention";
              return (
                <div key={shot.id} className={`rv-item ${isMajor ? "major" : "minor"} ${picked.has(shot.id) ? "picked" : ""}`}>
                  <label className="rv-check" title="Select"><input type="checkbox" aria-label={`Select shot ${shot.id}`} checked={picked.has(shot.id)} onChange={() => toggle(shot.id)} /></label>
                  <RvMedia dir={dir} job={job} thumb={t} onOpen={() => onOpen?.(shot.id)} />
                  <div className="rv-body">
                    <div className="rv-meta">
                      <span className="rv-id num">{shot.id}</span>
                      <span className="dim num">{fmtTime(shot.start)}</span>
                      <span className={`rv-sev ${isMajor ? "major" : "minor"}`}><i />{isMajor ? "Needs attention" : "Minor"}</span>
                      <span className="dim rv-model">{PROVIDER_NAME[job.provider] ?? job.provider} · {job.model.split("/").slice(-2).join("/")}</span>
                    </div>
                    <div className="rv-sum">{job.review!.summary}</div>
                    <Issues issues={job.review!.issues} />
                    <div className="rv-actions">
                      {fixing(shot.id) ? <span className="chip gen"><span className="spin sm" /> Fixing: re-rendering</span> : upgradeOf.has(shot.id) ? <button className="btn small primary" disabled={swapping} onClick={() => { setFilter("new"); }}>New version ready: see it</button> : <button className="btn small primary" onClick={() => setConfirm([shot.id])}>Fix</button>}
                      <button className="btn small ghost" onClick={() => accept([shot.id])}>Keep</button>
                      <button className="btn small ghost" onClick={() => { onSelect(shot.id); onClose(); }}>Show in timeline</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>}
        </>}
        {error && <div className="error-text" role="alert">{error}</div>}
        {queued && <div className="note ok" role="status"><I.Check size={14} /> {queued}</div>}
        <div className="rv-foot">
          {flagged.length > 0 && filter !== "new" && <>
            <label className="rv-target"><span className="dim">Fix with</span>
              <select className="text-input" value={target} onChange={(e) => setTarget(e.target.value)}>
                {FIX_TARGETS.map((t) => <option key={t.id} value={t.id} disabled={!!t.provider && !keys[t.provider as keyof KeyStatus]}>
                  {t.label}{t.provider && !keys[t.provider as keyof KeyStatus] ? " (no key)" : ""}</option>)}
              </select></label>
            <div style={{ flex: 1 }} />
            <button className="btn ghost" disabled={!shown.length} onClick={() => accept(actOn)}>Keep {sel.length ? sel.length : "all"}</button>
            <button className="btn primary" disabled={!shown.length || !!tgtBlocked || !actOn.every(canFix)} onClick={() => setConfirm(actOn)}>
              Fix {sel.length ? `${sel.length} selected` : `all ${shown.length}`}</button>
          </>}
          {(!flagged.length || filter === "new") && <><div style={{ flex: 1 }} /><button className="btn" onClick={onClose}>Close</button></>}
        </div>
        <p className="dim rv-note">Fix re-renders with the reviewer's corrections added. The current take stays until you choose the new version.
          {filter !== "major" && minor.length > 0 && " Minor flags are usually fine to keep."}</p>

        {confirm && <ConfirmRender count={confirm.length} seconds={0} provider={tgtProvider(confirm[0])}
                                   model={target === "same" ? `${base(confirm[0]).model.split("/").slice(-2).join("/")} (the model that drew the flagged video), with the reviewer's corrections` : `${tgt.label}, with the reviewer's corrections`}
                                   onCancel={() => setConfirm(null)} onConfirm={() => fix(confirm)}
                                   dir={dir} shots={confirm} modelId={tgtModel(confirm[0])} />}
    </Sheet>
  );
}

/** What the check found: the most serious thing in one line, and the rest one click away. */
function Issues({ issues }: { issues?: { kind: string; severity: string; detail: string }[] }) {
  const { first, rest } = splitIssues(issues);
  if (!first) return null;
  const row = (i: { kind: string; severity: string; detail: string }, k: number) => <li key={k} className={i.severity}><i aria-hidden="true" /><span><b>{KIND[i.kind] ?? i.kind}</b> {i.detail}</span></li>;
  return (
    <div className="rv-issues-wrap">
      <ul className="rv-issues">{row(first, 0)}</ul>
      {rest.length > 0 && <details className="rv-more"><summary>{rest.length} more detail{rest.length === 1 ? "" : "s"}</summary><ul className="rv-issues">{rest.map((i, k) => row(i, k + 1))}</ul></details>}
    </div>
  );
}

/** The flagged take itself: still thumbnail, plays on hover, click opens the shot viewer. */
function RvMedia({ dir, job, thumb, onOpen }: { dir: string; job: Job; thumb?: string | null; onOpen: () => void }) {
  const [play, setPlay] = useState(false);
  return (
    <button className="rv-media" onClick={onOpen} onMouseEnter={() => setPlay(true)} onMouseLeave={() => setPlay(false)} title="Open this shot">
      {play && job.output ? <video src={api.mediaUrl(`${dir}/${job.output}`)} autoPlay muted loop playsInline />
        : thumb ? <img src={api.mediaUrl(`${dir}/${thumb}`)} alt="" /> : <span className="dim">…</span>}
      <span className="rv-play"><I.Play size={12} /></span>
    </button>
  );
}
