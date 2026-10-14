import { useCallback, useEffect, useState } from "react";
import { api, errorText, type RegistryRefresh, type RegistryStatus } from "./api";

const NAMES: Record<string, string> = { elevenlabs: "ElevenLabs voices", kie: "Kie.ai models", openrouter: "OpenRouter writing models" };
const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "never");

/**
 * Settings: when each provider's list of models was last read. Refreshing reads the providers' own lists (nothing is sent but the request, nothing is spent) and keeps them on this computer, apart from
 * the app and from every film. A list that cannot be read changes nothing. The models FilmCrafter knows by heart are always there.
 */
export function ModelsRow() {
  const [st, setSt] = useState<RegistryStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<RegistryRefresh | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => { api.registry().then(setSt).catch((e) => setErr(errorText(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const refresh = async () => { setBusy(true); setErr(""); try { setRes(await api.registry<RegistryRefresh>("refresh")); load(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  return (
    <div className="field upd">
      <label style={{ display: "flex", justifyContent: "space-between" }}><span>AI models <span className="opt">which models each provider offers, kept apart from the app</span></span></label>
      <div className="upd-row"><button className="btn" onClick={() => void refresh()} disabled={busy}>{busy ? "Reading the lists…" : "Refresh the model lists"}</button>
        <span className="dim">{st ? `${st.models} models known` : ""}</span></div>
      {st && <ul className="mr-list">{Object.entries(st.providers).map(([p, v]) => <li key={p}><b>{NAMES[p] ?? p}</b> <span className="dim">last read {when(v.refreshed)}{v.stale ? " · worth refreshing" : ""}</span>
        {v.last_error && <span className="error-text"> could not be read last time: {v.last_error}</span>}</li>)}</ul>}
      {res && <p className="dim">{Object.entries(res.results).map(([p, r]) => `${NAMES[p] ?? p}: ${r.ok ? `${r.models} models` : `not changed (${r.error})`}`).join(" · ")}. {res.kept}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}
