import { useEffect, useState } from "react";
import { api, type Readiness, type ReadinessItem } from "./api";
import { ReadinessSheet } from "./ReadinessSheet";
import { goLabel, moreWords, nextSentence } from "./readinessWords";

/**
 * One slim line under the film's header: the single next thing to do, a button that goes there, and the whole list a click away. It only reads; a step that costs money sends you to
 * the place where the price is shown first. If the film cannot be read it says nothing rather than guess.
 */
export function NextStep({ dir, refresh, onGo, onPolish }: { dir: string; refresh: string; onGo: (item: ReadinessItem) => void; onPolish?: () => void }) {
  const [r, setR] = useState<Readiness | null>(null);
  const [open, setOpen] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => { let live = true; api.filmReadiness(dir).then((x) => { if (live) setR(x); }).catch(() => { if (live) setR(null); }); return () => { live = false; }; }, [dir, refresh, tick]);
  if (!r || !r.items?.length) return null;
  const n = r.next;
  return (
    <>
    <div className={`nx ${r.ready ? "ready" : n?.level ?? "note"}`} role="status" aria-label="The next step">
      <span className="nx-dot" aria-hidden="true" />
      <span className="nx-text"><span className="dim">{r.ready ? "Ready" : "Next"}</span> {nextSentence(n, r.ready)}</span>
      {n && <button className="btn sm" onClick={() => onGo(n)}>{goLabel(n.go)}</button>}
      {r.ready && onPolish && <button className="btn sm" onClick={onPolish} title="Go through the cut, the colour and the titles one after another; skip any you do not want">Polish my film</button>}
      {moreWords(r.items.length) && <button className="link" onClick={() => setOpen(true)}>{moreWords(r.items.length)}</button>}
    </div>
    {open && <ReadinessSheet dir={dir} onClose={() => { setOpen(false); setTick((t) => t + 1); }} onChanged={() => setTick((t) => t + 1)} onGo={(it) => { setOpen(false); onGo(it); }} />}
    </>
  );
}
