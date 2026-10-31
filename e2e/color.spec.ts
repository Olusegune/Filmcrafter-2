import { expect, test } from "@playwright/test";

// Driven on the screenshot harness (a made-up film held in memory): the grade, LUT and look controls are the real sheet; the preview pictures are two sample stills. Nothing is rendered or charged.
const open = async (page: import("@playwright/test").Page) => {
  await page.goto("/docshots.html?scene=color");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("heading", { name: /^Color/ })).toBeVisible();
};

test.describe("Color Studio", () => {
  test("a slider is saved as the grade of the scope you are on, and taken off again", async ({ page }) => {
    await open(page);
    const save = page.getByRole("button", { name: /^Save grade for/ });
    await expect(save).toBeDisabled();
    const ex = page.getByLabel("Exposure", { exact: true });
    await ex.focus();
    for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByRole("button", { name: /^Take the grade off the whole film/ })).toBeEnabled();
    await page.getByRole("button", { name: /^Take the grade off the whole film/ }).click();
    await expect(save).toBeDisabled();
    await expect(page.getByLabel("Exposure", { exact: true })).toHaveValue("0");
  });

  test("a grade goes on a scene without touching the film, and a double click puts a slider back to zero", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: /INT\. KITCHEN/ }).click();
    await expect(page.getByRole("heading", { name: "Grade for scene 1" })).toBeVisible();
    const c = page.getByLabel("Contrast", { exact: true });
    await c.focus();
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
    await expect(page.locator("output").filter({ hasText: "0.04" }).first()).toBeVisible();
    await c.dblclick();
    await expect(c).toHaveValue("0");
    await c.focus();
    await page.keyboard.press("ArrowRight");
    await page.getByRole("button", { name: /^Save grade for scene 1/ }).click();
    await page.getByRole("button", { name: "Whole film" }).click();
    await expect(page.getByLabel("Contrast", { exact: true })).toHaveValue("0");
  });

  test("a LUT made for another colour space is not applied, and says why", async ({ page }) => {
    await open(page);
    const pick = page.getByRole("combobox", { name: "Look", exact: true });
    await pick.selectOption({ label: "Log to Rec.709 (not for Rec.709)" });
    await expect(page.getByText(/expects Log pictures/)).toBeVisible();
    await expect(page.getByText(/not applied/).first()).toBeVisible();
    await page.getByRole("button", { name: /^Save grade for/ }).click();
    await expect(page.getByRole("alert")).toContainText(/expects log footage/);
  });

  test("a saved look is put on another scope with one press", async ({ page }) => {
    await open(page);
    const ex = page.getByLabel("Exposure", { exact: true });
    await ex.focus();
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
    await page.getByRole("button", { name: /^Save grade for/ }).click();
    await page.getByPlaceholder("Soft evening").fill("Evening");
    await page.getByRole("button", { name: /as a look$/ }).click();
    await page.getByRole("button", { name: /INT\. KITCHEN/ }).click();
    await page.getByRole("button", { name: "Put Evening on scene 1" }).click();
    await expect(page.getByLabel("Exposure", { exact: true })).not.toHaveValue("0");
  });
});
