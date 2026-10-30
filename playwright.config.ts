import { defineConfig } from "@playwright/test";

// Browser tests of real screens, driven against the dev server (`npm run dev`) on the screenshot harness (docshots.html), which answers the app's backend calls with made-up data:
// no engine, no provider, nothing is sent anywhere and nothing can be charged.
//   npx playwright test                   everything        npx playwright test e2e/shotlook.spec.ts        one file
// Locally it uses the Microsoft Edge that Windows already has (no browser download); in CI it uses Playwright's own Chromium (`npx playwright install chromium`).
// Set PW_CHANNEL=chrome (or msedge) to pick an installed browser.
// @ts-expect-error type error without @types/node package
const env: Record<string, string | undefined> = process.env;

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,                              // the first page load waits for the dev server to compile
  expect: { timeout: 12_000 },
  fullyParallel: true,
  workers: env.CI ? 2 : 3,
  retries: env.CI ? 1 : 0,
  reporter: env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:1420",
    channel: env.PW_CHANNEL ?? (env.CI ? undefined : "msedge"),
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "desktop" }],
  webServer: { command: "npm run dev", url: "http://localhost:1420", reuseExistingServer: true, timeout: 240_000 },
});
