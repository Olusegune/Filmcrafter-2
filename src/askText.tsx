import { createRoot } from "react-dom/client";
import { useEffect, useRef, useState } from "react";

/** A short question in the app's own style, answered with a line of text (the system prompt box is not available in every window). Resolves with the text, or null if cancelled. */
function TextDialog({ title, hint, ok, done }: { title: string; hint: string; ok: string; done: (v: string | null) => void }) {
  const [v, setV] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div className="overlay ask-overlay" onClick={() => done(null)}>
      <form className="sheet glass ask" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => { e.preventDefault(); if (v.trim()) done(v.trim()); }} onKeyDown={(e) => { if (e.key === "Escape") done(null); }}>
        <div className="ask-body"><h3>{title}</h3>
          <input ref={ref} className="text-input" value={v} placeholder={hint} maxLength={80} aria-label={title} onChange={(e) => setV(e.target.value)} /></div>
        <div className="ask-actions"><button type="button" className="btn ghost" onClick={() => done(null)}>Cancel</button>
          <button className="btn primary" type="submit" disabled={!v.trim()}>{ok}</button></div>
      </form>
    </div>
  );
}

export function askText(title: string, hint = "", ok = "Add"): Promise<string | null> {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const done = (v: string | null) => { root.unmount(); host.remove(); resolve(v); };
    root.render(<TextDialog title={title} hint={hint} ok={ok} done={done} />);
  });
}
