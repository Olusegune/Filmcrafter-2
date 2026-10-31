import { expect, test, type Page } from "@playwright/test";

// Driven on the screenshot harness (two made-up suggestions held in memory): the sheet, its buttons and its wording are the real ones; the rules and the previews are proved in the engine's own tests.
const open = async (page: Page) => {
  await page.goto("/docshots.html?scene=smarteditor");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("heading", { name: /Smart Editor/ })).toBeVisible();
};

test.describe("the Smart Editor", () => {
  test("each suggestion says what, why and which clips, and what was left alone on purpose", async ({ page }) => {
    await open(page);
    const card = page.getByRole("listitem", { name: "Tighten the end of S01-01" });
    await expect(card).toContainText("What:");
    await expect(card).toContainText("Why:");
    await expect(card).toContainText("Clips: S01-01");
    await expect(card).toContainText("Saves 1.0 s");
    await expect(page.getByRole("listitem", { name: "Give S01-02 a little more time" })).toContainText("Adds 0.6 s");
    await expect(page.getByRole("region", { name: "Left alone on purpose" })).toContainText("Kept the pause at the end of S02-01");
  });

  test("Preview shows a before and an after, and nothing is accepted by looking", async ({ page }) => {
    await open(page);
    await page.getByRole("listitem", { name: "Tighten the end of S01-01" }).getByRole("button", { name: "Preview before and after" }).click();
    await expect(page.getByLabel("Before", { exact: true })).toBeVisible();
    await expect(page.getByLabel("After the suggestion")).toBeVisible();
    await expect(page.getByRole("listitem", { name: "Tighten the end of S01-01" })).toBeVisible();
  });

  test("Accept does it and says how to undo it; Not this one keeps it away", async ({ page }) => {
    await open(page);
    await page.getByRole("listitem", { name: "Tighten the end of S01-01" }).getByRole("button", { name: "Accept" }).click();
    await expect(page.getByRole("status").filter({ hasText: /Done: Tighten the end of S01-01/ })).toContainText("Ctrl+Z");
    await page.getByRole("listitem", { name: "Give S01-02 a little more time" }).getByRole("button", { name: "Not this one" }).click();
    await expect(page.getByRole("listitem", { name: "Give S01-02 a little more time" })).toHaveCount(0);
    await expect(page.getByText(/Left out\. It will not be suggested again/)).toBeVisible();
  });

  test("a request in plain words is read, and one it cannot do is said plainly", async ({ page }) => {
    await open(page);
    await page.getByLabel("Or ask in your own words").fill("tighten this scene");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText(/Tightening: ending spoken clips/)).toBeVisible();
    await expect(page.getByRole("listitem", { name: "Give S01-02 a little more time" })).toHaveCount(0);
    await page.getByLabel("Or ask in your own words").fill("make this transition cinematic");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText(/did not understand that as something I can do yet/)).toBeVisible();
  });

  test("styles that are not built are shown and cannot be chosen", async ({ page }) => {
    await open(page);
    await expect(page.getByRole("option", { name: "Suspense and anticipation (not built yet)" })).toHaveAttribute("disabled", "");
  });
});
