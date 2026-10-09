import { useCallback, useEffect, useState } from "react";
import { api, AUTO_IMAGE_MODEL, errorText, type CatalogItem, type KeyStatus, type RefGenStatus } from "./api";
import { ModelPicker } from "./ModelPicker";
import { ask } from "./ask";
import * as I from "./icons";

const PROVIDERS = [["kie", "Kie.ai"], ["fal", "fal.ai"], ["google", "Google"], ["openai", "OpenAI"]] as const;
const KIND: Record<string, string> = { character: "Character", wardrobe: "Outfit", prop: "Prop", set: "Place" };
const STATE: Record<string, string> = { queued: "Waiting", submitting: "Sending…", submitted: "Making…", ready: "Ready", failed: "Failed", uncertain: "Check provider" };
const ACTIVE = ["queued", "submitting", "submitted"];

type Est = { count: number; usd: number | null; kie_credits_est?: number; basis: string; title: string; uses?: { model: string; title: string; count: number }[] };

/**
 * Make the pictures a package only described: characters who appear only in a group picture, and outfits, props and places with no
 * picture at all. Each picture is made from the prompt the package wrote for it, after the price is shown and confirmed, and only
 * becomes the reference when you choose it.
 */
export function RefGenSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged: () => void }) {
  const [st, setSt] = useState<RefGenStatus | null>(null);
  const [keys, setKeys] = useState<KeyStatus | null>(null);
  const [provider, setProvider] = useState<string>("kie");
  const [model, setModel] = useState(AUTO_IMAGE_MODEL.kie);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [est, setEst] = useState<Est | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const s = await api.refgen(dir, "status");
    setSt(s);
    setPicked((p) => { const n = { ...p }; for (const c of s.candidates) if (!(c.id in n)) n[c.id] = true; return n; });
  }, [dir]);
  useEffect(() => { load().catch((e) => setErr(errorText(e))); api.keyStatus().then(setKeys).catch(() => {}); }, [load]);
  useEffect(() => { api.renderCatalog(provider, "image").then(setCatalog).catch(() => setCatalog([])); }, [provider]);
  const working = st?.jobs.some((j) => ACTIVE.includes(j.state)) ?? false;
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => { load().catch(() => {}); }, 3000);
    return () => clearInterval(t);
  }, [working, load]);

  const ids = (st?.candidates ?? []).filter((c) => picked[c.id]).map((c) => c.id);
  useEffect(() => {
    setEst(null);
    if (!ids.length || !model) return;
    let alive = true;
    api.refgen<Est>(dir, "estimate", { ids, provider, model }).then((e) => alive && setEst(e)).catch(() => {});
    return () => { alive = false; };
  }, [dir, provider, model, ids.join(",")]);   // eslint-disable-line react-hooks/exhaustive-deps

  const price = (e: Est) => e.usd != null ? `about $${e.usd.toFixed(2)}${e.kie_credits_est ? ` (${e.kie_credits_est} Kie credits)` : ""}` : "a price this model doesn't publish";
  const make = async () => {
    if (!est) return;
    const ok = await ask(`Make ${ids.length} picture${ids.length === 1 ? "" : "s"} with ${est.title}?\n\nCost: ${price(est)}.${est.basis ? `\n${est.basis}.` : ""}\n\nNothing is sent until you press Make. `
      + "You choose which results to use afterwards.", { ok: "Make them" });
    if (!ok) return;
    setBusy(true); setErr("");
    try { await api.refgen(dir, "queue", { ids, provider, model, confirmed: true }); await load(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const act = async (action: "use" | "discard", job: string) => {
    setErr("");
    try { setSt(await api.refgen(dir, action, { job })); if (action === "use") { onChanged(); window.dispatchEvent(new Event("pf-library-changed")); } }
    catch (e) { setErr(errorText(e)); }
  };

  const ready = (st?.jobs ?? []).filter((j) => j.state === "ready" && !j.used);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass library-sheet" role="dialog" aria-label="Make missing pictures" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Make missing pictures</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">These characters, outfits, props and places have no picture of their own, so a model has nothing to look at for them. Each picture is made
          from the prompt the package wrote for it (or built from its notes), on the image model you choose, after you have seen the price. Nothing replaces a reference
          until you press <b>Use this</b>.</p>
        {err && <div className="error-text" role="alert">{err}</div>}
        {!st ? <div className="dim">Loading…</div> : <>
          {st.candidates.length === 0 && <p className="dim">Nothing is missing a picture.</p>}
          {st.candidates.length > 0 && <>
            <div className="seg" role="group" aria-label="Image provider">
              {PROVIDERS.map(([p, label]) => (
                <button key={p} className={provider === p ? "on" : ""} onClick={() => { setProvider(p); setModel(AUTO_IMAGE_MODEL[p]); }}>
                  {label}{keys && !keys[p as keyof KeyStatus] && <span className="dim"> · no key</span>}</button>))}
            </div>
            <ModelPicker catalog={catalog} value={model} onChange={setModel} label="Image model" onRefresh={async () => setCatalog(await api.renderCatalog(provider, "image", true))} />
            {est?.uses && est.uses.length > 1 && <p className="dim">Props and places have no picture to edit, so they use the text-to-image version:
              {" "}{est.uses.map((u) => `${u.count} on ${u.title}`).join(", ")}.</p>}
            <div className="lib-group">
              <h4>Missing ({st.candidates.length})</h4>
              {st.candidates.map((c) => (
                <details key={c.id} className="rg-row">
                  <summary>
                    <label onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} /></label>
                    <b>{c.name}</b> <span className="chip">{KIND[c.kind] ?? c.kind}</span> <span className="dim">{c.reason}</span>
                  </summary>
                  <p className="dim rg-prompt">{c.prompt}</p>
                  <p className="dim">Prompt: {c.prompt_from}.{c.refs.length > 0 && <> Shown for consistency: {c.refs.map((r) => r.path.split("/").pop()).join(", ")}.</>}</p>
                </details>
              ))}
            </div>
            <div className="sheet-actions">
              <span className="dim">{ids.length} selected{est ? ` · ${price(est)}` : ""}</span>
              <div style={{ flex: 1 }} />
              <button className="btn primary" disabled={!ids.length || !est || busy || !!(keys && !keys[provider as keyof KeyStatus])} onClick={make}>
                {busy ? "Sending…" : `Make ${ids.length || ""} picture${ids.length === 1 ? "" : "s"}…`}</button>
            </div>
            {keys && !keys[provider as keyof KeyStatus] && <p className="dim">Add your {PROVIDERS.find((p) => p[0] === provider)?.[1]} key in Settings to use it.</p>}
          </>}
          {(st.jobs.length > 0) && <div className="lib-group">
            <h4>Pictures made{ready.length > 1 && <button className="link" style={{ marginLeft: 10 }} onClick={async () => { for (const j of ready) await act("use", j.id); }}>Use all {ready.length} ready</button>}</h4>
            <div className="rg-grid">
              {st.jobs.map((j) => (
                <div key={j.id} className={`rg-card ${j.used ? "used" : ""}`}>
                  {j.state === "ready" && j.output ? <img src={api.mediaUrl(`${dir}/${j.output}`)} alt={`${j.asset_name}`} loading="lazy" />
                    : <div className="rg-wait">{ACTIVE.includes(j.state) ? <span className="spin" /> : <I.Alert size={16} />}</div>}
                  <div className="rg-meta"><b>{j.asset_name}</b>
                    <span className="dim">{j.used ? "In use" : STATE[j.state] ?? j.state}{j.cost ? ` · ${j.cost}${j.cost_unit === "credits" ? " credits" : ""}` : ""}</span>
                    {j.error && <span className="error-text">{j.error}</span>}</div>
                  <div className="rg-actions">
                    {j.state === "ready" && !j.used && <button className="btn sm primary" onClick={() => act("use", j.id)}>Use this</button>}
                    {!ACTIVE.includes(j.state) && !j.used && <button className="btn sm ghost" onClick={() => act("discard", j.id)}>Discard</button>}
                  </div>
                </div>
              ))}
            </div>
          </div>}
        </>}
      </div>
    </div>
  );
}
