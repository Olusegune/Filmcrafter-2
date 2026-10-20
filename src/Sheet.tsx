import { useEffect, useRef, type CSSProperties, type FormEventHandler, type ReactNode } from "react";

/**
 * The one dialog. Every sheet in the app used to be a hand-made `<div class="overlay"><div class="sheet" role="dialog">`, each deciding for itself whether Escape,
 * the backdrop or Tab did anything. This does it once: the page behind is marked inert to screen readers (aria-modal), Escape and a click on the backdrop dismiss the
 * topmost dialog only, Tab stays inside, and focus returns to what had it when the dialog opens.
 *
 * `onDismiss` is what Escape and the backdrop do. Leave it undefined while the dialog must not be left (a render being sent, a file being written).
 */

// The open dialogs, oldest first. A dialog made by `ask()` joins the same list, so Escape closes only the one on top.
type Entry = { id: symbol; el: Element | null };
const stack: Entry[] = [];
/** `o` is above `me`: later in the page (a dialog inside another one counts as later), or, when either has no element to compare, opened later. */
const above = (o: Entry, me: Entry) =>
  o.el && me.el ? !!(me.el.compareDocumentPosition(o.el) & Node.DOCUMENT_POSITION_FOLLOWING) : stack.indexOf(o) > stack.indexOf(me);
export const modalStack = {
  // `el` is the dialog's element: with it, "on top" follows the page, so a dialog and one inside it that open in the same render (React mounts the inner one first) still stack correctly.
  push: (id: symbol, el: Element | null = null) => { stack.push({ id, el }); },
  remove: (id: symbol) => { const i = stack.findIndex((e) => e.id === id); if (i >= 0) stack.splice(i, 1); },
  isTop: (id: symbol) => { const me = stack.find((e) => e.id === id); return !!me && !stack.some((o) => o !== me && above(o, me)); },
  size: () => stack.length,
};

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/** Where Tab goes next inside a dialog of `count` focusable things: wraps at both ends. `at` is -1 when focus is not on any of them. Pure, so it can be tested. */
export function nextFocus(at: number, count: number, back: boolean): number {
  if (count <= 0) return -1;
  if (at < 0) return back ? count - 1 : 0;
  return back ? (at === 0 ? count - 1 : at - 1) : (at === count - 1 ? 0 : at + 1);
}

const visible = (e: HTMLElement) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);

export function Sheet({ onDismiss, label, className, style, overlayClass, role = "dialog", onSubmit, children }: {
  onDismiss?: (() => unknown) | undefined;
  label: string;
  className?: string;            // classes of the panel besides "sheet glass"
  onSubmit?: FormEventHandler<HTMLFormElement>;   // given: the panel is a <form>
  style?: CSSProperties;
  overlayClass?: string;         // classes of the backdrop besides "overlay"
  role?: "dialog" | "alertdialog";
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement & HTMLFormElement>(null);   // a div, or a form when onSubmit is given
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;

  useEffect(() => {
    const id = Symbol("sheet");
    const before = document.activeElement as HTMLElement | null;
    const p = panel.current;
    modalStack.push(id, p);
    // Focus goes to the dialog itself (announced by its label); the next Tab reaches its first control. A control that asked for focus (autoFocus) keeps it.
    if (p && !p.contains(document.activeElement)) p.focus({ preventScroll: true });

    const onKey = (e: KeyboardEvent) => {
      if (!modalStack.isTop(id)) return;
      if (e.key === "Escape" && !e.defaultPrevented) {
        if (dismiss.current) { e.preventDefault(); dismiss.current(); }
        return;
      }
      if (e.key !== "Tab" || !p) return;
      const items = [...p.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(visible);
      if (!items.length) { e.preventDefault(); p.focus(); return; }
      const at = p === document.activeElement ? -1 : items.indexOf(document.activeElement as HTMLElement);
      const n = nextFocus(at, items.length, e.shiftKey);
      // Only take over at the ends (or when focus is outside the list); the browser's own order is right in between.
      if (at < 0 || (!e.shiftKey && at === items.length - 1) || (e.shiftKey && at === 0)) { e.preventDefault(); items[n].focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      modalStack.remove(id);
      if (before && before.isConnected && typeof before.focus === "function") before.focus({ preventScroll: true });
    };
  }, []);

  const cls = `sheet glass${className ? ` ${className}` : ""}`;
  return (
    <div className={`overlay${overlayClass ? ` ${overlayClass}` : ""}`} onClick={(e) => { if (e.target === e.currentTarget) dismiss.current?.(); }}>
      {onSubmit
        ? <form ref={panel}className={cls} role={role} aria-modal="true" aria-label={label} tabIndex={-1} style={style} onSubmit={onSubmit}>{children}</form>
        : <div ref={panel} className={cls} role={role} aria-modal="true" aria-label={label} tabIndex={-1} style={style}>{children}</div>}
    </div>
  );
}
