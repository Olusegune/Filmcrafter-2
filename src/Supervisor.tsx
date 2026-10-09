import { useCallback, useEffect, useState } from "react";
import { api, errorText, type Estimate } from "./api";
import { DirectorChanges } from "./DirectorChanges";
import { IntroCardSheet } from "./IntroCard";
import * as I from "./icons";
import { useRouting } from "./Routing";
import { useBoard } from "./Board";

type Item = { id: string; shot: string; source: string; severity: "major" | "minor" | "info"; title: string; detail: string; fix: string;
  kind: "image" | "video" | "lipsync"; render?: { provider: string; model: string } | null; actions: ("accept" | "ignore" | "fix" | "regenerate" | "recheck" | "title" | "card")[]; status: string;
  decision?: { action: string; at: number; note?: string; provider?: string; model?: string } | null };
type Group = { id: string; scene: string; title: string; kind: string; action: "fix" | "regenerate"; items: string[]; shots: string[];
  render?: { provider: string; model: string } | null };
type Listing = { items: Item[]; groups: Group[]; summary: { open: number; major: number; minor: number; info: number; decided: number; ready: boolean } };

/** The engine's answer made safe to draw: a reply with a part missing (or nothing at all) shows an empty, release-ready list instead of taking the whole sheet down. */
export function normaliseListing(raw: unknown): Listing {
  const r = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as Partial<Listing>;
  const base = { open: 0, major: 0, minor: 0, info: 0, decided: 0, ready: true };
  const s = r.summary && typeof r.summary === "object" ? r.summary : {};
  return { items: Array.isArray(r.items) ? r.items : [], groups: Array.isArray(r.groups) ? r.groups : [], summary: { ...base, ...s } };
}
type Pending = { item: Item; action: "fix" | "regenerate"; provider: string; model: string; est: Estimate | null; pricing: boolean };
type Batch = { key: string; label: string; ids: string[]; shots: string[]; kind: string; action: "fix" | "regenerate"; provider: string; model: string;
  est: Estimate | null; pricing: boolean };

const ACTION_LABEL = { accept: "Accept", ignore: "Ignore", fix: "Fix", regenerate: "Regenerate", recheck: "Check again (no charge)", title: "Add a title card", card: "Design the intro…" };
const STATUS_LABEL: Record<string, string> = { recheck: "Checking with the provider…", accept: "Accepted", ignore: "Ignored", working: "Re-rendering…", done: "Re-rendered", failed: "Re-render failed" };

