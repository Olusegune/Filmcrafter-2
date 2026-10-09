import { useCallback, useEffect, useState } from "react";
import { api, errorText, type CameraGroup, type CameraVocab, type LookSuggestion, type ShotCamera } from "./api";
import { PanelHead } from "./Dock";
import * as I from "./icons";

const ORDER: CameraGroup[] = ["size", "angle", "movement", "lens", "lighting", "focus", "energy"];
const ICON: Record<CameraGroup, React.ReactNode> = {
  size: <I.FrameSize size={13} />, angle: <I.Angle size={13} />, movement: <I.Move size={13} />, lens: <I.Lens size={13} />,
  lighting: <I.Light size={13} />, focus: <I.Focus size={13} />, energy: <I.Bolt size={13} />,
};
/** What the feeling of the shot suggests for its camera and light, with one button to use it. Free; a choice already made is never offered again. */
export function LookSuggest({ s, more, busy, onUse, onUseAll }: { s: LookSuggestion; more: number; busy: boolean; onUse: () => void; onUseAll: () => void }) {
  return (
    <div className="cam-suggest" role="note">
      <p><b>Suggested for “{s.emotion}”</b> <span className="dim">{s.why}</span></p>
      <ul>{s.proposals.map((p) => <li key={p.group}><span className="dim">{p.group === "movement" ? "Movement" : p.group[0].toUpperCase() + p.group.slice(1)}</span> {p.label}</li>)}</ul>
      <div className="cam-actions">
        <button className="btn small" disabled={busy} onClick={onUse}>Use these</button>
        {more > 0 && <button className="link" disabled={busy} onClick={onUseAll}>Use the suggestions for all {more + 1} shots with a feeling</button>}
      </div>
    </div>);
}

let vocabPromise: Promise<CameraVocab> | null = null;       // the same list for every shot: asked for once
/** Suggestions for the whole project are asked for once, not on every click from shot to shot: kept for half a minute, and dropped as soon as a camera choice is made here. */
let looksCache: { dir: string; at: number; p: Promise<LookSuggestion[]> } | null = null;
const loadLooksFor = (dir: string, force = false) => {
  if (force || !looksCache || looksCache.dir !== dir || Date.now() - looksCache.at > 30_000) {
    looksCache = { dir, at: Date.now(), p: api.camera<{ shots: LookSuggestion[] }>(dir, "suggest").then((r) => r.shots ?? []).catch(() => []) };
  }
  return looksCache.p;
};
export const forgetLooks = () => { looksCache = null; };
const loadVocab = (dir: string) => (vocabPromise ??= api.camera<CameraVocab>(dir, "vocab").catch((e) => { vocabPromise = null; throw e; }));

/**
 * Camera and lighting for one shot, as named choices: shot size, angle, movement, lens, lighting, focus (including rack focus) and
 * energy. Each starts on "the Director's choice" (showing which term the Director's wording already names); picking a term writes
 * that wording into this shot's prompt in place of the Director's. Nothing is rendered or billed by choosing.
 */
