import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, type Overlay } from "./api";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { barBox, drag, laneAt, packLanes, restack, seekInto, SNAP_PX, timeAtX, type Drag } from "./laneMath";
import "./lanes.css";

export const LANE_H = 22;

const KIND_GLYPH: Record<string, string> = { text: "T", image: "▣", svg: "▣", fill: "■", shape: "◆", icon: "★" };
const labelOf = (o: Overlay) => o.name || o.text || o.file?.split(/[\\/]/).pop() || (o.kind === "fill" ? "Colour backdrop" : o.kind === "shape" ? "Shape" : o.kind === "icon" ? "Icon" : "Picture");
const clock = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;

/** How many lanes the layers need; the timeline uses it to size its scroll area. */
export function laneCount(items: Overlay[]): number {
  const placed = items.filter((o) => o.placed && o.start != null && o.end != null);
  return placed.length ? Math.max(...Object.values(packLanes(placed.map((o) => ({ id: o.id, start: o.start!, end: o.end! })), items.map((o) => o.id)))) + 1 : 0;
}

/** One layer as a bar: drag to move, drag an edge to trim, the eye hides it, arrow keys nudge it. `live` is what a drag in progress looks like. */
export function LayerBar({ o, lane, pps, selected, live, onSelect, onToggle, onPointer, onNudge, onLane }: {
  o: Overlay; lane: number; pps: number; selected: boolean; live?: { start: number; end: number; dy?: number };
  onSelect: () => void; onToggle: () => void; onPointer: (kind: Drag, e: React.PointerEvent) => void; onNudge: (dt: number) => void; onLane?: (dir: -1 | 1) => void;
}) {
  const span = { start: live?.start ?? o.start!, end: live?.end ?? o.end!, keys: o.keys };
  const b = barBox(span, pps);
  const name = labelOf(o);
  return (
    <div role="group" aria-label={`Layer ${name}, ${clock(span.start)} to ${clock(span.end)}${o.enabled ? "" : ", hidden"}`}
         className={["lane-bar", `k-${o.kind}`, selected && "sel", !o.enabled && "off", live && "dragging"].filter(Boolean).join(" ")}
         style={{ left: b.left, width: b.width, top: lane * LANE_H + (live?.dy ?? 0), ...(live ? { zIndex: 5 } : {}) }}
         onClick={(e) => { e.stopPropagation(); onSelect(); }}>
      <i className="lane-edge l" onPointerDown={(e) => onPointer("trim-start", e)} title="Drag to trim the start" />
      <button className="lane-eye" onClick={(e) => { e.stopPropagation(); onToggle(); }} aria-pressed={o.enabled}
              aria-label={o.enabled ? `Hide ${name}` : `Show ${name}`} title={o.enabled ? "Hide this layer" : "Show this layer"}>{o.enabled ? "●" : "○"}</button>
      <span className="lane-body" tabIndex={0} onPointerDown={(e) => onPointer("move", e)} title={`${name} · ${clock(span.start)} – ${clock(span.end)} · drag to move (sideways in time, up or down to put it in front of or behind another layer); arrow keys nudge; Up and Down change the lane`}
            onKeyDown={(e) => {
              const step = e.shiftKey ? 1 : 0.1;
              if (e.key === "ArrowLeft") { e.preventDefault(); onNudge(-step); } else if (e.key === "ArrowRight") { e.preventDefault(); onNudge(step); }
              else if (e.key === "ArrowUp") { e.preventDefault(); onLane?.(-1); } else if (e.key === "ArrowDown") { e.preventDefault(); onLane?.(1); }
              else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); }
            }}>
        <b aria-hidden>{KIND_GLYPH[o.kind] ?? "▣"}</b> {name}
      </span>
      {b.keys.map((k, i) => <u key={i} className="lane-key" style={{ left: k }} title="Keyframe" aria-hidden />)}
      <i className="lane-edge r" onPointerDown={(e) => onPointer("trim-end", e)} title="Drag to trim the end" />
    </div>
  );
}

