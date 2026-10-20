import { useCallback, useEffect, useMemo, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, type CleanupItem, type CleanupScan } from "./api";
import { ask } from "./ask";
import * as I from "./icons";
import { readTileSize, sizeText as size, stepIndex, TILE_MIN, writeTileSize, type TileSize } from "./cleanupView";

/**
 * Clean up: the videos and pictures that nothing uses any more (older takes, keyframe versions you did not pick, leftovers), with a preview of each.
 * Removing moves them to a trash folder inside the project, where they can be restored; only "Empty trash" deletes them for good.
 */
export function CleanupSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged: () => void }) {
  const [scan, setScan] = useState<CleanupScan | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [tile, setTileState] = useState<TileSize>(() => readTileSize());
  const setTile = (t: TileSize) => { setTileState(t); writeTileSize(t); };
  const [viewing, setViewing] = useState<string | null>(null);        // the file shown large, by path

  const apply = useCallback((s: CleanupScan, keep?: Set<string>) => {
    setScan(s);
    setPicked(new Set(s.items.filter((i) => !keep || keep.has(i.path)).map((i) => i.path)));
  }, []);
  const load = useCallback(() => api.cleanup(dir, "scan").then((s) => apply(s)).catch((e) => setErr(errorText(e))), [dir, apply]);
  useEffect(() => { load(); }, [load]);

  const items = scan?.items ?? [];
  const chosen = useMemo(() => items.filter((i) => picked.has(i.path)), [items, picked]);
  const chosenBytes = chosen.reduce((n, i) => n + i.size, 0);
  const toggle = (p: string) => setPicked((s) => { const n = new Set(s); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  const url = (i: CleanupItem) => api.mediaUrl(`${dir}/${i.path}`);

  const run = async (what: string, fn: () => Promise<string>) => {
    setBusy(what); setErr(""); setNote("");
    try { setNote(await fn()); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const remove = async () => {
    if (!chosen.length) return;
    if (!await ask(`Move ${chosen.length} file${chosen.length === 1 ? "" : "s"} (${size(chosenBytes)}) to this project's trash? You can restore them until you empty the trash.`, { ok: "Move to trash" })) return;
    await run("remove", async () => {
      const r = await api.cleanup<{ moved: number; bytes: number; skipped: { path: string; why: string }[]; scan: CleanupScan }>(dir, "discard", { paths: chosen.map((i) => i.path) });
      apply(r.scan);
      return `Moved ${r.moved} file${r.moved === 1 ? "" : "s"} (${size(r.bytes)}) to the trash.${r.skipped.length ? ` ${r.skipped.length} left alone (${r.skipped[0].why}).` : ""}`;
    });
  };
  const restore = () => run("restore", async () => {
    const r = await api.cleanup<{ restored: number; left: number; scan: CleanupScan }>(dir, "restore");
    apply(r.scan);
    return `Restored ${r.restored} file${r.restored === 1 ? "" : "s"}.${r.left ? ` ${r.left} stayed in the trash because something new is in their place.` : ""}`;
  });
  const empty = async () => {
    if (!scan?.trash.files) return;
    if (!await ask(`Delete the ${scan.trash.files} file${scan.trash.files === 1 ? "" : "s"} in the trash (${size(scan.trash.bytes)}) for good? This cannot be undone.`, { ok: "Delete for good", danger: true })) return;
    await run("empty", async () => {
      const r = await api.cleanup<{ deleted: number; bytes: number; scan: CleanupScan }>(dir, "empty");
      apply(r.scan, picked);
      return `Deleted ${r.deleted} file${r.deleted === 1 ? "" : "s"} (${size(r.bytes)}).`;
    });
  };

  const groups: [string, string, CleanupItem[]][] = [["video", "Videos", items.filter((i) => i.kind === "video")], ["image", "Pictures", items.filter((i) => i.kind === "image")], ["audio", "Audio", items.filter((i) => i.kind === "audio")]];
  return (
    <Sheet label="Clean up" className="cleanup" onDismiss={onClose}>
        <div className="vs-head"><h2>Clean up</h2><div style={{ flex: 1 }} />
          <div className="cl-sizes" role="group" aria-label="Picture size">{(["small", "medium", "large"] as TileSize[]).map((t) => <button key={t} className={tile === t ? "on" : ""} aria-pressed={tile === t} onClick={() => setTile(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
          <button className="btn ghost small" onClick={load} disabled={!!busy}>Refresh</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Videos and pictures that nothing uses any more: older takes and keyframe versions you did not pick. Anything in the film, an approved
          keyframe, a reference or something made in the last ten minutes is never listed. Removing moves files to a trash folder in this project, so you can restore them.</p>
        {!scan && !err && <p className="dim">Looking…</p>}
        {scan?.rendering ? <p className="si-problems">A render is running. Wait for it to finish before removing anything.</p> : null}
        {scan && !items.length && <p className="dim">Nothing to clean up. {scan.kept} file{scan.kept === 1 ? " is" : "s are"} in use.</p>}
        {groups.filter(([, , g]) => g.length).map(([k, label, g]) => (
          <section key={k} className="cl-group">
            <div className="cl-head"><b>{label}</b> <span className="dim">{g.length} · {size(g.reduce((n, i) => n + i.size, 0))}</span><div style={{ flex: 1 }} />
              <button className="link" onClick={() => setPicked((s) => { const n = new Set(s); g.forEach((i) => n.add(i.path)); return n; })}>All</button>
              <button className="link" onClick={() => setPicked((s) => { const n = new Set(s); g.forEach((i) => n.delete(i.path)); return n; })}>None</button></div>
            <div className="cl-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${TILE_MIN[tile]}px, 1fr))` }}>
              {g.map((i) => (
                <div key={`${i.path}|${i.name}`} className={`cl-card ${picked.has(i.path) ? "on" : "off"}`}>
                  <button className="cl-thumb" onClick={() => setViewing(i.path)} aria-label={`Look at ${i.name} larger`} title="Look at it larger">
                    {i.kind === "video" ? <video src={`${url(i)}#t=0.3`} muted preload="metadata" playsInline /> : <img src={url(i)} alt="" loading="lazy" />}
                    <span className="cl-zoom" aria-hidden="true">⤢</span>
                  </button>
                  <label className="cl-check" title={picked.has(i.path) ? "Will be moved to the trash" : "Will be kept"}>
                    <input type="checkbox" aria-label={`Select ${i.name}`} checked={picked.has(i.path)} onChange={() => toggle(i.path)} /></label>
                  <div className="cl-meta" title={i.path}>
                    <span className="cl-top"><b className="num">{i.shot ?? "unlisted"}</b><span className="dim num">{size(i.size)}</span></span>
                    <span className="cl-model dim">{i.model ?? i.what}</span>
                  </div>
                </div>))}
            </div>
          </section>))}
        {viewing && <Viewer items={items} path={viewing} picked={picked} url={url} onToggle={toggle} onMove={setViewing} onClose={() => setViewing(null)} />}
        {err && <p className="error-text" role="alert">{err}</p>}
        {note && <p className="dim" role="status">{note}</p>}
        {scan && items.length > 0 && <div className="cl-actions">
          <span>{chosen.length} chosen · {size(chosenBytes)}</span><div style={{ flex: 1 }} />
          <button className="btn primary" disabled={!chosen.length || !!busy || !!scan.rendering} onClick={remove}><I.Trash size={14} /> {busy === "remove" ? "Moving…" : "Move to trash"}</button></div>}
        {scan && scan.trash.files > 0 && <div className="cl-trash">
          <I.Trash size={15} /> <span><b>Trash</b> {scan.trash.files} file{scan.trash.files === 1 ? "" : "s"} · {size(scan.trash.bytes)}</span><div style={{ flex: 1 }} />
          <button className="btn small" disabled={!!busy} onClick={restore}>Restore all</button>
          <button className="btn small ghost danger" disabled={!!busy} onClick={empty}>Empty trash…</button></div>}
    </Sheet>
  );
}

/** One file, large: a video plays with its controls, a picture fills the frame. Arrow keys move through the list; the person decides to keep or remove it here. */
function Viewer({ items, path, picked, url, onToggle, onMove, onClose }: { items: CleanupItem[]; path: string; picked: Set<string>; url: (i: CleanupItem) => string; onToggle: (p: string) => void; onMove: (p: string) => void; onClose: () => void }) {
  const idx = items.findIndex((i) => i.path === path);
  const item = items[idx];
  const go = (d: 1 | -1) => { const n = stepIndex(idx, d, items.length); if (n >= 0) onMove(items[n].path); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      else if (e.key === "ArrowRight") { e.stopPropagation(); go(1); }
      else if (e.key === "ArrowLeft") { e.stopPropagation(); go(-1); }
    };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  });   // eslint-disable-line react-hooks/exhaustive-deps
  if (!item) return null;
  const on = picked.has(item.path);
  return (
    <div className="overlay cl-viewer" onClick={(e) => { e.stopPropagation(); onClose(); }}>
      <div className="cl-view" role="dialog" aria-label={`${item.shot ?? "File"} larger`} onClick={(e) => e.stopPropagation()}>
        <div className="cl-view-media">{item.kind === "video" ? <video key={item.path} src={url(item)} controls autoPlay muted loop playsInline /> : item.kind === "image" ? <img src={url(item)} alt="" /> : <p className="dim">No preview for this file.</p>}</div>
        <div className="cl-view-bar">
          <button className="btn ghost small" onClick={() => go(-1)} aria-label="Previous file">← Previous</button>
          <span className="cl-view-title"><b className="num">{item.shot ?? "unlisted"}</b> <span className="dim">{item.model ?? item.what} · {size(item.size)} · {idx + 1} of {items.length}</span></span>
          <button className="btn ghost small" onClick={() => go(1)} aria-label="Next file">Next →</button>
        </div>
        <div className="cl-view-actions">
          <button className={`btn ${on ? "" : "primary"}`} onClick={() => onToggle(item.path)}>{on ? "Keep this one instead" : "Move this one to the trash"}</button>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
