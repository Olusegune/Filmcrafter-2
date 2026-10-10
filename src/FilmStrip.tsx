import { useEffect, useRef, useState } from "react";
import { api, errorText, type MakeShot } from "./api";
import { clock, durationFromDrag, insertIndex, layout } from "./stripMath";

/**
 * The film as one strip of shots along time. The same shots as the cards, seen as a timeline: drag a block's right edge to make the shot shorter or longer,
 * drag a block to move it, click to choose it. Changes go straight to the shots, so the cards, the shot list and the studio all agree.
 */
export function FilmStrip({ dir, rd, shots, selected, onSelect, onChanged }: { dir: string; rd: string; shots: MakeShot[]; selected: string | null; onSelect: (id: string) => void; onChanged: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [live, setLive] = useState<{ id: string; seconds: number } | null>(null);
  const [drop, setDrop] = useState<{ id: string; at: number } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, e.contentRect.width - 8)));
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const secs = shots.map((s) => (live?.id === s.id ? live.seconds : s.duration));
  const { blocks, scale, total } = layout(secs, shots.map((s) => s.id), w);
  const url = (s: MakeShot) => { const rel = s.keyframe.chosen ?? s.storyboard.chosen; return rel ? api.mediaUrl(`${rd}/${rel}`) : ""; };

  const resize = (e: React.PointerEvent, s: MakeShot) => {
    e.stopPropagation(); e.preventDefault();
    const x0 = e.clientX, d0 = s.duration;
    const move = (ev: PointerEvent) => setLive({ id: s.id, seconds: durationFromDrag(d0, ev.clientX - x0, scale) });
    const up = async (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      const seconds = durationFromDrag(d0, ev.clientX - x0, scale);
      setLive(null);
      if (seconds !== d0) { try { await api.shots("set", dir, { id: s.id, patch: { generation: { duration: seconds } } }); await api.make("sync", dir); onChanged(); } catch (x) { setErr(errorText(x)); } }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const dragBlock = (e: React.PointerEvent, s: MakeShot) => {
    if ((e.target as HTMLElement).closest(".fs-edge")) return;
    onSelect(s.id);
    const x0 = e.clientX, start = blocks.find((b) => b.id === s.id)!;
    let moved = false;
    const at = (ev: PointerEvent) => insertIndex(blocks, s.id, start.left + start.width / 2 + (ev.clientX - x0));
    const move = (ev: PointerEvent) => { if (Math.abs(ev.clientX - x0) > 6) { moved = true; setDrop({ id: s.id, at: at(ev) }); } };
    const up = async (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      setDrop(null);
      if (!moved) return;
      const from = shots.findIndex((x) => x.id === s.id), to = at(ev);
      if (to === from) return;
      try { await api.shots("move", dir, { id: s.id, delta: to - from }); await api.make("sync", dir); onChanged(); } catch (x) { setErr(errorText(x)); }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const step = Math.max(1, Math.ceil(total / 12));
  const ticks = total > 0 ? Array.from({ length: Math.floor(total / step) + 1 }, (_, i) => i * step) : [];
  const last = blocks[blocks.length - 1];
  const dropLeft = (() => {
    if (!drop || !blocks.length) return 0;
    const rest = blocks.filter((b) => b.id !== drop.id);
    if (drop.at <= 0 || !rest.length) return 0;
    const b = rest[Math.min(drop.at, rest.length) - 1];
    return b.left + b.width + 1;
  })();
  return (
    <div className="fs" ref={box} aria-label="The film as a timeline">
      <div className="fs-ruler" aria-hidden="true">{ticks.map((t) => <span key={t} style={{ left: t * scale }}>{clock(t)}</span>)}<span className="fs-total">{clock(total)} total</span></div>
      <div className="fs-track" style={{ width: last ? last.left + last.width : 0 }}>
        {shots.map((s, i) => {
          const b = blocks[i]; if (!b) return null;
          const pic = url(s);
          return (
            <div key={s.id} className={`fs-block ${selected === s.id ? "on" : ""} ${drop?.id === s.id ? "moving" : ""}`} style={{ left: b.left, width: b.width, backgroundImage: pic ? `url("${pic}")` : undefined }}
                 onPointerDown={(e) => dragBlock(e, s)} role="button" tabIndex={0} aria-label={`${s.id}, ${secs[i]} seconds`}
                 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(s.id); }}>
              <span className="fs-id num">{s.id}</span><span className="fs-len num">{secs[i]}s</span>
              <span className="fs-edge" title="Drag to make the shot shorter or longer" onPointerDown={(e) => resize(e, s)} />
            </div>);
        })}
        {drop && <i className="fs-drop" style={{ left: dropLeft }} />}
      </div>
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}
