import { useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { api, errorText, type ComfyInstallPlan, type EngineEvent } from "./api";
import * as I from "./icons";

/** The facts an install needs to state before anyone presses the button: what, from where, how big, where, and how to undo it. Pure. */
export function installFacts(p: ComfyInstallPlan): { label: string; value: string }[] {
  if (!p.ok || !p.asset) return [];
  return [
    { label: "What", value: `ComfyUI's official portable build${p.gpu ? ` for your ${p.gpu}` : ""}${p.tag ? ` (${p.tag})` : ""}: a folder with its own Python, so nothing else on your computer changes` },
    { label: "From", value: `${p.source}, checked against GitHub's published checksum` },
    { label: "Size", value: `${p.download_gb} GB to download; about ${p.need_gb} GB of room needed${p.free_gb != null ? ` (${p.free_gb} GB free)` : ""}, including space for the models you download next` },
    { label: "Where", value: p.dest },
    { label: "To remove it", value: "delete that folder" },
  ];
}

/** Shown in Settings → ComfyUI when no copy is found: one button that downloads, checks and unpacks ComfyUI, then starts it. */
export function ComfyInstallCard({ onInstalled }: { onInstalled: (startScript: string) => void }) {
  const [plan, setPlan] = useState<ComfyInstallPlan | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [pct, setPct] = useState<number | null>(null);
  useEffect(() => { api.comfyInstall("plan").then(setPlan).catch((e) => setErr(errorText(e))); }, []);
  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => {
      if (e.task === "comfy" && e.stage && typeof e.progress === "number") { setBusy(`${e.stage[0].toUpperCase()}${e.stage.slice(1)}`); setPct(Math.round((e.progress as number) * 100)); }
    });
    return () => { un.then((f) => f()); };
  }, []);
  const go = async () => {
    setErr(""); setBusy("Starting…"); setPct(0);
    try {
      const r = await api.comfyInstall<{ start: string | null }>("install");
      setBusy(""); setPct(null);
      if (r.start) onInstalled(r.start);
    } catch (e) { setErr(errorText(e)); setBusy(""); setPct(null); }
  };
  if (!plan && !err) return <div className="comfy-none dim"><span className="spin sm" /> Looking up the latest ComfyUI…</div>;
  return (
    <div className="comfy-none comfy-install">
      <b>ComfyUI isn't on this computer yet.</b>
      {plan?.installed && <p>It is installed at <span className="num">{plan.path}</span>. Press Start it.
        {plan.start && <> <button className="btn small" disabled={!!busy} onClick={() => onInstalled(plan.start!)}>Start it</button></>}</p>}
      {plan && !plan.installed && plan.ok && <>
        <p>ComfyUI is free and runs on your own graphics card, so renders cost nothing. PULSEFRAME can install it for you, with no terminal and no setup:</p>
        <dl className="ci-facts">{installFacts(plan).map((f) => <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>
        {plan.warnings.map((w) => <p key={w} className="fr-note warn"><I.Alert size={13} /> {w}</p>)}
        {busy ? <div role="status" aria-live="polite">
          <div className="q-bar" role="progressbar" aria-label="Installing ComfyUI" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? 0}><i style={{ width: `${pct ?? 0}%` }} /></div>
          <span className="dim">{busy}{pct != null ? ` · ${pct}%` : ""}. You can keep working; if it is interrupted, press Install again and it carries on.</span></div>
          : <button className="btn primary" onClick={go}>Install ComfyUI ({plan.download_gb} GB download)</button>}
      </>}
      {plan && !plan.installed && !plan.ok && <>
        <p>{plan.reason}</p>
        {plan.manual_url && <button className="btn small" onClick={() => openUrl(plan.manual_url!)}>Open comfy.org/download</button>}
      </>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}
