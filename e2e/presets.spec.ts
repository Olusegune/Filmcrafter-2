import { expect, test, type Page } from "@playwright/test";

// Driven on the screenshot harness: the sheet, its cards (with the preset pack's own thumbnails), the stacking, the preview table and the "yours is kept" rule are the real ones; the harness works the same
// rules out in a few lines so the sheet can be tried, and the engine's own tests prove the real ones. Nothing is rendered or charged.
const open = async (page: Page) => {
  await page.goto("/docshots.html?scene=presets");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("heading", { name: /^Presets/ })).toBeVisible();
};
const card = (page: Page, name: string) => page.getByRole("listitem", { name, exact: true });

test.describe("the presets sheet", () => {
  test("shows the library with the pack's thumbnails, and search and filters narrow it", async ({ page }) => {
    await open(page);
    await expect(page.locator(".ps-card")).toHaveCount(37);
    await expect(card(page, "Vertical Micro-Drama").locator("img")).toBeVisible();
    await page.getByLabel("Search").fill("storybook");
    await expect.poll(() => page.locator(".ps-card").count()).toBeGreaterThanOrEqual(7);
    await page.getByLabel("Search").fill("");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await expect(page.locator(".ps-card")).toHaveCount(3);
    await page.getByRole("button", { name: "Mine", exact: true }).click();
    await expect(page.getByText("No preset matches.")).toBeVisible();
  });

  test("a preset is added to the stack, previewed, and a choice of yours is kept unless you tick it", async ({ page }) => {
    await open(page);
    await card(page, "Vertical Micro-Drama").getByRole("button", { name: "Add to stack" }).click();
    await card(page, "Cinematic Storybook 2.5D").getByRole("button", { name: "Add to stack" }).click();
    const stack = page.getByRole("complementary", { name: "Your stack" });
    await expect(stack.locator(".ps-order li")).toHaveCount(2);
    await stack.getByRole("button", { name: "Preview what this changes" }).click();
    const plan = stack.getByRole("region", { name: "What would change" });
    await expect(plan.getByRole("row", { name: /Visual style/ })).toContainText("Yours, kept");
    await expect(plan.getByRole("row", { name: /Visual style/ })).toContainText("claymation");
    await expect(plan.getByRole("row", { name: /Acting/ })).toContainText("New");
    await expect(plan.getByRole("row", { name: /Delivery/ })).toContainText("vertical version, captions on, 20% kept clear");
    await expect(plan).toContainText("Your film keeps its own shape");
    await plan.getByLabel("Replace mine").check();
    await expect(plan.getByRole("row", { name: /Visual style/ })).toContainText("Replace mine");
    await plan.getByLabel("Replace mine").uncheck();
    await plan.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByRole("status").filter({ hasText: /^Applied:/ })).toContainText("Kept yours: Visual style");
    await stack.getByRole("button", { name: "Undo the last application" }).click();
    await expect(page.getByRole("status").filter({ hasText: /^Put back:/ })).toBeVisible();
  });

  test("the stack can be reordered and a preset taken out, and nothing is applied by looking", async ({ page }) => {
    await open(page);
    await card(page, "Documentary / Interview").getByRole("button", { name: "Add to stack" }).click();
    await card(page, "Mini Story").getByRole("button", { name: "Add to stack" }).click();
    const stack = page.getByRole("complementary", { name: "Your stack" });
    await stack.getByRole("button", { name: "Move Mini Story earlier" }).click();
    await expect(stack.locator(".ps-order li").first()).toContainText("Mini Story");
    await stack.getByRole("button", { name: "Take Mini Story out of the stack" }).click();
    await expect(stack.locator(".ps-order li")).toHaveCount(1);
    await stack.getByRole("button", { name: "Preview what this changes" }).click();
    await expect(stack.getByRole("button", { name: "Undo the last application" })).toBeDisabled();
  });

  test("a favourite is marked and your own preset is kept and found under Mine", async ({ page }) => {
    await open(page);
    await card(page, "Documentary / Interview").getByRole("button", { name: /Mark Documentary \/ Interview as a favorite/ }).click();
    await page.getByRole("button", { name: "Favorites", exact: true }).click();
    await expect(page.locator(".ps-card")).toHaveCount(1);
    await page.getByRole("button", { name: "All", exact: true }).click();
    await card(page, "Mini Story").getByRole("button", { name: "Add to stack" }).click();
    const stack = page.getByRole("complementary", { name: "Your stack" });
    await stack.getByLabel("Keep this as my own preset").fill("My quick story");
    await stack.getByRole("button", { name: "Keep", exact: true }).click();
    await page.getByRole("button", { name: "Mine", exact: true }).click();
    await expect(card(page, "My quick story")).toBeVisible();
  });

  test("the series plan is made from an idea, marks what is a suggestion, and what you write becomes yours", async ({ page }) => {
    await open(page);
    await page.getByRole("tab", { name: "Series plan" }).click();
    await page.getByLabel("Your idea, in a sentence or two").fill("A young nurse discovers her hospital is hiding a name.");
    await page.getByRole("button", { name: "Make the plan (free)" }).click();
    await expect(page.locator(".ps-ep")).toHaveCount(10);
    await expect(page.getByText(/a plan to edit, not a story written for you/)).toBeVisible();
    const first = page.locator(".ps-ep").first();
    await first.getByText("Episode 1: the hook").click();
    const hook = first.getByLabel("Hook", { exact: true });
    await expect(first.locator(".ps-badge").first()).toHaveText("Suggestion");
    await hook.fill("A name on a chart that is not hers.");
    await first.getByRole("button", { name: "Save" }).first().click();
    await expect(first.locator(".ps-badge").first()).toHaveText("Yours");
    await page.getByRole("button", { name: "Check the plan" }).click();
    await expect(page.getByRole("region", { name: "Plan check" })).toContainText("1 of 10 episodes have something you wrote");
  });

  test("the vertical tab says the film keeps its shape, and a slider chooses what a phone version keeps of a shot", async ({ page }) => {
    await open(page);
    await page.getByRole("tab", { name: "Vertical version" }).click();
    await expect(page.getByText(/Your film keeps its own shape/)).toBeVisible();
    const s = page.getByLabel("S01-01", { exact: true });
    await s.focus();
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
    await expect(page.locator("output").filter({ hasText: "70%" })).toBeVisible();
    await s.dblclick();
    await expect(page.locator("output").filter({ hasText: "middle" }).first()).toBeVisible();
  });
});
