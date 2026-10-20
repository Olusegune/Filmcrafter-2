import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Sheet, modalStack, nextFocus } from "../Sheet";

describe("Tab inside a dialog", () => {
  it("wraps from the last control to the first, and back", () => {
    expect(nextFocus(2, 3, false)).toBe(0);
    expect(nextFocus(0, 3, true)).toBe(2);
  });
  it("moves one step in between", () => {
    expect(nextFocus(0, 3, false)).toBe(1);
    expect(nextFocus(2, 3, true)).toBe(1);
  });
  it("starts at the first control (or the last, going back) when focus is not on any", () => {
    expect(nextFocus(-1, 3, false)).toBe(0);
    expect(nextFocus(-1, 3, true)).toBe(2);
  });
  it("has nowhere to go in a dialog with no controls", () => {
    expect(nextFocus(-1, 0, false)).toBe(-1);
  });
});

describe("the dialog stack", () => {
  it("only the newest dialog is on top, and the one under it is back on top when it closes", () => {
    const a = Symbol("a"), b = Symbol("b");
    modalStack.push(a); modalStack.push(b);
    expect(modalStack.isTop(a)).toBe(false);
    expect(modalStack.isTop(b)).toBe(true);
    modalStack.remove(b);
    expect(modalStack.isTop(a)).toBe(true);
    modalStack.remove(a);
    expect(modalStack.size()).toBe(0);
  });
});

describe("<Sheet>", () => {
  it("is a labelled, modal dialog over a backdrop", () => {
    const html = renderToStaticMarkup(<Sheet label="Export" onDismiss={() => {}}><p>hi</p></Sheet>);
    expect(html).toContain('class="overlay"');
    expect(html).toContain('class="sheet glass"');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-label="Export"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain("<p>hi</p>");
  });
  it("keeps the caller's classes and style on the panel", () => {
    const html = renderToStaticMarkup(<Sheet label="x" className="wide" style={{ width: 400 }}>y</Sheet>);
    expect(html).toContain('class="sheet glass wide"');
    expect(html).toContain("width:400px");
  });
  it("is a form when it has a submit handler", () => {
    expect(renderToStaticMarkup(<Sheet label="x" onSubmit={() => {}}>y</Sheet>)).toMatch(/<form class="sheet glass"[^>]*role="dialog"/);
  });
});

// A hand-built dialog has no Escape, no focus handling and no aria-modal, and that is how the app used to be. New dialogs go through <Sheet>.
describe("every dialog goes through <Sheet>", () => {
  const sources = import.meta.glob("../*.tsx", { eager: true, query: "?raw", import: "default" }) as Record<string, string>;
  const files = Object.keys(sources).map((p) => p.replace("../", "")).filter((f) => f !== "Sheet.tsx");
  // Not sheets: the command palette and the Director command have their own typing and arrow-key handling; the intro tour, the transition pop-over and the Wizard's
  // inline choice are not modal; the Cleanup viewer and the two picture lightboxes are a picture on a backdrop.
  const NOT_SHEETS = new Set(["Palette.tsx", "Command.tsx", "Tour.tsx", "TransitionHandles.tsx", "Wizard.tsx:video-choice", "Cleanup.tsx", "Keyframe.tsx", "SelectReview.tsx", "ask.tsx", "askText.tsx"]);
  it("no screen builds its own sheet panel", () => {
    const offenders: string[] = [];
    for (const f of files) {
      if (NOT_SHEETS.has(f)) continue;
      const text = sources[`../${f}`];
      if (/className="sheet glass/.test(text) || /className=\{`sheet glass/.test(text)) offenders.push(f);
    }
    expect(offenders, `${offenders.join(", ")} build a sheet by hand: use <Sheet> from ./Sheet`).toEqual([]);
  });
});
