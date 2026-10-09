import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorText, type BoardShot, type Library, type RefItem } from "./api";
import { PanelHead } from "./Dock";
import * as I from "./icons";

const KINDS: Record<string, { label: string; icon: ReactNode }> = {
  character: { label: "People", icon: <I.User size={13} /> }, wardrobe: { label: "Outfits", icon: <I.Shirt size={13} /> },
  prop: { label: "Props", icon: <I.Cube size={13} /> }, set: { label: "Places", icon: <I.Mountain size={13} /> },
};
const FROM: Record<string, string> = { project: "whole project", scene: "this scene", shot: "this shot only", performer: "performs here" };

/**
 * Which library pictures this one shot is shown to the model: turn any on or off, or put it back to automatic.
 * The model only takes so many pictures, so fewer, right ones usually beat many.
 */
export function ShotRefs({ dir, shot, library, thumbs, want, onChanged }: {
  dir: string; shot: BoardShot | undefined; library: Library; thumbs: Record<string, string | null>; want: (srcs: string[]) => void; onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const items = useMemo(() => library.items.filter((i) => i.kind in KINDS && !i.sheet && i.files.length > 0), [library]);
  useEffect(() => { want(items.map((i) => i.files[0])); }, [items]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!shot || !items.length) return null;
  const on = new Map(shot.references.map((r) => [r.id, r.from]));
  const own = library.assign.shots[shot.id] ?? {};
  const changed = (own.add?.length ?? 0) + (own.remove?.length ?? 0) > 0;
  const act = async (f: () => Promise<unknown>) => { setBusy(true); setErr(""); try { await f(); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  const toggle = (it: RefItem) => act(() => api.library(dir, "assign", { scope: "shot", key: shot.id, id: it.id, on: !on.has(it.id) }));
  const auto = () => act(async () => { for (const id of new Set([...(own.add ?? []), ...(own.remove ?? [])])) await api.library(dir, "reset", { scope: "shot", key: shot.id, id }); });
  return (
    <section className="panel shotrefs">
      <PanelHead icon={<I.Layers size={18} />} title="Pictures used in this shot" tag={`${on.size} on`} tone="free"
                 hint="These pictures are shown to the model to keep faces, outfits, props and places the same. Click one to turn it on or off for this shot only." right={changed ? <button className="link" onClick={auto} disabled={busy}>Back to automatic</button> : undefined} />
      {Object.entries(KINDS).map(([kind, k]) => {
        const list = items.filter((i) => i.kind === kind);
        if (!list.length) return null;
        return (
          <div key={kind}>
            <div className="sr-kind">{k.icon} {k.label}</div>
            <div className="sr-grid">{list.map((it) => {
              const t = thumbs[it.files[0]];
              const src = on.get(it.id);
              return (
                <button key={it.id} className={`sr-item ${src ? "on" : ""}`} onClick={() => toggle(it)} disabled={busy} aria-pressed={!!src} title={src ? `On (${FROM[src] ?? src}). Click to turn off for this shot.` : "Off. Click to use it in this shot."}>
                  <span className="sr-thumb" style={t ? { backgroundImage: `url("${api.mediaUrl(`${dir}/${t}`)}")` } : undefined} />
                  <span className="sr-name">{it.name}</span>
                  <span className="sr-state">{src ? (FROM[src] ?? "on") : "off"}</span>
                  {src && <i className="sr-tick"><I.Check size={10} /></i>}
                </button>);
            })}</div>
          </div>);
      })}
      {err && <p className="error-text">{err}</p>}
    </section>
  );
}
