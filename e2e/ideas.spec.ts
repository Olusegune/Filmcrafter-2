import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Four finishing touches, driven on the screenshot harness: a film's own picture on Home, the ready screen after an export (with the vertical version one click away), a season made into films, and
// finding the screen colour. The harness's made-up engine answers; the engine's own tests prove the real answers. Nothing is rendered or charged.
const calm = async (page: Page) => {
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
};
const home = async (page: Page) => {
  await page.addInitScript(() => { try { localStorage.setItem("pf-home-welcome", "1"); } catch { /* optional */ } });
  await page.goto("/docshots.html?scene=homeflow");
  await calm(page);
  await expect(page.getByRole("heading", { name: "What will you create today?" })).toBeVisible();
};

test.describe("a film's own picture on Home", () => {
  test("a film with a picture shows it, and one without keeps the plain strip", async ({ page }) => {
    await home(page);
    const withPic = page.getByRole("button", { name: "Continue Last Train" });
    await expect(withPic.locator("img.hm-cardpic")).toBeVisible();
    expect(await withPic.locator("img.hm-cardpic").evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    const without = page.getByRole("button", { name: "Continue The Lighthouse Keeper" });
    await expect(without.locator(".mini-strip")).toBeVisible();
    await expect(without.locator("img")).toHaveCount(0);
  });

  test("a picture that cannot be shown falls back to the strip instead of a broken image", async ({ page }) => {
    await page.route("**/docshots/img/s3.png", (r) => r.abort());
    await home(page);
    const card = page.getByRole("button", { name: "Continue Last Train" });
    await expect(card.locator(".mini-strip")).toBeVisible();
    await expect(card.locator("img")).toHaveCount(0);
  });
});

test.describe("the ready screen after an export", () => {
  const exportIt = async (page: Page, scene: string) => {
    await page.goto(`/docshots.html?scene=${scene}`);
    await calm(page);
    await page.getByRole("button", { name: "Export video" }).click();
  };

  test("a finished export says the film is ready and offers the vertical version, which is a separate file", async ({ page }) => {
    await exportIt(page, "exportsheet");
    const ready = page.locator(".export-ready");
    await expect(ready).toContainText("Your film is ready.");
    await expect(ready).toContainText("2:24");
    await expect(ready).toContainText("The film above is not changed. Free: it is made on this computer.");
    await ready.getByRole("button", { name: "Also make a vertical version for phones" }).click();
    await expect(ready.locator(".export-extra")).toContainText("The vertical version is ready — 1080×1920");
    await expect(ready.locator(".export-extra")).toContainText("TikTok");
    await expect(ready.getByRole("button", { name: /Also make a vertical version/ })).toHaveCount(0);
    await expect(ready.getByRole("button", { name: "Show the film in its folder" })).toBeVisible();
  });

  test("exporting again clears the vertical version, and a draft is not called ready", async ({ page }) => {
    await exportIt(page, "exportsheet");
    await page.getByRole("button", { name: "Also make a vertical version for phones" }).click();
    await expect(page.locator(".export-extra")).toBeVisible();
    await page.getByRole("button", { name: "Export again" }).click();
    await expect(page.locator(".export-ready")).toContainText("Your film is ready.");
    await expect(page.locator(".export-extra")).toHaveCount(0);
    await exportIt(page, "exportdraft");
    await expect(page.getByText(/Exported draft/)).toBeVisible();
    await expect(page.locator(".export-ready")).toHaveCount(0);
  });

  test("the ready screen has no accessibility violations", async ({ page }) => {
    await exportIt(page, "exportsheet");
    await expect(page.locator(".export-ready")).toBeVisible();
    await page.waitForTimeout(400);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(r.violations.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
  });
});

test.describe("a season made into films", () => {
  test("asks first, says plainly that it is free and what happens next, and reports what it made", async ({ page }) => {
    await page.goto("/docshots.html?scene=presets");
    await calm(page);
    await page.getByRole("tab", { name: "Series plan" }).click();
    await page.getByLabel("Your idea, in a sentence or two").fill("A young nurse discovers her hospital is hiding a name.");
    await page.getByRole("button", { name: "Make the plan (free)" }).click();
    const make = page.getByRole("button", { name: "Make the 10 episode films (free)" });
    await expect(make).toBeVisible();
    await make.click();
    const ask = page.getByRole("alertdialog");
    await expect(ask).toContainText("Make 10 films, one for each episode?");
    await expect(ask).toContainText("It is free: nothing is generated and nothing is charged");
    await ask.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText(/Made 10 films/)).toHaveCount(0);
    await make.click();
    await page.getByRole("alertdialog").getByRole("button").last().click();
    await expect(page.getByRole("status").filter({ hasText: "Made 10 films" })).toContainText("the price shown first");
    await expect(page.locator(".ps-ep")).toHaveCount(10);                                           // the plan itself is still there, unchanged
  });
});

test.describe("finding the screen colour", () => {
  test("a button finds the colour, sets it and says what it found", async ({ page }) => {
    await page.goto("/docshots.html?scene=layerclip");
    await calm(page);
    await page.locator("details.ly-mix summary").click();
    const mix = page.locator("details.ly-mix");
    await expect(mix.getByRole("button", { name: "Find the screen colour" })).toHaveCount(0);        // only once a colour is being cut out
    await mix.getByLabel("Cut out a colour (a green screen)").check();
    await mix.getByRole("button", { name: "Find the screen colour" }).click();
    await expect(mix.getByRole("status")).toContainText("Found a green screen. Its colour is set.");
    await expect(mix.getByLabel("Colour to remove")).toHaveValue("#1fae4b");
  });
});