/** The layers as lanes above the shots, Premiere style. Reads and writes through the same engine calls as the Layers panel and tells it (and the player) when something changed. */
export function LayerLanes({ dir, pps, duration, selected, onSelect, snap, top, onCount, time, onSeek }: {
  dir: string; pps: number; duration: number; selected: string | null; onSelect: (id: string | null) => void; snap: number[]; top: number; onCount?: (lanes: number) => void;
  time?: number; onSeek?: (t: number) => void;
}) {
  const [items, setItems] = useState<Overlay[]>([]);
  const [err, setErr] = useState("");
  const [live, setLive] = useState<{ id: string; start: number; end: number; dy: number } | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; t: number } | null>(null);          // the add menu: at the pointer (right-click) or at the playhead (the button)
  const [hint, setHint] = useState("");
  const rowRef = useRef<HTMLDivElement>(null);
  const say = (t: string) => { setHint(t); window.setTimeout(() => setHint(""), 3500); };
  const load = useCallback(() => api.overlays(dir, "list").then((r) => setItems(r ?? [])).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); window.addEventListener("pf-overlays-changed", load); return () => window.removeEventListener("pf-overlays-changed", load); }, [load]);

  const placed = useMemo(() => items.filter((o) => o.placed && o.start != null && o.end != null), [items]);
  const order = useMemo(() => items.map((o) => o.id), [items]);                         // drawing order, the last on top: the lanes follow it
  const spans = useMemo(() => placed.map((o) => ({ id: o.id, start: o.start!, end: o.end! })), [placed]);
  const lanes = useMemo(() => packLanes(spans, order), [spans, order]);
  const count = placed.length ? Math.max(...Object.values(lanes)) + 1 : 0;
  useEffect(() => { onCount?.(count); }, [count, onCount]);

  const save = async (id: string, patch: Record<string, unknown>) => {
    setErr("");
    try { setItems((await api.overlays(dir, "update", { id, ...patch })) ?? []); window.dispatchEvent(new Event("pf-overlays-changed")); }
    catch (e) { setErr(errorText(e)); }
  };
  const pick = (o: Overlay) => {
    onSelect(o.id);
    const t = onSeek && time != null && o.start != null && o.end != null ? seekInto(time, o.start, o.end) : null;      // outside it: go into it, so it is on the player at full strength
    if (t != null) onSeek!(t);
  };
  const begin = (o: Overlay, kind: Drag, e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation(); e.preventDefault();
    pick(o);
    const x0 = e.clientX, from = { start: o.start!, end: o.end! }, reach = SNAP_PX / pps;
    const y0 = e.clientY, lane0 = lanes[o.id] ?? 0;
    let last = from, lastY = e.clientY;
    const move = (ev: PointerEvent) => {
      last = drag(kind, from, (ev.clientX - x0) / pps, duration, ev.altKey ? [] : snap, reach);     // Alt turns snapping off
      lastY = ev.clientY;
      const dy = kind === "move" ? Math.max(-lane0 * LANE_H, Math.min((Math.max(1, count) - 1 - lane0) * LANE_H, ev.clientY - y0)) : 0;     // up and down only while moving, and only through the lanes there are
      setLive({ id: o.id, ...last, dy });
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      setLive(null);
      const timeChanged = Math.abs(last.start - from.start) > 0.004 || Math.abs(last.end - from.end) > 0.004;
      const target = kind === "move" ? laneAt(lane0 * LANE_H + LANE_H / 2 + (lastY - y0), LANE_H, count) : lane0;
      void (async () => {
        if (timeChanged) await save(o.id, { start: last.start, end: last.end });
        if (target !== lane0) await restackTo(o, target, timeChanged ? { id: o.id, start: last.start, end: last.end } : undefined);
      })();
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const nudge = (o: Overlay, dt: number) => { const r = drag("move", { start: o.start!, end: o.end! }, dt, duration); void save(o.id, r); };

  // Moving a bar to another lane puts the layer in front of, or behind, the layers it overlaps in time: the lane is the stacking order
  const restackTo = async (o: Overlay, target: number, moved?: { id: string; start: number; end: number }) => {
    const sp = spans.map((x) => (moved && x.id === moved.id ? moved : x));
    const ln = packLanes(sp, order);
    const to = restack(order, sp, ln, o.id, target);
    if (to === null) { say("Nothing overlaps it there, so there is nothing to put it in front of or behind. Layers that don\u2019t overlap can share a lane."); return; }
    setErr("");
    try { setItems((await api.overlays(dir, "reorder", { id: o.id, to })) ?? []); window.dispatchEvent(new Event("pf-overlays-changed")); }
    catch (e) { setErr(errorText(e)); }
  };
  const step = (o: Overlay, dir2: -1 | 1) => void restackTo(o, (lanes[o.id] ?? 0) + dir2);

  // Adding at a time: from the \u201c+ Add layer\u201d button (at the playhead), by right-click (at that spot), or by dropping pictures on the row
  const addAt = async (data: Record<string, unknown>, at: number) => {
    setMenu(null); setErr("");
    try {
      const r = await api.overlays(dir, "add", { start: at, end: Math.min(duration || at + 4, at + 4), ...data });
      setItems(r ?? []); onSelect(r?.[r.length - 1]?.id ?? null); window.dispatchEvent(new Event("pf-overlays-changed"));
    } catch (e) { setErr(errorText(e)); }
  };
  const pictureAt = async (at: number) => { setMenu(null); const f = await open({ filters: [{ name: "Picture", extensions: ["png", "jpg", "jpeg", "webp", "svg"] }] }); if (typeof f === "string") await addAt({ image: f, y: 0.5, width: 0.3, anim: "zoom_in" }, at); };
  const rowTime = (clientX: number) => timeAtX(clientX - (rowRef.current?.getBoundingClientRect().left ?? 0), pps, duration);
  useEffect(() => {                                              // pictures dropped from Explorer onto the row land where they are dropped
    let off: (() => void) | undefined;
    try {
      void getCurrentWebview().onDragDropEvent((ev) => {
        const p = ev.payload as { type: string; paths?: string[]; position?: { x: number; y: number } };
        const el = rowRef.current;
        if (p.type !== "drop" || !p.paths?.length || !p.position || !el) return;
        const r = el.getBoundingClientRect(), x = p.position.x / (window.devicePixelRatio || 1), y = p.position.y / (window.devicePixelRatio || 1);
        if (x < r.left || x > r.right || y < r.top - 6 || y > r.bottom + 6) return;
        const pics = p.paths.filter((f) => /\.(png|jpe?g|webp|svg)$/i.test(f));
        if (!pics.length) { say("Drop pictures (PNG, JPG, WebP or SVG) on the Layers row. Videos and music go in My media."); return; }
        pics.forEach((f, i) => void addAtRef.current({ image: f, y: 0.5, width: 0.3, anim: "zoom_in" }, rowTime(x) + i * 0.5));
      }).then((u) => { off = u; });
    } catch { /* not inside the app window */ }
    return () => off?.();
  }, [pps, duration]);   // eslint-disable-line react-hooks/exhaustive-deps
  const addAtRef = useRef(addAt);
  addAtRef.current = addAt;
  useEffect(() => {                                              // the menu goes away when anything else is pressed
    if (!menu) return;
    const close = () => setMenu(null), key = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(null); };
    window.addEventListener("pointerdown", close); window.addEventListener("keydown", key);
    return () => { window.removeEventListener("pointerdown", close); window.removeEventListener("keydown", key); };
  }, [menu]);

  const unplaced = items.filter((o) => !o.placed);
  const addButton = (
    <button className="lane-add" onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); setMenu({ x: r.left, y: r.bottom + 4, t: Math.max(0, Math.round((time ?? 0) * 10) / 10) }); }}
              title="Add text, a picture or an icon at the playhead. You can also right-click the row to add at that spot, or drop pictures on it.">+ Add layer</button>
  );
  return (
    <div className="tl-lanes" ref={rowRef} style={{ top, height: Math.max(1, count) * LANE_H + 4 }} aria-label="Layers on the timeline"
         onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, t: rowTime(e.clientX) }); }}>
      {placed.map((o) => (
        <LayerBar key={o.id} o={o} lane={lanes[o.id]} pps={pps} selected={o.id === selected} live={live?.id === o.id ? live : undefined}
                  onSelect={() => pick(o)} onToggle={() => save(o.id, { enabled: !o.enabled })} onPointer={(k, e) => begin(o, k, e)} onNudge={(dt) => nudge(o, dt)} onLane={(d) => step(o, d)} />
      ))}
      {!items.length && <span className="lane-empty"><b>Layers go here.</b> Move the playhead, then press <i>+ Layer</i> above (or <kbd>Y</kbd>) to add text, a picture or an icon. It shows as a bar you can drag. {addButton}</span>}
      {placed.length > 0 && <span className="lane-label" aria-hidden="true">Layers</span>}
      {placed.length > 0 && addButton}
      {hint && <span className="lane-hint" role="status">{hint}</span>}
      {menu && <div className="lane-menu" role="menu" style={{ position: "fixed", left: menu.x, top: menu.y }} onPointerDown={(e) => e.stopPropagation()}>
        <span className="lane-menu-head">Add at {clock(menu.t)}</span>
        <button role="menuitem" onClick={() => addAt({ kind: "text", text: "Your text", y: 0.5, anim: "rise" }, menu.t)}>Text</button>
        <button role="menuitem" onClick={() => pictureAt(menu.t)}>Picture…</button>
        <button role="menuitem" onClick={() => addAt({ kind: "icon", icon: "star", x: 0.5, y: 0.5, width: 0.12, color: "#ffd166", anim: "zoom_in" }, menu.t)}>Icon</button>
        <button role="menuitem" onClick={() => addAt({ kind: "shape", shape: "rounded", x: 0.5, y: 0.5, width: 0.25, height: 0.25, color: "#ffd166", anim: "fade" }, menu.t)}>Shape</button>
        <button role="menuitem" onClick={() => addAt({ kind: "fill", color: "#000000", opacity: 0.4, anim: "fade" }, menu.t)}>Colour tint</button>
      </div>}
      {unplaced.length > 0 && <span className="lane-unplaced" title={unplaced.map((o) => `${labelOf(o)}: ${o.reason}`).join("\n")}>{unplaced.length} layer{unplaced.length > 1 ? "s" : ""} without a time</span>}
      {err && <span className="lane-err" role="alert">{err}</span>}
    </div>
  );
}
