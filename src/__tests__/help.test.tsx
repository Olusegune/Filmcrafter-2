import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import guide from "../../docs/GETTING_STARTED.md?raw";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

import { HelpSheet, docImage, renderGuide } from "../Help";
import type { ReactElement } from "react";

const refs = [...guide.matchAll(/^!\[([^\]]*)\]\((img\/[^)]+)\)\s*$/gm)].map((m) => ({ alt: m[1], path: m[2] }));

describe("the documentation's screenshots", () => {
  it("has some, each with a caption, and every one exists in docs/img", () => {
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

  it("the guide has a section on the sound of each shot, and the shortcuts include it", () => {
    expect(guide).toContain("## 24. The sound of each shot");
    expect(guide).toContain("`Shift+M`");
  });
});
