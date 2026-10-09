import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, type Estimate } from "./api";
import * as I from "./icons";

/** The inspector's pinned bottom bar: where the open tab's main action always sits, whatever the panel above is scrolled to. */
export const DockCtx = createContext<{ el: HTMLElement | null; tab: string }>({ el: null, tab: "" });

/** Content for the dock. It appears only while its own tab is the open one. */
export function DockSlot({ tab, children }: { tab: string; children: ReactNode }) {
  const { el, tab: open } = useContext(DockCtx);
  if (open !== tab) return null;
  return el ? createPortal(children, el) : <div className="dock-inline">{children}</div>;
}

export function DockBar({ chips, children }: { chips?: ReactNode; children: ReactNode }) {
  return (
    <div className="dock-bar">
      {chips ? <div className="dock-chips">{chips}</div> : null}
      <div className="dock-actions">{children}</div>
    </div>
  );
}

/** The one main action of a tab: warm and glowing so it can't be missed. `tone="quiet"` is its calmer sibling. */
export function Cta({ icon, children, price, busy, disabled, onClick, title, tone = "warm" }: {
  icon?: ReactNode; children: ReactNode; price?: string; busy?: boolean; disabled?: boolean; onClick: () => void; title?: string; tone?: "warm" | "quiet";
}) {
  return (
    <button className={`cta ${tone}`} onClick={onClick} disabled={disabled || busy} title={title}>
      <span className="cta-ic">{busy ? <span className="spin" /> : icon}</span>
      <span className="cta-label">{children}</span>
      {price ? <span className="cta-price">{price}</span> : null}
    </button>
  );
}

/** A panel's title with its icon, an optional status tag and a one-line hint. */
export function PanelHead({ icon, title, tag, tone = "ok", hint, right }: {
  icon: ReactNode; title: string; tag?: string; tone?: "ok" | "free" | "warn"; hint?: string; right?: ReactNode;
}) {
  return (
    <div className="ph">
      <div className="ph-row">
        <span className="ph-ic">{icon}</span>
        <h3 className="ph-title">{title}</h3>
        {tag ? <span className={`ph-tag ${tone}`}>{tag}</span> : null}
        <span style={{ flex: 1 }} />
        {right}
      </div>
      {hint ? <p className="ph-hint">{hint}</p> : null}
    </div>
  );
}

/** A small read-only fact in the dock or a settings row. */
export function Pill({ icon, children, tone, title }: { icon?: ReactNode; children: ReactNode; tone?: "ok" | "warn"; title?: string }) {
  return <span className={`pill ${tone ?? ""}`} title={title}>{icon}{children}</span>;
}

/** "≈ $0.04", "≈ 16 cr", "free", or nothing when no price is known. */
export function priceLabel(e: Estimate | null | undefined): string {
  if (!e) return "";
  if (e.usd != null) return e.usd === 0 ? "free" : `≈ $${e.usd < 0.1 ? e.usd.toFixed(3) : e.usd.toFixed(2)}`;
  if (e.kie_credits_est) return `≈ ${e.kie_credits_est} cr`;
  return "";
}

/** The price of one render, kept up to date as the choices change (asked of the engine once the choices settle). */
export function useEstimate(dir: string, shots: string[], provider: string, model: string | null, kind: "video" | "image", deps: unknown[] = []): Estimate | null {
  const [est, setEst] = useState<Estimate | null>(null);
  const key = shots.join(",");
  useEffect(() => {
    if (!dir || !shots.length || !provider) return;
    let live = true;
    const t = setTimeout(() => { api.renderEstimate(dir, shots, provider, model, kind).then((e) => live && setEst(e)).catch(() => live && setEst(null)); }, 350);
    return () => { live = false; clearTimeout(t); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dir, key, provider, model, kind, ...deps]);
  return est;
}

export const Hint = ({ children }: { children: ReactNode }) => <p className="dim hint-line"><I.Info size={13} /> {children}</p>;
