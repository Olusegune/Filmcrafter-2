import { useCallback, useEffect, useState } from "react";
import { api, errorText, type PlacesStatus } from "./api";

/**
 * A heads-up above the pictures: a place that nobody described is invented again by the picture model in every shot, which is where messy, inconsistent backgrounds come from. It offers a free first
 * description from the story's own words (never over one that exists) and a way to Cast & World. It makes and buys nothing.
 */
export function PlaceNotice({ dir, onOpenPlaces }: { dir: string; onOpenPlaces?: () => void }) {
  const [st, setSt] = useState<PlacesStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [said, setSaid] = useState("");
  const load = useCallback(() => api.filmPlaces("status", dir).then(setSt).catch(() => setSt(null)), [dir]);
  useEffect(() => { void load(); window.addEventListener("pf-library-changed", load); return () => window.removeEventListener("pf-library-changed", load); }, [load]);
  const missing = st?.places.filter((p) => p.missing) ?? [];
  if (!missing.length && !said) return null;
  const fill = async () => {
    setBusy(true); setErr("");
    try { const r = await api.filmPlaces("draft", dir); setSt(r); setSaid(r.filled?.length ? `Wrote a first description for ${r.filled.map((f) => f.name).join(", ")} from the story. Read it in Cast & World and add what the story does not say.` : r.note ?? ""); }
    catch (e) { setErr(errorText(e)); }
    setBusy(false);
  };
  return (
    <div className="place-notice" role="status">
      {missing.length > 0 && <p><b>{missing.length === 1 ? "One place has" : `${missing.length} places have`} no description or picture</b> ({missing.slice(0, 3).map((p) => p.name).join("; ")}{missing.length > 3 ? "; …" : ""}). The picture model then invents the background again in every shot, which is where messy, changing backgrounds come from.
        A short description of what is there (the fence, the buildings, where things are) and a picture of the place keep it the same.</p>}
      {said && <p className="dim">{said}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
      {missing.length > 0 && <div className="place-actions"><button className="btn sm" disabled={busy} onClick={() => void fill()}>{busy ? "Writing…" : "Fill in from the story (free)"}</button>
        {onOpenPlaces && <button className="btn ghost sm" onClick={onOpenPlaces}>Open Places in Cast &amp; World</button>}</div>}
    </div>
  );
}
