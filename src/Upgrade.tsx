import { useEffect, useState } from "react";
import { api, errorText, type BoardShot, type Estimate } from "./api";
import { PanelHead } from "./Dock";
import { listPrice, shotLength, shotPrice } from "./price";
import * as I from "./icons";

type Row = { label: string; provider: string; model: string; price_usd: number | null; verified: boolean };

/** Quality ladder: re-render this shot from its keyframe on a better (or cheaper) model, with the price first. */
export function UpgradePanel({ dir, shot, open, onDone }: { dir: string; shot?: BoardShot; open: boolean; onDone: () => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [pick, setPick] = useState<Row | null>(null);
  const [est, setEst] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api.routing<{ video: Row[] }>(dir, "models").then((m) => setRows(m.video.filter((r) => r.verified))).catch(() => {}); }, [dir]);
  useEffect(() => { if (open) document.querySelector(".upgrade")?.scrollIntoView({ block: "nearest" }); }, [open]);
  if (!shot || !shot.keyframe) return null;
  const inUse = shot.versions.find((v) => v.approved) ?? shot.versions.filter((v) => v.state === "ready").slice(-1)[0];
  const current = inUse ? (inUse.provider === "own" ? (inUse.media_kind === "image" ? "a moving still" : "your own clip") : `${inUse.model.split("/").slice(-2).join("/")} on ${inUse.provider}`) : "nothing yet";
  const choose = async (r: Row) => {
    setPick(r); setEst(null); setErr("");
    setEst(await api.renderEstimate(dir, [shot.id], r.provider, r.model, "video").catch(() => null));
  };
  const send = async () => {
    if (!pick) return;
    setBusy("Sending…"); setErr("");
    try { await api.queueRender(dir, [shot.id], pick.provider, pick.model, {}); setPick(null); onDone(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const price = (r: Row) => listPrice(r.price_usd);
  return (
    <details className={`panel upgrade ${open ? "hl" : ""}`} open={open || undefined}>
      <summary><PanelHead icon={<I.Layers size={18} />} title="Quality ladder" tag="Re-render on a better model" tone="free" right={<I.Chevron size={16} />} /></summary>
      <p className="dim">Now using {current}. Re-render from the same keyframe on any proven model; the new take becomes a version you can compare. The prices in the list are for a typical 5-second shot so the models can be compared; pick one to see the price of this shot ({shotLength(shot.start, shot.end)}).</p>
      <div className="up-list">{rows.map((r) => (
        <button key={r.provider + r.model} className={`mp-row ${pick === r ? "on" : ""}`} onClick={() => choose(r)}>
          <span className="mp-name">{r.label} <span className="dim">· {r.provider}</span></span><span className="mp-price">{price(r)}</span><span />
        </button>))}</div>
      {pick && <div className="sup-confirm" style={{ marginTop: 8, flexWrap: "wrap" }}>
        <span style={{ flex: "1 1 100%" }}>{pick.label} on {pick.provider}, this shot ({shotLength(shot.start, shot.end)}): <b>{shotPrice(est, price(pick))}</b></span>
        {est?.basis && <span className="dim" style={{ flex: "1 1 100%", fontSize: 12 }}>{est.basis}</span>}
        <button className="btn primary small" onClick={send} disabled={!!busy}>{busy || "Render"}</button>
        <button className="btn ghost small" onClick={() => setPick(null)}>Cancel</button></div>}
      {err && <div className="error-text">{err}</div>}
    </details>
  );
}
