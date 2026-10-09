import { createRoot } from "react-dom/client";
import { useEffect, useRef } from "react";
import * as I from "./icons";

/**
 * A confirmation in the app's own style, as a promise: `if (!(await ask("Make 4 pictures?\n\nCost: about $0.42."))) return;`
 * The first line is the title; blank lines separate paragraphs. Used wherever money is spent or something is replaced.
 */
export function Dialog({ message, ok, danger, done }: { message: string; ok: string; danger: boolean; done: (v: boolean) => void }) {
  const [title, ...rest] = message.split("\n\n");
  const okRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    okRef.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") done(false); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [done]);
  return (
    <div className="overlay ask-overlay" onClick={() => done(false)}>
      <div className="sheet glass ask" role="alertdialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className={`ask-ic ${danger ? "danger" : ""}`}>{danger ? <I.Alert size={20} /> : <I.Sparkle size={20} />}</div>
        <div className="ask-body">
          <h3>{title}</h3>
          {rest.map((p, i) => <p key={i}>{p.split("\n").map((l, k) => <span key={k}>{l}<br /></span>)}</p>)}
        </div>
        <div className="ask-actions">
          <button className="btn ghost" onClick={() => done(false)}>Cancel</button>
          <button ref={okRef} className={`btn ${danger ? "danger" : "primary"}`} onClick={() => done(true)}>{ok}</button>
        </div>
      </div>
    </div>
  );
}

/** The button words and tone follow the question when the caller does not say: "Remove …?" asks for Remove and is red; "Make …?" asks for Continue. */
export function defaults(message: string): { ok: string; danger: boolean } {
  const m = message.trim();
  const verb = [[/^Remove\b/i, "Remove"], [/^Clear\b/i, "Clear"], [/^Replace\b/i, "Replace"], [/^Use this file as the script/i, "Use it"], [/^Go back\b/i, "Go back"], [/^Split\b/i, "Split"]] as const;
  const hit = verb.find(([re]) => re.test(m));
  return hit ? { ok: hit[1], danger: !/^(Go back|Use this)/i.test(m) } : { ok: "Continue", danger: false };
}

export function ask(message: string, opts: { ok?: string; danger?: boolean } = {}): Promise<boolean> {
  const d = defaults(message);
  opts = { ok: opts.ok ?? d.ok, danger: opts.danger ?? d.danger };
  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const done = (v: boolean) => { root.unmount(); host.remove(); resolve(v); };
    root.render(<Dialog message={message} ok={opts.ok ?? "OK"} danger={!!opts.danger} done={done} />);
  });
}
