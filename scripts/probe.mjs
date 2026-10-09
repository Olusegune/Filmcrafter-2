// Runs the clicks of a docshots scene, then evaluates a snippet in the page and prints the result. For measuring layout in the browser preview.
//   node scripts/probe.mjs studio "document.title"
//   node scripts/probe.mjs "js:@open document.querySelector('.rail button').click(); await new Promise(r=>setTimeout(r,800));" "window.__errs"
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SHOTS, connect } from "./docshots.mjs";

const [scene, snippet] = process.argv.slice(2);
const exe = process.env.PF_BROWSER || ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find(existsSync);
const proc = spawn(exe, ["--headless=new", "--remote-debugging-port=9334", `--user-data-dir=${mkdtempSync(join(tmpdir(), "pf-probe-"))}`, "--hide-scrollbars", "--disable-gpu", "about:blank"], { stdio: "ignore" });
try {
  const cdp = await connect(9334);
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await cdp.send("Page.navigate", { url: process.env.PF_URL || "http://localhost:1420/?mock" });
  await new Promise((r) => setTimeout(r, 1500));
  const run = (expression) => cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  // a scene from scripts/docshots.mjs, or raw clicks written as  js:<code>  (errors the page logs are collected in window.__errs)
  const body = scene.startsWith("js:") ? scene.slice(3).replace("@open", SHOTS.studio.steps) : SHOTS[scene].steps;
  const hook = "window.__errs = []; { const oe = console.error; console.error = (...a) => { window.__errs.push(a.map(String).join(' ').slice(0, 400)); oe(...a); }; window.addEventListener('error', (e) => window.__errs.push(String(e.message))); }";
  const steps = await run(`(async () => { ${hook} ${body} return true; })()`);
  if (steps.exceptionDetails) throw new Error(steps.exceptionDetails.exception?.description);
  const r = await run(`(async () => { return (${snippet}); })()`);
  console.log(JSON.stringify(r.result?.value ?? r.exceptionDetails?.exception?.description, null, 1));
  cdp.close();
} finally { proc.kill(); }
