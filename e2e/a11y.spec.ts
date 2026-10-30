import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";

// Every screen the screenshot harness (src/docshots/main.tsx) can show is scanned with axe-core for WCAG 2.1 A and AA violations. The list of scenes is read from the harness itself, so a
// new scene is covered the day it is added. Animations are switched off first: a sheet that is still fading in has a colour between its two states, and axe reports a contrast that is not real.
// The harness un-scrolls long lists for its screenshots (body.docshot); that is removed so the scan sees the screen as the app shows it.
// An automated scan finds about a third of the accessibility problems there are: it does not replace a person using a screen reader or only a keyboard.
const names = [...readFileSync("src/docshots/main.tsx", "utf8").matchAll(/^  "?([a-z0-9-]+)"?: \(\) =>/gm)].map((m) => m[1]);

test("the harness lists its scenes", () => {
  expect(names.length).toBeGreaterThan(30);
});

for (const name of names) {
  test(`the ${name} screen has no WCAG A or AA violations`, async ({ page }) => {
    await page.goto(`/docshots.html?scene=${name}`);
    await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
    await page.waitForTimeout(900);
    await page.evaluate(() => document.body.classList.remove("docshot"));
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(r.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
  });
}
