import { useEffect, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, type Job, type Shot } from "./api";
import * as I from "./icons";
import { CheaperRetry } from "./CheaperRetry";
import { fmtDuration, kindLabel, queueSentence, queueSummary, type QueueRow, type QueueSummary } from "./queueMath";

/** The clock the queue measures against, in seconds. Ticks once a second while something is rendering, and not at all when nothing is. */
export function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    setNow(Math.floor(Date.now() / 1000));
    if (!ticking) return;
    const t = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(t);
  }, [ticking]);
  return now;
}

export function useQueue(jobs: Job[]): QueueSummary {
  const active = jobs.some((j) => j.state === "queued" || j.state === "submitting" || j.state === "submitted");
  const now = useNow(active);
  return queueSummary(jobs, now);
}

/** In the top bar while anything is rendering: one line of truth, and a way into the queue. */
export function QueueChip({ q, onOpen }: { q: QueueSummary; onOpen: () => void }) {
  if (!q.active) return null;
  return (
    <button className="spend-chip route-chip queue-chip" onClick={onOpen} title="See every render, what it is doing and how long is left" aria-label={`Render queue: ${queueSentence(q)}`}>
      <span className="spin sm" /> {queueSentence(q).replace(/ · about.*$/, "")}
    </button>
  );
}

/** One line in the Review sheet while renders are still coming in. */
export function QueueBanner({ q, onOpen }: { q: QueueSummary; onOpen: () => void }) {
  if (!q.active) return null;
  return (
    <div className="queue-banner" role="status">
      <span className="spin sm" /> <span><b>{q.active} still rendering:</b> {queueSentence(q)}. New takes appear here, checked, as they finish.</span>
      <button className="btn ghost small" onClick={onOpen}>See progress</button>
    </div>
  );
}

function Bar({ row }: { row: QueueRow }) {
  if (row.phase !== "rendering" && row.phase !== "sending") return null;
  const pct = row.fraction != null ? Math.round(row.fraction * 100) : null;
  return (
    <div className={`q-bar ${pct == null ? "indeterminate" : ""}`} role="progressbar" aria-label={`${row.job.shot_id} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined}
         aria-valuetext={pct == null ? "in progress" : `${pct} percent`}>
      <i style={pct == null ? undefined : { width: `${pct}%` }} />
    </div>
  );
}

function Row({ row, name, dir, onShow, onChanged, onError }: { row: QueueRow; name: string; dir: string; onShow: (shot: string) => void; onChanged: (j: Job) => void; onError: (m: string) => void }) {
  const j = row.job;
  const act = async (action: "cancel" | "retry" | "dismiss") => { try { onChanged(await api.resolveJob(dir, j.id, action)); } catch (e) { onError(errorText(e)); } };
  const model = j.kind === "asset" ? (j.asset_name ?? "reference picture") : j.model.split("/").slice(-2).join("/");
  return (
    <li className={`q-row ${row.phase}`}>
      <div className="q-main">
        <span className="q-id num">{j.shot_id || "—"}</span>
        <span className="q-kind">{kindLabel(j)}</span>
        <span className="dim q-model">{model}</span>
        <span className="q-state">{row.phase === "done" ? <I.Check size={13} /> : row.phase === "failed" || row.phase === "check" ? <I.Alert size={13} /> : null} {row.label}</span>
        <span className="q-time dim num">
          {row.elapsed != null && `${fmtDuration(row.elapsed)} so far`}{row.etaS != null && row.etaS > 0 && ` · about ${fmtDuration(row.etaS)} left`}
          {row.phase === "done" && j.cost != null && j.cost > 0 && `${j.cost_unit === "credits" ? j.cost + " credits" : "$" + j.cost.toFixed(2)}`}
        </span>
      </div>
      <Bar row={row} />
      {(row.phase === "failed" || row.phase === "check") && j.error && <div className="q-error">{j.error}</div>}
      {j.retry_note && <div className="dim q-note">{j.auto_retried ? "Retried automatically. " : ""}{j.retry_note}</div>}
      {j.retried_as && <div className="dim q-note">Retried on another model.</div>}
      <div className="q-actions">
        {j.shot_id && <button className="btn ghost small" onClick={() => onShow(j.shot_id)}>Show {name}</button>}
        {row.phase === "waiting" && <button className="btn ghost small" onClick={() => act("cancel")}>Cancel (not sent yet, nothing billed)</button>}
        {row.phase === "failed" && <CheaperRetry dir={dir} job={j} onJobs={(js) => js.forEach(onChanged)} />}
        {(row.phase === "failed" || row.phase === "check") && <>
          <button className="btn small" onClick={() => act("retry")}>Try again</button>
          <button className="btn ghost small" onClick={() => act("dismiss")}>Dismiss</button></>}
      </div>
    </li>
  );
}

export function RenderQueueSheet({ dir, jobs, shots, onJob, onShow, onReview, onClose }: {
  dir: string; jobs: Job[]; shots: Shot[]; onJob: (j: Job) => void; onShow: (shot: string) => void; onReview: () => void; onClose: () => void;
}) {
  const q = useQueue(jobs);
  const [err, setErr] = useState("");
  const name = (id: string) => (shots.some((s) => s.id === id) ? `shot ${id}` : "it");
  const groups: [string, QueueRow[]][] = [["Failed or needs a check", q.failed], ["Rendering and waiting", q.rows], ["Finished in the last 15 minutes", q.done]];
  const empty = !q.rows.length && !q.done.length && !q.failed.length;
  return (
    <Sheet label="Render queue" className="queue-sheet" onDismiss={onClose}>
        <div className="rv-head">
          <div>
            <h2>Render queue</h2>
            <p className="sub" role="status">{q.active ? queueSentence(q) + (q.estUsd != null ? ` · about $${q.estUsd.toFixed(2)} in flight` : "") : "Nothing is rendering right now."}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close /></button>
        </div>
        {empty && <div className="review-empty">No renders yet. Queue some from a shot, or press “Render all”.</div>}
        <div className="queue-list">
          {groups.map(([title, rows]) => rows.length > 0 && (
            <section key={title}>
              <h3 className="perf-h">{title} <span className="dim" style={{ textTransform: "none", letterSpacing: 0 }}>{rows.length}</span></h3>
              <ul className="q-rows">{rows.map((r) => <Row key={r.job.id} row={r} name={name(r.job.shot_id)} dir={dir} onShow={(s) => { onShow(s); onClose(); }} onChanged={onJob} onError={setErr} />)}</ul>
            </section>))}
        </div>
        {err && <div className="error-text" role="alert">{err}</div>}
        <div className="rv-foot">
          <span className="dim">Renders keep going if you close this. Times are estimates from this project's earlier takes.</span>
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={() => { onClose(); onReview(); }}>Open Review</button>
        </div>
    </Sheet>
  );
}
