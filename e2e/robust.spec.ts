import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

// Every screen the harness can show, at three window sizes, is checked for the faults a person meets first: a script error, a failed request, a picture that did not load, a control with no name,
// something wider than the window (a scrollbar sideways), and text running out of its box. The scene list is read from the harness, so a new screen is covered the day it is added.
// Some harness scenes are photographed at a fixed size on purpose (the whole-window ones); those are checked at their own size only.
const names = [...readFileSync("src/docshots/main.tsx", "utf8").matchAll(/^  "?([a-z0-9-]+)"?: \(\) =>/gm)].map((m) => m[1]);
const WHOLE = new Set(["home", "homeflow", "film", "studio"]);                     // whole-window screens: their own layout is the thing under test
// Scenes whose harness wrapper has a fixed width (a widget photographed at 900 px, say): at a narrower window the wrapper, not the app, is what is wider.
const FIXED = new Set(["layerlanes", "continuity", "compare", "studiovoice", "cutedit"]);
const SIZES = [{ w: 1100, h: 700 }, { w: 1440, h: 900 }, { w: 820, h: 800 }];

for (const name of names) {
  for (const { w, h } of SIZES) {
    test(`the ${name} screen at ${w}x${h} has no script error, broken picture, unnamed control or sideways overflow`, async ({ page }) => {
      const problems: string[] = [];
      page.on("pageerror", (e) => problems.push(`script error: ${e.message}`));
      page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push(`console error: ${m.text().slice(0, 160)}`); });
      await page.route(/\/(f1|render)\/s\d\.png$/, (r) => r.fulfill({ path: "src/docshots/img/s1.png" }));          // the harness's made-up media folders: sample pictures stand in
      await page.setViewportSize({ width: w, height: h });
      await page.goto(`/docshots.html?scene=${name}`);
      await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
      await page.waitForTimeout(700);
      await page.evaluate(() => document.body.classList.remove("docshot"));
      const found = await page.evaluate(({ whole, sheetScene }) => {
        const out: string[] = [];
        for (const img of Array.from(document.images)) if (img.complete && img.naturalWidth === 0 && img.src && !img.src.startsWith("data:")) out.push(`picture did not load: ${img.src.split("/").slice(-2).join("/")}`);
        for (const el of Array.from(document.querySelectorAll("button, [role=button], a[href], input:not([type=hidden]), select, textarea"))) {
          const e = el as HTMLElement;
          if (e.offsetParent === null && getComputedStyle(e).position !== "fixed") continue;                          // not shown
          const name = (e.getAttribute("aria-label") || e.getAttribute("title") || e.textContent || "").trim() || (e as HTMLInputElement).placeholder || "";
          const labelled = (e as HTMLInputElement).labels?.length || e.getAttribute("aria-labelledby");
          if (!name && !labelled) out.push(`a control has no name: <${e.tagName.toLowerCase()} class="${e.className}">`);
        }
        const root = document.documentElement;
        if (!whole && !sheetScene && root.scrollWidth > window.innerWidth + 2) out.push(`wider than the window: ${root.scrollWidth} > ${window.innerWidth}`);
        for (const el of Array.from(document.querySelectorAll("button, .btn, label, h1, h2, h3"))) {
          const e = el as HTMLElement;
          if (e.offsetParent === null) continue;
          const cs = getComputedStyle(e);
          if (cs.overflow === "hidden" || cs.textOverflow === "ellipsis" || cs.display === "inline") continue;
          if (e.scrollWidth > e.clientWidth + 3 && e.clientWidth > 0 && cs.whiteSpace === "nowrap") out.push(`text runs out of its box: "${(e.textContent || "").trim().slice(0, 40)}"`);
        }
        return out;
      }, { whole: WHOLE.has(name), sheetScene: FIXED.has(name) && w < 1000 });
      expect([...problems, ...found]).toEqual([]);
    });
  }
}
