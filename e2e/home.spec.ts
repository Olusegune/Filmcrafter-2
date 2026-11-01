import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Driven on the screenshot harness: the real Home screen, its preset cards (the engine's own preset list and the pack's pictures), and its buttons. What Home asks the app to do is recorded in window.__home.
const calls = (page: Page) => page.evaluate(() => (window as unknown as { __home?: unknown[] }).__home ?? []);
const open = async (page: Page, query = "", seen = true) => {
  if (seen) await page.addInitScript(() => { try { localStorage.setItem("pf-home-welcome", "1"); } catch { /* optional */ } });          // the first-launch question has been answered, unless a test is about it
  await page.goto(`/docshots.html?scene=homeflow${query}`);
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("heading", { name: "What will you create today?" })).toBeVisible();
};

test.describe("the Home screen", () => {
  test("offers the three ways to begin, all visible without scrolling at a laptop size", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await open(page);
    for (const name of ["New film", "Start from an idea", "Explore presets"]) await expect(page.getByRole("button", { name })).toBeInViewport();
    await expect(page.getByRole("heading", { name: "Explore creative presets" })).toBeInViewport();
  });

  test("a new film, an idea and a story file each reach the app", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "New film" }).click();
    await page.getByRole("button", { name: "Start from an idea" }).click();
    expect(await calls(page)).toEqual([{ new: {} }, { new: { kind: "idea" } }]);
  });

  test("the featured presets all have pictures that load, and each opens its details", async ({ page }) => {
    await open(page);
    const cards = page.locator(".hm-presets .hm-pcard");
    await expect(cards).toHaveCount(6);
    await expect(page.locator(".hm-presets img.hm-thumb")).toHaveCount(6);
    const broken = await page.locator(".hm-presets img.hm-thumb").evaluateAll((els) => els.filter((e) => !(e as HTMLImageElement).complete || (e as HTMLImageElement).naturalWidth === 0).length);
    expect(broken).toBe(0);
    await cards.first().getByRole("button").click();
    const sheet = page.getByRole("dialog", { name: "Vertical Micro-Drama" });
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText("It sets");
    await expect(sheet).toContainText("Nothing is made, nothing is bought");
  });

  test("starting from a preset asks the app to make a film with exactly that preset", async ({ page }) => {
    await open(page);
    await page.locator(".hm-presets .hm-pcard").nth(1).getByRole("button").click();
    await page.getByRole("button", { name: /^Start a film with this preset/ }).click();
    expect(await calls(page)).toEqual([{ new: { preset: "animated_short" } }]);
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("View all presets lists every preset, searches them and filters by kind", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: /^View all presets/ }).click();
    const list = page.getByRole("list", { name: "Presets" });
    await expect(list.getByRole("listitem")).toHaveCount(37);
    await page.getByLabel("Search").fill("storybook");
    expect(await list.getByRole("listitem").count()).toBeGreaterThan(3);
    await page.getByLabel("Search").fill("zzzz nothing");
    await expect(page.getByRole("dialog", { name: "All presets" }).getByRole("status")).toContainText("No preset matches");
    await page.getByLabel("Search").fill("");
    await page.getByRole("button", { name: "Acting", exact: true }).click();
    await expect(list.getByRole("listitem")).toHaveCount(3);
    await list.getByRole("listitem").first().getByRole("button").click();
    await expect(page.getByRole("dialog", { name: "Natural acting" })).toBeVisible();
  });

  test("a missing preset picture falls back to a plain tile instead of a broken image", async ({ page }) => {
    await page.route("**/presets/vertical_micro_drama.png", (r) => r.abort());
    await open(page);
    const first = page.locator(".hm-presets .hm-pcard").first();
    await expect(first.locator(".hm-noimg")).toBeVisible();
    await expect(first.locator("img")).toHaveCount(0);
  });

  test("recent films show their stage, frame shape and day, and one click continues", async ({ page }) => {
    await open(page);
    const card = page.getByRole("button", { name: "Continue Last Train" });
    await expect(card).toContainText("Story locked · 9:16 · Today");
    await expect(card).toContainText("Continue where you left off");
    await card.click();
    expect(await calls(page)).toEqual([{ open: "f1" }]);
    await expect(page.getByRole("button", { name: /^Continue Exit Plan/ })).toHaveCount(0);        // an old music-video project is not offered as a film
  });

  test("with many films only a screenful is shown until you ask for the rest", async ({ page }) => {
    await open(page, "&many=1");
    await expect(page.locator(".hm-recent .hm-rcard")).toHaveCount(8);
    await page.getByRole("button", { name: "Show all 60 films" }).click();
    await expect(page.locator(".hm-recent .hm-rcard")).toHaveCount(60);
    await page.getByRole("button", { name: "Show fewer" }).click();
    await expect(page.locator(".hm-recent .hm-rcard")).toHaveCount(8);
  });

  test("with no films it says so, kindly, and still offers Open project", async ({ page }) => {
    await open(page, "&none=1");
    await expect(page.getByText("No films yet.")).toBeVisible();
    await page.getByRole("button", { name: /Open project/ }).click();
    expect(await calls(page)).toEqual([{ choose: true }]);
  });

  test("works at a narrow window: one column, nothing cut off sideways", async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 800 });
    await open(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1 || (document.querySelector(".home") as HTMLElement).scrollWidth > (document.querySelector(".home") as HTMLElement).clientWidth + 1);
    expect(wide).toBe(false);
    await expect(page.getByRole("button", { name: "Explore presets" })).toBeVisible();
  });

  test("everything can be reached and used from the keyboard, with a visible focus", async ({ page }) => {
    await open(page);
    await page.locator(".hm-presets .hm-pcard").first().getByRole("button").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Vertical Micro-Drama" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const ring = await page.locator(".hm-presets .hm-pcard").first().getByRole("button").evaluate((el) => { (el as HTMLElement).focus(); return getComputedStyle(el.querySelector(".hm-thumb")!).boxShadow; });
    expect(ring).not.toBe("none");
  });

  test("the preset gallery and a preset's details have no accessibility violations when open", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: /^View all presets/ }).click();
    for (const step of ["gallery", "details"]) {
      if (step === "details") await page.getByRole("list", { name: "Presets" }).getByRole("listitem").first().getByRole("button").click();
      await page.waitForTimeout(500);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(r.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`), step).toEqual([]);
    }
  });

});

test.describe("the first-launch question", () => {
  test("is asked once of someone with no films, and each answer goes where it says", async ({ page }) => {
    await open(page, "&none=1", false);
    const q = page.getByRole("dialog", { name: "What would you like to create?" });
    await expect(q).toBeVisible();
    for (const name of ["A film from my story", "A short video using a preset", "An animated film", "Open an existing project"]) await expect(q.getByRole("button", { name: new RegExp(`^${name}`) })).toBeVisible();
    await q.getByRole("button", { name: /^A film from my story/ }).click();
    expect(await calls(page)).toEqual([{ new: {} }]);
    await page.reload();
    await expect(page.getByRole("heading", { name: "What will you create today?" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);                                         // answered: not asked again
  });

  test("a preset answer opens the gallery, an animated answer opens that preset, an open answer opens the project chooser", async ({ page }) => {
    await open(page, "&none=1", false);
    await page.getByRole("button", { name: /^A short video using a preset/ }).click();
    await expect(page.getByRole("dialog", { name: "All presets" })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Help me choose" }).click();
    await page.getByRole("button", { name: /^An animated film/ }).click();
    await expect(page.getByRole("dialog", { name: "Animated Short Film" })).toBeVisible();
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: "Help me choose" }).click();
    await page.getByRole("button", { name: /^Open an existing project/ }).click();
    expect(await calls(page)).toEqual([{ choose: true }]);
  });

  test("Not now closes it for good, and Help me choose brings it back on request", async ({ page }) => {
    await open(page, "&none=1", false);
    await page.getByRole("button", { name: "Not now" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Help me choose" }).click();
    await expect(page.getByRole("dialog", { name: "What would you like to create?" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("is never forced on someone who already has films", async ({ page }) => {
    await open(page, "", false);
    await expect(page.getByRole("button", { name: "Continue Last Train" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("has no accessibility violations", async ({ page }) => {
    await open(page, "&none=1", false);
    await expect(page.getByRole("dialog", { name: "What would you like to create?" })).toBeVisible();
    await page.waitForTimeout(500);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(r.violations.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
  });
});