/** Production Supervisor: every finding in one queue, with Review / Accept / Fix / Regenerate / Ignore. */
export function SupervisorSheet({ dir, onClose, onReview, onChanged }: { dir: string; onClose: () => void; onReview: (shot: string) => void; onChanged: () => void }) {
  const [l, setL] = useState<Listing | null>(null);
  const [show, setShow] = useState<"open" | "all">("open");
  const [sev, setSev] = useState<"all" | "major" | "minor" | "info">("all");
  const [busy, setBusy] = useState("");
  const [card, setCard] = useState(false);
  const [err, setErr] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const { route } = useRouting(dir);
  const { board, thumbs, want } = useBoard(dir, []);
  const shotSrc = (id: string) => board?.shots.find((s) => s.id === id)?.thumb_src ?? null;
  const pictureOf = (id: string) => { const s = shotSrc(id), t = s ? thumbs[s] : null; return t ? api.mediaUrl(`${dir}/${t}`) : null; };
  const needed = (l?.items ?? []).map((i) => shotSrc(i.shot)).concat((l?.groups ?? []).flatMap((g) => g.shots.map(shotSrc))).filter((x): x is string => !!x);
  const wantKey = needed.join("|") + "|" + (board?.shots.length ?? 0);
  useEffect(() => { const srcs = [...(board?.shots ?? []).map((s) => s.thumb_src).filter((x): x is string => !!x)]; if (srcs.length) want(srcs); }, [wantKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const load = useCallback(() => api.supervisor<Listing>(dir, "list").then((r) => setL(normaliseListing(r))).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);

  const decide = async (item: Item, action: string, extra: Record<string, unknown> = {}) => {
    setBusy(item.id); setErr("");
    try { setL(normaliseListing(await api.supervisor<Listing>(dir, "decide", { item: item.id, action, ...extra }))); onChanged(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const [batch, setBatch] = useState<Batch | null>(null);
  const [lip, setLip] = useState<{ shots: number } | null>(null);
  const [lipMsg, setLipMsg] = useState("");
  useEffect(() => { api.lipsyncCheck<{ shots: number }>(dir, "count").then(setLip).catch(() => {}); }, [dir]);
  const priceBatch = async (key: string, label: string, ids: string[], shots: string[], kind: string, action: "fix" | "regenerate", render?: Group["render"]) => {
    const pick = render ?? (kind === "image" ? route?.image : route?.video);
    if (!pick?.provider) { setErr((pick as { reason?: string })?.reason ?? "No provider to render with. Check Plan & budget."); return; }
    const b: Batch = { key, label, ids, shots, kind, action, provider: pick.provider, model: pick.model!, est: null, pricing: true };
    setBatch(b);
    const est = kind === "lipsync" ? null : await api.renderEstimate(dir, shots, b.provider, b.model, kind as "image" | "video").catch(() => null);
    setBatch({ ...b, est, pricing: false });
  };
  const sendBatch = async () => {
    if (!batch) return;
    const b = batch; setBatch(null); setBusy("batch"); setErr("");
    try {
      const r = await api.supervisor<Listing & { batch: { done: string[]; skipped: { shot: string; reason: string }[] } }>(dir, "decide_many",
        { items: b.ids, action: b.action, provider: b.provider, model: b.model });
      setL(normaliseListing(r)); onChanged();
      if (r.batch?.skipped?.length) setErr(`Sent ${(r.batch.done ?? []).length}; not sent: ${r.batch.skipped.map((s) => `${s.shot} (${s.reason})`).join("; ")}`);
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const runLip = async () => {
    setBusy("lip"); setLipMsg("Checking lip-sync…"); setErr("");
    try {
      const r = await api.lipsyncCheck<{ checked: number; off: string[]; errors: string[] }>(dir, "run");
      setLipMsg(`Checked ${r.checked} singing shot${r.checked === 1 ? "" : "s"}: ${r.off.length ? `${r.off.length} out of sync (listed below)` : "all in sync"}.`);
      if (r.errors.length) setErr(r.errors.join(" "));
      await load();
    } catch (e) { setErr(errorText(e)); setLipMsg(""); } finally { setBusy(""); }
  };
  const [backlog, setBacklog] = useState(0);
  useEffect(() => { api.reviewBacklog(dir, false).then((r) => setBacklog(r.unchecked)).catch(() => {}); }, [dir]);
  const runBacklog = async () => {
    setBusy("backlog"); setErr("");
    try { const r = await api.reviewBacklog(dir, true); setBacklog(r.unchecked); await load(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const stale = (l?.items ?? []).filter((i) => i.source === "keyframe changed" && ["open", "failed"].includes(i.status));

  const price = async (item: Item, action: "fix" | "regenerate") => {
    const pick = item.kind === "lipsync" ? item.render : item.kind === "image" ? route?.image : route?.video;
    if (!pick?.provider) { setErr((pick as { reason?: string } | null | undefined)?.reason ?? "No provider to render with. Check Plan & budget."); return; }
    const p: Pending = { item, action, provider: pick.provider, model: pick.model!, est: null, pricing: true };
    setPending(p);
    const est = item.kind === "lipsync" ? null : await api.renderEstimate(dir, [item.shot], p.provider, p.model, item.kind).catch(() => null);
    setPending({ ...p, est, pricing: false });
  };
  const confirm = async () => {
    if (!pending) return;
    const p = pending; setPending(null);
    await decide(p.item, p.action, { provider: p.provider, model: p.model });
  };

  const items = (l?.items ?? []).filter((i) => (show === "all" || ["open", "failed"].includes(i.status)) && (sev === "all" || i.severity === sev));
  const cost = (e: Estimate | null, i_kind: string) => i_kind === "lipsync" ? "priced by the second of video (about $0.13 per second on fal)" : !e ? "Price unknown" : e.usd != null ? `≈ $${e.usd.toFixed(2)}` : e.kie_credits_est ? `≈ ${e.kie_credits_est} Kie credits` : `price not published (the budget counts it as $${i_kind === "image" ? "0.25" : "1.00"})`;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass sup-sheet" role="dialog" aria-label="Production Supervisor" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Production Supervisor</h2><div style={{ flex: 1 }} />
          <button className="btn ghost small" onClick={load}>Refresh</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Every quality finding in one place: take reviews, keyframe checks, continuity, failed renders and shots still
          missing. Decide each one. Fix re-renders with the finding's correction; Regenerate re-renders as planned. Both show the price first
          and follow the project's mode and budget. Nothing is ever re-rendered without you.</p>
        <DirectorChanges dir={dir} onChanged={onChanged} picture={pictureOf} />
        {l && <div className={`sup-summary ${l.summary.ready ? "ready" : ""}`}>
          {l.summary.ready ? <><I.Check size={16} /> <b>Release ready:</b> no open major findings.</> :
            <><I.Alert size={16} /> <b>{l.summary.major} major</b> finding{l.summary.major === 1 ? "" : "s"} to decide before release.</>}
          <span className="dim">{l.summary.minor} minor · {l.summary.info} notes · {l.summary.decided} decided</span>
        </div>}
        <div className="sup-batches">
          {stale.length > 0 && <div className="sup-batch">
            <span><b>{stale.length} video{stale.length === 1 ? "" : "s"}</b> made from an older keyframe: {stale.map((i) => i.shot).join(", ")}</span>
            <button className="btn small" disabled={!!busy} onClick={() => priceBatch("stale", `Re-render ${stale.length} videos from their new keyframes`, stale.map((i) => i.id),
              stale.map((i) => i.shot), "video", "regenerate")}>Re-render these</button></div>}
          {(l?.groups ?? []).slice(0, 6).map((g) => <div key={g.id} className="sup-batch">
            <span>Scene {g.scene} · <b>{g.title}</b> in {g.shots.length} shots ({g.shots.join(", ")})</span>
            <button className="btn small ghost" disabled={!!busy} onClick={() => priceBatch(g.id, `${g.action === "fix" ? "Fix" : "Re-render"} ${g.shots.length} shots: ${g.title}`,
              g.items, g.shots, g.kind, g.action, g.render)}>{g.action === "fix" ? "Fix all" : "Re-render all"} {g.shots.length}</button></div>)}
          {backlog > 0 && <div className="sup-batch">
            <span><b>{backlog} take{backlog === 1 ? "" : "s"}</b> never visually checked. FilmCrafter no longer checks old takes on its own; check them now
              {route?.brain.local ? " (free on your local model)" : " (one AI look each, a few cents on OpenAI)"}?</span>
            <button className="btn small ghost" disabled={!!busy} onClick={runBacklog}>{busy === "backlog" ? "Checking…" : `Check ${backlog}`}</button></div>}
          {lip && lip.shots > 0 && <div className="sup-batch">
            <span>{lipMsg || <>Lip-sync: <b>{lip.shots} singing shot{lip.shots === 1 ? "" : "s"}</b> can be checked (one AI look each{route?.brain.local ? ", free on your local model" : ", a few cents each on OpenAI"}).</>}</span>
            <button className="btn small ghost" disabled={!!busy} onClick={runLip}>{busy === "lip" ? "Checking…" : "Check lip-sync"}</button></div>}
          {batch && <div className="sup-confirm sup-batch-confirm">
            <span>{batch.label} on <b>{batch.provider}</b> ({batch.model.split("/").slice(-1)[0]}): <b>{batch.pricing ? "pricing…" : cost(batch.est, batch.kind)}</b></span>
            <button className="btn primary small" onClick={sendBatch} disabled={batch.pricing}>Send</button>
            <button className="btn ghost small" onClick={() => setBatch(null)}>Cancel</button></div>}
        </div>
        <div className="sup-filters">
          <div className="mode-toggle">{(["open", "all"] as const).map((k) => <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{k === "open" ? "To decide" : "Everything"}</button>)}</div>
          <div className="mode-toggle">{(["all", "major", "minor", "info"] as const).map((k) => <button key={k} className={sev === k ? "on" : ""} onClick={() => setSev(k)}>{k === "all" ? "All" : k === "info" ? "Notes" : k[0].toUpperCase() + k.slice(1)}</button>)}</div>
        </div>
        {err && <div className="error-text">{err}</div>}
        {!l ? <div className="dim">Checking the production…</div> : items.length === 0 ? <p className="dim">Nothing here. {show === "open" ? "Every finding has a decision." : ""}</p> :
          <div className="sup-list">{items.map((i) => (
            <div key={i.id} className={`sup-item sev-${i.severity}`}>
              {pictureOf(i.shot) && <img className="sup-pic" src={pictureOf(i.shot)!} alt={i.shot} />}
              <div className="sup-head">
                <span className={`sup-sev ${i.severity}`}>{i.severity === "info" ? "note" : i.severity}</span>
                <button className="link num" onClick={() => { onReview(i.shot); onClose(); }} title="Review this shot">{i.shot}</button>
                <b>{i.title}</b><span className="dim sup-src">{i.source}</span>
                {i.status !== "open" && <span className={`chip sup-status ${i.status}`}>{STATUS_LABEL[i.status] ?? i.status}</span>}
              </div>
              <div className="sup-detail">{i.detail}</div>
              {i.fix && <div className="sup-fix"><b>Correction:</b> {i.fix}</div>}
              {pending?.item.id === i.id ? (
                <div className="sup-confirm">
                  <span>{pending.action === "fix" ? "Re-render with the correction" : "Re-render as planned"} on <b>{pending.provider}</b> ({pending.model.split("/").slice(-1)[0]}):{" "}
                    <b>{pending.pricing ? "pricing…" : cost(pending.est, pending.item.kind)}</b></span>
                  <button className="btn primary small" onClick={confirm} disabled={pending.pricing}>Send</button>
                  <button className="btn ghost small" onClick={() => setPending(null)}>Cancel</button>
                </div>
              ) : (
                <div className="sup-actions">
                  <button className="btn ghost small" onClick={() => { onReview(i.shot); onClose(); }}>Review</button>
                  {i.status !== "open" && <button className="btn ghost small" disabled={busy === i.id} onClick={() => decide(i, "reopen")}>Reopen</button>}
                  {i.actions.filter((a) => !(i.status === "working" && (a === "fix" || a === "regenerate"))).map((a) => (i.status === a ? null :
                    <button key={a} className={`btn small ${a === "fix" ? "" : a === "card" ? "primary" : "ghost"}`} disabled={busy === i.id}
                            onClick={() => a === "fix" || a === "regenerate" ? price(i, a) : a === "card" ? setCard(true) : decide(i, a)}>{ACTION_LABEL[a]}</button>))}
                </div>)}
            </div>))}</div>}
      </div>
      {card && <IntroCardSheet dir={dir} onClose={() => setCard(false)} onChanged={() => { onChanged(); load(); }} />}
    </div>
  );
}
