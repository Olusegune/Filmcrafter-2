import { expect, test, type Page } from "@playwright/test";

// Driven on the screenshot harness: the sheet, its cards, its word boxes and its buttons are the real ones; the pictures here are sample stills (the engine draws the real previews from your words, and its own
// tests check them). Nothing is rendered or charged.
const open = async (page: Page) => {
  await page.goto("/docshots.html?scene=motion");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("heading", { name: /^Motion graphics/ })).toBeVisible();
};

test.describe("the motion graphics sheet", () => {
  test("shows the eight built-in ones with a picture, what each is for, and how long it lasts", async ({ page }) => {
    await open(page);
    await expect(page.locator(".mg-card")).toHaveCount(8);
    const lt = page.getByRole("listitem", { name: "Lower third" });
    await expect(lt).toContainText("A name and a role at the bottom of the picture");
    await expect(lt).toContainText("4.5 s · 4 layers");
    await expect(lt.getByRole("img", { name: "How Lower third looks" })).toBeVisible();
  });

  test("choosing one shows its word boxes, and typing changes only that one's words", async ({ page }) => {
    await open(page);
    await page.getByRole("listitem", { name: "Title card" }).getByRole("button").click();
    const side = page.getByRole("complementary", { name: "Title card words" });
    await expect(side.getByLabel("Title")).toHaveValue("The Last Train");
    await side.getByLabel("Title").fill("Night Shift");
    await page.getByRole("listitem", { name: "Lower third" }).getByRole("button").click();
    await expect(page.getByRole("complementary", { name: "Lower third words" }).getByLabel("Name")).toHaveValue("Sarah Okafor");
    await page.getByRole("listitem", { name: "Title card" }).getByRole("button").click();
    await expect(page.getByRole("complementary", { name: "Title card words" }).getByLabel("Title")).toHaveValue("Night Shift");
  });

  test("Add puts it at the playhead, says what was made, and Take it away undoes just that", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Add at the playhead (12.3 s)" }).click();
    const done = page.getByRole("status").filter({ hasText: /^Added Lower third/ });
    await expect(done).toContainText("4 layers from 12.3 s");
    await done.getByRole("button", { name: "Take it away again" }).click();
    await expect(page.getByRole("status").filter({ hasText: /^Added/ })).toHaveCount(0);
  });

  test("a word limit holds, and the sheet says the picture is how it looks once settled", async ({ page }) => {
    await open(page);
    const name = page.getByRole("complementary", { name: "Lower third words" }).getByLabel("Name");
    await name.fill("x".repeat(100));
    expect((await name.inputValue()).length).toBe(60);
    await expect(page.getByText(/once it has settled/)).toBeVisible();
  });
});
