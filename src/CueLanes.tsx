import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, type Cue, type CueList, type MixSettings } from "./api";

export const CHEAD_H = 26;           // the band's header row
export const CLANE_H = 28;
export const CUE_EVENT = "fc-cues-changed";
export const notifyCues = () => window.dispatchEvent(new Event(CUE_EVENT));

const LANES: { kind: "sfx" | "ambience" | "music"; label: string; colour: string }[] = [
  { kind: "sfx", label: "Effects", colour: "#7fb6e8" }, { kind: "ambience", label: "Ambience", colour: "#7fe0b0" }, { kind: "music", label: "Music", colour: "#c78fe0" },
];

/** The film's planned cues (Sound & Music > Scene sound), kept fresh while the timeline is open. Null until read; empty when the film has no plan. */
export function useCues(dir: string | null): { list: CueList | null; mix: MixSettings | null; reload: () => void } {
  const [list, setList] = useState<CueList | null>(null);
  const [mix, setMix] = useState<MixSettings | null>(null);
  const reload = useCallback(() => {
    if (!dir) return;
    api.filmCues("list", dir).then(setList).catch(() => setList(null));
    api.audioMix<MixSettings>("settings", dir).then(setMix).catch(() => setMix(null));
  }, [dir]);
  useEffect(() => { reload(); window.addEventListener(CUE_EVENT, reload); return () => window.removeEventListener(CUE_EVENT, reload); }, [reload]);
  return { list, mix, reload };
}

/** The lanes that have something in them, in order. */
export const cueLaneKinds = (list: CueList | null): ("sfx" | "ambience" | "music")[] => {
  const have = new Set((list?.cues ?? []).filter((c) => c.approval !== "rejected").map((c) => c.kind));
  return LANES.filter((l) => have.has(l.kind)).map((l) => l.kind);
};

/** Seconds a cue is heard for: what was set, else the whole sound, else (a loop) until its shot or scene ends. */
export const cueSeconds = (c: Cue, anchorEnd: number, anchorStart: number): number => {
  const start = anchorStart + c.start;
  if (c.duration) return c.duration;
  if (c.loop) return Math.max(0.2, anchorEnd - start);
  return c.asset_seconds ?? 2;
};

/**
 * The planned sound under the shots in Edit mode: one lane each for effects, ambience and music (the voices have their own band above). A clip sits where the plan puts it; drag it sideways to
 * move it, click it to change its level, fades, start or whether it is heard. Everything here is non-destructive: no sound file is touched, and a muted cue is only left out of the film.
 */
