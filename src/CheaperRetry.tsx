import { useState } from "react";
import { api, errorText, type Job } from "./api";
import { ask } from "./ask";

export type RetryOption = { provider: string; model: string; label: string; price_usd: number; cheaper: boolean | null; saves_usd: number | null; strength: string; warning: string };
export type RetryOptions = { can: boolean; reason?: string; options: RetryOption[]; original_usd?: number | null; failed_model?: string; auto?: boolean };

/** Pure: the price of one try, in words. */
export const usd = (n: number): string => `$${n < 0.1 ? n.toFixed(3) : n.toFixed(2)}`;

/** Pure: one option as a line, with what it saves when the failed model's price is known. */
export function optionLine(o: Pick<RetryOption, "label" | "price_usd" | "saves_usd">): string {
  return `${o.label} · about ${usd(o.price_usd)}${o.saves_usd != null && o.saves_usd > 0 ? ` (saves ${usd(o.saves_usd)})` : ""}`;
}

/** Pure: the question asked before a retry is sent. */
export function confirmText(o: RetryOption, shot: string): string {
  return `Retry ${shot} on ${o.label}.\n\nAbout ${usd(o.price_usd)}. The failed render stays in the list.${o.warning ? `\n\n${o.warning}` : ""}\n\nSend it?`;
}

/** On a failed render: the cheaper models FilmCrafter has proved, with prices, and one click to try the shot again on the one you choose. Free until you confirm. */
export function CheaperRetry({ dir, job, onJobs }: { dir: string; job: Job; onJobs: (jobs: Job[]) => void }) {
  const [opts, setOpts] = useState<RetryOptions | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  if (job.state !== "failed" || job.retried_as || (job.kind ?? "video") === "asset") return null;
  const load = async () => {
    setOpen(true); setErr(""); setBusy(true);
    try { setOpts(await api.retryCheaper<RetryOptions>(dir, "options", { job: job.id })); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const send = async (o: RetryOption) => {
    if (!(await ask(confirmText(o, job.shot_id)))) return;
    setBusy(true); setErr("");
    try { const r = await api.retryCheaper<{ jobs: Job[] }>(dir, "retry", { job: job.id, provider: o.provider, model: o.model }); onJobs(r.jobs ?? []); setOpen(false); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="cr">
      {!open && <button className="btn ghost small" onClick={load} title="See cheaper models that FilmCrafter has proved with a real render. Free: nothing is sent until you confirm.">Try a cheaper model…</button>}
      {open && <div className="cr-box">
        {busy && !opts && <span className="dim"><span className="spin sm" /> Looking at the prices…</span>}
        {opts && !opts.can && <p className="dim">{opts.reason}</p>}
        {opts?.can && <>
          <p className="dim">{opts.original_usd != null ? `The failed model costs about ${usd(opts.original_usd)}. ` : ""}These are proved with a real render here.</p>
          <ul className="cr-list">{opts.options.map((o) => (
            <li key={o.provider + o.model}>
              <span><b>{optionLine(o)}</b>{o.strength && <span className="dim"> — {o.strength}</span>}</span>
              <button className="btn small" disabled={busy} onClick={() => send(o)}>Use this</button>
            </li>))}</ul></>}
        {err && <p className="error-text" role="alert">{err}</p>}
        <button className="link" onClick={() => setOpen(false)}>Close</button>
      </div>}
    </div>
  );
}
