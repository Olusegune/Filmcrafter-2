import { useCallback, useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { api, errorText, type UpdateInfo } from "./api";
import * as I from "./icons";

const AUTO = "pf-auto-update", LAST = "pf-update-last", FOUND = "pf-update-found";
const DAY = 24 * 3600 * 1000;
const get = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const put = (k: string, v: string | null) => { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* optional */ } };
export const autoChecks = () => get(AUTO) === "1";

/** What a check found, in words. Pure, so it can be tested. */
export function updateText(u: UpdateInfo): { tone: "ok" | "new" | "warn"; text: string } {
  if (u.status === "update") return { tone: "new", text: `PULSEFRAME ${u.latest} is available (you have ${u.current}).` };
  if (u.status === "up_to_date") return { tone: "ok", text: `You have the latest version (${u.current}).` };
  if (u.status === "offline") return { tone: "warn", text: "Couldn't reach the update list. Check your internet connection and try again." };
  return { tone: "warn", text: "The update list isn't available to this app right now. Open the releases page to look for a newer version yourself." };
}

/** Settings: the version, a button to check, and a switch for one automatic check a day (off by default: a check tells GitHub this computer asked). */
export function UpdateRow() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [auto, setAuto] = useState(autoChecks());
  const run = useCallback(async () => {
    setBusy(true); setErr("");
    try { const u = await api.checkUpdate(); setInfo(u); put(LAST, String(Date.now())); put(FOUND, u.status === "update" ? JSON.stringify(u) : null); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }, []);
  const t = info ? updateText(info) : null;
  return (
    <div className="field upd">
      <label style={{ display: "flex", justifyContent: "space-between" }}><span>Updates <span className="opt">PULSEFRAME checks the public release list on GitHub</span></span></label>
      <div className="upd-row">
        <button className="btn" onClick={run} disabled={busy}><I.Refresh size={14} /> {busy ? "Checking…" : "Check for updates"}</button>
        {info && info.status !== "offline" && <button className="btn ghost" onClick={() => openUrl(info.url).catch(() => {})}>{info.status === "update" ? "Open the download page" : "Open the releases page"}</button>}
        <label className="ov-check upd-auto" title="Asks once a day. GitHub can see that this computer asked; nothing else is sent."><input type="checkbox" checked={auto}
               onChange={(e) => { setAuto(e.target.checked); put(AUTO, e.target.checked ? "1" : "0"); }} /> Check once a day</label>
      </div>
      {t && <p className={`upd-msg ${t.tone}`}>{t.text}{info?.status === "update" && info.notes ? <span className="dim"> {info.notes}</span> : null}</p>}
      {err && <p className="error-text">{err}</p>}
    </div>
  );
}

/** Home: a small amber pill when a newer version is known (from the daily check, if it is switched on, or a check made in Settings). */
export function UpdatePill() {
  const [u, setU] = useState<UpdateInfo | null>(() => { try { const v = JSON.parse(get(FOUND) || "null"); return v && v.status === "update" ? v : null; } catch { return null; } });
  useEffect(() => {
    if (!autoChecks()) return;
    const last = Number(get(LAST)) || 0;
    if (Date.now() - last < DAY) return;
    api.checkUpdate().then((r) => { put(LAST, String(Date.now())); put(FOUND, r.status === "update" ? JSON.stringify(r) : null); setU(r.status === "update" ? r : null); }).catch(() => {});
  }, []);
  if (!u) return null;
  return <button className="upd-pill" onClick={() => openUrl(u.url).catch(() => {})} title={u.notes || "Open the download page"}><I.Rocket size={13} /> Update {u.latest} available</button>;
}