export function CueLanes({ dir, list, mix, shots, pps, top, view, onChanged }: {
  dir: string; list: CueList; mix: MixSettings | null; shots: { id: string; start: number; end: number }[]; pps: number; top: number; view: [number, number]; onChanged: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const where = useMemo(() => Object.fromEntries(shots.map((s) => [s.id, s])), [shots]);
  const sceneSpan = useMemo(() => {
    const out: Record<number, [number, number]> = {};
    for (const [n, s] of Object.entries(list.scenes)) {
      const bs = s.shots.map((x) => where[x.id]).filter(Boolean);
      if (bs.length) out[Number(n)] = [Math.min(...bs.map((b) => b.start)), Math.max(...bs.map((b) => b.end))];
    }
    return out;
  }, [list, where]);
  const kinds = cueLaneKinds(list);
  const pin = view[0] + 8;
  const anchor = (c: Cue): [number, number] | null => (c.shot ? (where[c.shot] ? [where[c.shot].start, where[c.shot].end] : null) : sceneSpan[c.scene] ?? null);
  const save = async (id: string, d: Record<string, unknown>) => { setErr(""); try { await api.filmCues("update", dir, { id, ...d }); notifyCues(); onChanged(); } catch (e) { setErr(errorText(e)); } };
  const setMix = async (d: Record<string, unknown>) => { try { await api.audioMix("set_settings", dir, d); notifyCues(); } catch (e) { setErr(errorText(e)); } };
  const muted = new Set(mix?.mute_lanes ?? []);
  const count = list.cues.filter((c) => c.approval === "approved").length;
  const flagged = list.cues.filter((c) => c.fresh.length).length;

  return (
    <div className="cl" style={{ top }} aria-label="Planned sound on the timeline">
      <div className="vl-head" style={{ left: pin }}><b>Sound</b><span className="dim">{count} cue{count === 1 ? "" : "s"} in the film{flagged ? ` · ${flagged} may need another look` : ""}</span>
        {err && <span className="error-text" role="alert">{err}</span>}</div>
      {kinds.map((kind) => {
        const lane = LANES.find((l) => l.kind === kind)!;
        return (
          <div key={kind} className={`vl-lane cl-lane ${muted.has(kind) ? "muted" : ""}`} style={{ height: CLANE_H, ["--vc" as string]: lane.colour }}>
            <span className="vl-name cl-name" style={{ left: pin }}><i className="vl-dot" /><b>{lane.label}</b>
              <button className={`cl-m ${muted.has(kind) ? "on" : ""}`} aria-pressed={muted.has(kind)} aria-label={`Leave ${lane.label} out of the film`} title="Mute: leave this lane out of the film and the preview"
                      onClick={(e) => { e.stopPropagation(); void setMix({ mute_lanes: muted.has(kind) ? [...muted].filter((x) => x !== kind) : [...muted, kind] }); }}>M</button></span>
            {list.cues.filter((c) => c.kind === kind && c.approval !== "rejected").map((c) => {
              const a = anchor(c);
              if (!a) return null;
              const secs = cueSeconds(c, a[1], a[0]);
              const left = (a[0] + c.start) * pps;
              const w = Math.max(10, secs * pps);
              if (left + w < view[0] - 200 || left > view[1] + 200) return null;
              return <Clip key={c.id} dir={dir} c={c} left={left} width={w} lane={lane.colour} pps={pps} open={open === c.id} onOpen={() => setOpen(open === c.id ? null : c.id)} onSave={(d) => save(c.id, d)} />;
            })}
          </div>);
      })}
    </div>
  );
}

function Clip({ dir, c, left, width, lane, pps, open, onOpen, onSave }: { dir: string; c: Cue; left: number; width: number; lane: string; pps: number; open: boolean; onOpen: () => void;
  onSave: (d: Record<string, unknown>) => void }) {
  const [dx, setDx] = useState(0);
  const drag = useRef<{ x: number; moved: boolean } | null>(null);
  const [g, setG] = useState({ gain_db: String(c.gain_db), fade_in: String(c.fade_in), fade_out: String(c.fade_out), start: c.start.toFixed(2) });
  useEffect(() => setG({ gain_db: String(c.gain_db), fade_in: String(c.fade_in), fade_out: String(c.fade_out), start: c.start.toFixed(2) }), [c]);
  const down = (e: React.PointerEvent) => { e.stopPropagation(); (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); drag.current = { x: e.clientX, moved: false }; };
  const move = (e: React.PointerEvent) => { const d = drag.current; if (!d) return; const m = e.clientX - d.x; if (Math.abs(m) > 3) d.moved = true; if (d.moved) setDx(Math.max(m, -c.start * pps)); };      // never before the start of its shot
  const up = (e: React.PointerEvent) => {
    const d = drag.current; drag.current = null;
    if (!d) return;
    if (!d.moved) { setDx(0); onOpen(); return; }
    const start = Math.max(0, Math.round((c.start + (e.clientX - d.x) / pps) * 10) / 10);          // to a tenth of a second
    setDx(0);
    if (start !== c.start) onSave({ start });
  };
  const bad = c.fresh.length > 0;
  return (
    <>
      <button className={`vl-clip cl-clip ${c.muted ? "off" : ""} ${bad ? "stale" : ""} ${c.needs_sound ? "gap" : "rec"}`} style={{ left: left + dx, width, ["--vc" as string]: lane }} onPointerDown={down} onPointerMove={move} onPointerUp={up}
              title={`${c.asset_name ?? c.plan?.description ?? "A sound"}: from ${c.start.toFixed(1)} s, ${c.gain_db} dB${c.muted ? ", left out of the film" : ""}${bad ? `. ${c.fresh[0].why}` : ""}. Drag to move, click to adjust.`}
              aria-label={`${c.asset_name ?? "Planned sound"}, ${c.kind}${c.muted ? ", muted" : ""}${bad ? ", may need another look" : ""}`}>
        <span className="vl-text">{c.asset_name ?? c.plan?.description ?? "needs a sound"}</span>
      </button>
      {open && <div className="cl-pop glass" style={{ left: left + Math.min(width, 40) }} onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Adjust ${c.asset_name ?? "this cue"}`}>
        <b>{c.asset_name ?? c.plan?.description ?? "Planned sound"}</b>
        {c.asset_file && <audio controls preload="none" src={api.mediaUrl(`${dir}/${c.asset_file}`)} aria-label="Hear it" />}
        <div className="cl-grid">
          {(["gain_db", "fade_in", "fade_out", "start"] as const).map((k) => <label key={k}>{{ gain_db: "Level (dB)", fade_in: "Fade in (s)", fade_out: "Fade out (s)", start: "Starts (s into shot)" }[k]}
            <input value={g[k]} inputMode="decimal" onChange={(e) => setG({ ...g, [k]: e.target.value })} onKeyDown={(e) => e.key === "Enter" && onSave({ [k]: g[k] })} onBlur={() => g[k] !== String(k === "start" ? c.start.toFixed(2) : c[k]) && onSave({ [k]: g[k] })} /></label>)}
        </div>
        <div className="cl-row"><button className="btn sm" aria-pressed={!!c.muted} onClick={() => onSave({ muted: !c.muted })}>{c.muted ? "Put it back in the film" : "Leave it out of the film"}</button>
          <button className="link" onClick={onOpen}>Close</button></div>
        {bad && <p className="ss-warn">{c.fresh[0].why}</p>}
        <p className="dim">Nothing here changes the sound file.</p>
      </div>}
    </>
  );
}
