import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import guide from "../../docs/GETTING_STARTED.md?raw";
import styles from "../../analysis/filmcrafter_engine/styles.json";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

import { HelpSheet, docImage, renderGuide } from "../Help";
import type { ReactElement } from "react";

const refs = [...guide.matchAll(/^!\[([^\]]*)\]\((img\/[^)]+)\)\s*$/gm)].map((m) => ({ alt: m[1], path: m[2] }));

describe("the documentation's screenshots", () => {
  it("has some, each with a caption, and every one exists in docs/img (including the film folder)", () => {
    expect(refs.length).toBeGreaterThanOrEqual(6);
    for (const r of refs) {
      expect(r.alt.length, `${r.path} needs a caption`).toBeGreaterThan(10);
      expect(docImage(r.path), `${r.path} is in the guide but not in docs/img: run node scripts/docshots.mjs`).toBeTruthy();
    }
  });

  it("are drawn in the in-app guide as pictures with captions", () => {
    const html = renderToStaticMarkup(<HelpSheet onClose={() => {}} />);
    expect((html.match(/<figure class="guide-shot">/g) ?? []).length).toBe(refs.length);
    expect(html).toContain("<figcaption>");
    expect(html).not.toContain("![");                    // none left as plain text
  });

  it("gives every block of the guide its own key (a repeat can drop or double a block in the viewer)", () => {
    const parts = guide.split(/\r?\n(?=## )/);
    for (const md of [parts[0], ...parts.slice(1)]) {
      const keys = renderGuide(md).map((e) => String((e as ReactElement).key));
      expect(new Set(keys).size, `repeated keys in: ${md.split(/\r?\n/)[0]}`).toBe(keys.length);
    }
    const all = renderGuide(guide).map((e) => String((e as ReactElement).key));
    expect(new Set(all).size).toBe(all.length);
  });

  it("lists every look the app offers, so the guide and the app cannot disagree (run scripts/make_look_docs.py after adding one)", () => {
    for (const st of styles.styles) {
      if (st.family === "auto") continue;
      expect(guide, `${st.name} is in the app but not in the guide`).toContain(`**${st.name}**`);
    }
    expect(guide).toContain("Cast & World");
    expect(guide).toContain("## The look library");
  });

  it("is the film guide: the steps, the money rules, the look and the shortcuts", () => {
    for (const h of ["## Before you start", "## The steps of a film", "## Cast & World: the Production Bible", "### Choosing the look", "### Animation principles", "### Production Supervisor", "## Keyboard shortcuts", "## When something goes wrong"]) expect(guide).toContain(h);
    expect(guide).toContain("shows its price first");
    expect(guide).not.toMatch(/music video from a song|Autopilot|BPM/i);        // this is not the PULSEFRAME guide
  });
});
