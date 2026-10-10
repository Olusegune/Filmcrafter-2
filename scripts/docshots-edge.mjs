// Regenerates screenshots of the screens built since the old preview data (mock-data) went missing, from the screenshot harness (src/docshots, docshots.html).
// It needs only Edge or Chrome and Node 22 or newer (it talks to the browser over the DevTools protocol; no packages). Nothing is sent anywhere and no real project is read.
//
//   npm run dev                                  (the preview must be on http://localhost:1420)
//   node scripts/docshots-edge.mjs               (every scene)       node scripts/docshots-edge.mjs review kt   (just those)
//   PF_OUT=<folder> node scripts/docshots-edge.mjs ...              (keep a run out of docs/img)
//
// Each scene is opened in a tall window; the harness writes "width,height" of what it drew into the page title; the window is then set to exactly that size and photographed.
// Add a scene to src/docshots/main.tsx, add a line below, and reference docs/img/<file> in docs/GETTING_STARTED.md.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.PF_OUT || join(ROOT, "docs", "img");
const BASE = process.env.PF_URL || "http://localhost:1420/docshots.html";
const PORT = 9344;
const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium",
];

// name: [file, query]
const SCENES = {
  review: ["review.png", "scene=review"],
  queue: ["queue.png", "scene=queue"],
  retry: ["queue-retry.png", "scene=retry&click=Try a cheaper model"],
  kt: ["keyframetools.png", "scene=keyframetools"],
  handfix: ["handfix.png", "scene=handfix&drag=0.40,0.48,0.62,0.86"],
  budget: ["planbudget.png", "scene=planbudget"],
  select: ["selectreview.png", "scene=selectreview"],
  compare: ["comparetakes.png", "scene=compare"],
  dirlib: ["directionlib.png", "scene=directionlibrary&clickcss=.dl-card:nth-child(2)"],
  directions: ["directions.png", "scene=directions"],
  looks: ["looks.png", "scene=looks"],
  lighting: ["lighting.png", "scene=lighting&clickcss=.lt-run:nth-of-type(3) > summary"],
  cleanup: ["cleanup.png", "scene=cleanup"],
  models: ["modelchoice.png", "scene=modelchoice"],
  home: ["home.png", "scene=home"],
  newfilm: ["newfilm.png", "scene=newfilm"],
  newfilmwrite: ["newfilm-story.png", "scene=newfilmwrite"],
  film: ["film.png", "scene=film"],
  library: ["library.png", "scene=library"],
  supervisor: ["supervisor.png", "scene=supervisor"],
  acting: ["acting.png", "scene=acting"],
  layers: ["layers.png", "scene=layers"],
  lanes: ["layerlanes.png", "scene=layerlanes"],
  colourmatch: ["colourmatch.png", "scene=colourmatch"],
  compose: ["compose.png", "scene=compose"],
  motionlib: ["motionlibrary.png", "scene=compose&click=Motion"],
};

const browser = BROWSERS.find((p) => existsSync(p));
if (!browser) { console.error("No Edge or Chrome found."); process.exit(1); }
try { await fetch(BASE); } catch { console.error(`The preview isn't running on ${BASE.split("/docshots")[0]}. Start it with: npm run dev`); process.exit(1); }
mkdirSync(OUT, { recursive: true });

const profile = mkdtempSync(join(tmpdir(), "pf-shots-"));
const proc = spawn(browser, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--autoplay-policy=no-user-gesture-required", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const cleanup = () => { try { proc.kill(); } catch { /* already gone */ } setTimeout(() => { try { rmSync(profile, { recursive: true, force: true }); } catch { /* still in use: the system clears it */ } }, 800); };
process.on("exit", cleanup);

let wsUrl = null;
for (let i = 0; i < 60 && !wsUrl; i++) {
  try { const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); wsUrl = list.find((t) => t.type === "page")?.webSocketDebuggerUrl ?? null; } catch { /* not up yet */ }
  if (!wsUrl) await sleep(250);
}
if (!wsUrl) { console.error("Couldn't reach the browser."); cleanup(); process.exit(1); }
const ws = new WebSocket(wsUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((res) => { const n = ++id; pending.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); });
const evalJs = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true })).result?.result?.value;

const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
await send("Page.enable");
for (const name of names) {
  const spec = SCENES[name];
  if (!spec) { console.error(`unknown scene: ${name} (try: ${Object.keys(SCENES).join(", ")})`); continue; }
  const [file, query] = spec;
  try {
    await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 2400, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url: `${BASE}?${query.replace(/ /g, "%20")}` });
    let size = null;
    for (let i = 0; i < 80 && !size; i++) { await sleep(250); const t = await evalJs("document.title"); if (/^\d+,\d+$/.test(t ?? "")) size = t.split(",").map(Number); }
    if (!size) { console.error(`${name}: the screen never reported its size`); continue; }
    const [w, h] = [Math.min(1500, size[0] === 1440 ? 1440 : size[0]), Math.min(3400, size[1])];
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
    await sleep(700);
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    writeFileSync(join(OUT, file), Buffer.from(shot.result.data, "base64"));
    console.log(`${name.padEnd(11)} ${w}x${h}  ${file}`);
  } catch (e) { console.error(`${name}: ${String(e.message ?? e).split("\n")[0]}`); }
}
ws.close();
cleanup();