export function ShotCamera({ dir, shotId, sceneShotIds, onChanged }: { dir: string; shotId: string; sceneShotIds: string[]; onChanged?: () => void }) {
  const [vocab, setVocab] = useState<CameraVocab | null>(null);
  const [cam, setCam] = useState<ShotCamera | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [looks, setLooks] = useState<LookSuggestion[]>([]);
  const [busy, setBusy] = useState(false);
  const loadLooks = useCallback((force = false) => loadLooksFor(dir, force).then(setLooks), [dir]);
  const load = useCallback(async () => { setCam(await api.camera<ShotCamera>(dir, "get", { shot: shotId })); }, [dir, shotId]);
  useEffect(() => {
    setCam(null); setNote(""); setErr("");
    loadVocab(dir).then(setVocab).catch((e) => setErr(errorText(e)));
    load().catch((e) => setErr(errorText(e)));
    loadLooks();
  }, [dir, load, loadLooks]);
  const useLooks = async (ids: string[]) => {
    setBusy(true); setErr(""); setNote("");
    try {
      await api.camera(dir, "suggest_apply", { shots: ids });
      await load(); await loadLooks(true); onChanged?.();
      setNote(ids.length > 1 ? `Chosen for ${ids.length} shots. Render them again to see it.` : "Chosen. Render this shot again to see it.");
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };

  const choose = async (group: CameraGroup, id: string, shots: string[] = [shotId]) => {
    setErr(""); setNote("");
    try {
      const r = await api.camera<{ shot: ShotCamera }>(dir, "set", { shots, picks: { [group]: id } });
      if (shots.includes(shotId)) setCam(r.shot);
      forgetLooks(); loadLooks(true);
      if (shots.length > 1) setNote(`Applied to ${shots.length} shots of this scene.`);
      onChanged?.();
    } catch (e) { setErr(errorText(e)); }
  };
  const reset = async () => {
    setErr(""); setNote("");
    try { await api.camera(dir, "reset", { shots: [shotId] }); await load(); forgetLooks(); loadLooks(true); onChanged?.(); } catch (e) { setErr(errorText(e)); }
  };
  if (!vocab || !cam) return err ? <section className="panel"><PanelHead icon={<I.Camera size={18} />} title="Camera & lighting" /><p className="error-text" role="alert">{err}</p></section> : null;

  const picked = Object.keys(cam.picked).length;
  const termLabel = (g: CameraGroup, id: string | null | undefined) => vocab[g].terms.find((t) => t.id === id)?.label;
  return (
    <details className="panel cam-panel" open={picked > 0 || looks.some((l) => l.shot === shotId)}>
      <summary><PanelHead icon={<I.Camera size={18} />} title="Camera & lighting" tag={picked ? `${picked} changed` : "Free"} tone={picked ? "warn" : "free"} right={<I.Chevron size={16} />} /></summary>
      <p className="dim">Pick named choices for this shot. They replace the Director's wording for that one thing in the prompt; the Director's plan is not changed.
        Render the shot again to see them.</p>
      {(() => { const mine = looks.find((l) => l.shot === shotId); return mine ? <LookSuggest s={mine} more={looks.length - 1} busy={busy} onUse={() => useLooks([shotId])} onUseAll={() => useLooks(looks.map((l) => l.shot))} /> : null; })()}
      <div className="cam-grid">
        {ORDER.map((g) => {
          const det = cam.detected[g];
          const own = cam.picked[g] ?? "";
          const shown = g === "energy" ? cam.director.energy : termLabel(g, det);
          return (
            <label key={g}><span className="cam-lbl">{ICON[g]} {vocab[g].label}</span>
              <select value={own} aria-label={vocab[g].label} onChange={(e) => choose(g, e.target.value)}>
                <option value="">{shown ? `Director: ${shown}` : "Director's choice"}</option>
                {vocab[g].terms.map((t) => <option key={t.id} value={t.id}>{t.label}{t.video_only ? " (video)" : ""}</option>)}
              </select>
            </label>);
        })}
      </div>
      {cam.changed_since_take && <p className="fr-note warn">The camera changed after this shot's last take: render it again to see the change.</p>}
      {(cam.effective.framing || cam.effective.movement) && <p className="dim cam-now">Sent as: {[cam.effective.framing, cam.effective.lens, cam.effective.movement].filter(Boolean).join(" · ")}</p>}
      <div className="cam-actions">
        <button className="link" title="Read the mood of every shot and plan the light to match" onClick={() => window.dispatchEvent(new Event("pf-open-lighting"))}>Plan the light from the mood…</button>
        {picked > 0 && <button className="link" onClick={reset}>Back to the Director's choices</button>}
        {picked > 0 && sceneShotIds.length > 1 && <button className="link" title="Give every shot of this scene the same choices as this one"
          onClick={async () => { for (const g of ORDER) { const v = cam.picked[g]; if (v) await choose(g, v, sceneShotIds); } }}>Apply these to every shot in this scene</button>}
      </div>
      {note && <p className="dim">{note}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </details>
  );
}
