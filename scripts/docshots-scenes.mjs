// Regenerates the pictures of the newer screens in docs/img from the screenshot harness (made-up data, no engine, nothing is sent anywhere).
//
//   npx vite --port 1420 --strictPort     (in another terminal)
//   node scripts/docshots-scenes.mjs      (all)     or     node scripts/docshots-scenes.mjs home-new motion-graphics    (just those)
//   python scripts/shrink_docshots.py     (then make them smaller: they are bundled into the app so the guide works offline)
//
// Each shot is a harness scene (src/docshots/main.tsx), what to do on it, and what to photograph. Add one to cover a new screen, then reference it in docs/GETTING_STARTED.md as ![what it shows](img/name.png).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.PF_OUT || join(ROOT, "docs", "img");
const BASE = process.env.PF_BASE || "http://localhost:1420";
mkdirSync(OUT, { recursive: true });

const sheet = ".sheet";
const SHOTS = {
  "home-new": { scene: "homeflow", size: [1440, 900], seen: true, alt: "The Home screen: three ways to begin, featured presets, and your films" },
  "home-welcome": { scene: "homeflow", query: "&none=1", size: [1100, 800], seen: false, shoot: ".hm-welcome", alt: "The first-launch question: what would you like to create?" },
  "home-presets": { scene: "homeflow", size: [1280, 900], seen: true, steps: async (p) => { await p.getByRole("button", { name: /^View all presets/ }).click(); }, shoot: ".hm-gallery", alt: "All presets, searchable and filtered by kind" },
  "home-preset-details": { scene: "homeflow", size: [1100, 800], seen: true, steps: async (p) => { await p.locator(".hm-presets .hm-pcard").first().getByRole("button").click(); }, shoot: ".hm-details", alt: "A preset's details: what it sets and what it stacks" },
  "newfilm-setup": { scene: "newfilmpreset", size: [1000, 1250], steps: async (p) => { await p.getByText("Advanced: change what the preset brings").click(); }, shoot: sheet, alt: "Setting a film up from a preset: length, episodes and Advanced choices" },
  "guide-path": { scene: "guide", size: [1000, 1100], shoot: sheet, alt: "The Guide: the path from story to export, with the finishing tools" },
  "motion-graphics": { scene: "motion", size: [1200, 900], shoot: sheet, alt: "Motion graphics: eight ready-made titles, with their words" },
  "mix-effects": { scene: "layermix", size: [520, 900], steps: async (p) => { await p.locator("details.ly-mix summary").click(); }, shoot: "details.ly-mix", alt: "A layer's Mix and effects: blend mode, glow, blur, a shape and a cut-out colour" },
  "video-clip-layer": { scene: "layerclip", size: [420, 980], steps: async (p) => { await p.locator("details.ly-mix summary").click(); }, alt: "A video clip layer: where to start, loop, width, opacity and a cut-out colour" },
  "presets-sheet": { scene: "presets", size: [1280, 900], shoot: sheet, alt: "The Presets sheet: stack presets, preview what changes, apply, undo" },
  "color-studio": { scene: "color", size: [1280, 900], shoot: sheet, alt: "Color Studio" },
  "smart-editor": { scene: "smarteditor", size: [1100, 900], shoot: sheet, alt: "The Smart Editor: suggestions for the cut, each with its reason" },
};

const wanted = process.argv.slice(2);
const names = wanted.length ? wanted : Object.keys(SHOTS);
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });          // the same browser the tests use
let failed = 0;
for (const name of names) {
  const s = SHOTS[name];
  if (!s) { console.error(`no such shot: ${name}`); failed++; continue; }
  const page = await browser.newPage({ viewport: { width: s.size[0], height: s.size[1] }, deviceScaleFactor: 1 });
  try {
    if (s.seen !== false) await page.addInitScript(() => { try { localStorage.setItem("pf-home-welcome", "1"); } catch { /* optional */ } });
    await page.route(/\/(f1|render)\/s\d\.png$/, (r) => r.fulfill({ path: join(ROOT, "src", "docshots", "img", "s1.png") }));
    await page.goto(`${BASE}/docshots.html?scene=${s.scene}${s.query ?? ""}`);
    await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }" });
    await page.waitForTimeout(1100);
    await page.evaluate(() => document.body.classList.remove("docshot"));
    if (s.steps) { await s.steps(page); await page.waitForTimeout(500); }
    const file = join(OUT, `${name}.png`);
    if (s.shoot && s.maxH) {                                             // the top part of a long panel
      const b = await page.locator(s.shoot).first().boundingBox();
      await page.screenshot({ path: file, clip: { x: b.x, y: b.y, width: b.width, height: Math.min(b.height, s.maxH) } });
    } else if (s.shoot) await page.locator(s.shoot).first().screenshot({ path: file });
    else await page.screenshot({ path: file });
    console.log(`ok   ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}: ${String(e.message).split("\n")[0]}`);
    failed++;
  } finally { await page.close(); }
}
await browser.close();
process.exit(failed ? 1 : 0);
