import { expect, test } from "@playwright/test";

// Driven on the screenshot harness (made-up film held in memory): no engine, no provider, nothing is charged.
const scene = (name: string) => `/docshots.html?scene=${name}`;
const open = async (page: import("@playwright/test").Page, name: string) => {
  await page.goto(scene(name));
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
};

test.describe("the Performance Director", () => {
  test("a draft is kept as your own words, and can go back to the draft", async ({ page }) => {
    await open(page, "acting");
    await page.getByRole("tab", { name: /Scenes/ }).click();
    const purpose = page.getByLabel("What this scene is for").first();
    await expect(purpose).toHaveValue(/ask him to stay/);
    const row = page.locator(".pd-field").filter({ has: purpose });
    await expect(row.getByText("Draft")).toBeVisible();
    await row.getByRole("button", { name: "Keep this" }).click();
    await expect(row.getByText("Yours")).toBeVisible();
    await row.getByRole("button", { name: "Back to the draft" }).click();
    await expect(row.getByText("Draft")).toBeVisible();
  });

  test("a person's notes are saved for that person", async ({ page }) => {
    await open(page, "acting");
    await page.getByRole("tab", { name: /People/ }).click();
    const save = page.getByRole("button", { name: "Save Sarah" });
    await expect(save).toBeDisabled();
    await page.getByPlaceholder("Their longer goal.").first().fill("to be taken seriously");
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByPlaceholder("Their longer goal.").first()).toHaveValue("to be taken seriously");
  });

  test("the shot panel suggests beats for free and turns a direction on", async ({ page }) => {
    await open(page, "shotacting");
    await page.getByRole("button", { name: "Suggest beats (free)" }).click();
    await expect(page.locator(".beat-sum").first()).toBeVisible();                       // the details are folded; the summary line shows
    await expect(page.getByText(/Suggested automatically/).first()).toBeAttached();
    const btn = page.getByRole("button", { name: "More restrained" });
    await expect(btn).toHaveAttribute("aria-pressed", "false");
    await btn.click();
    await expect(page.getByRole("button", { name: /More restrained · ●/ })).toHaveAttribute("aria-pressed", "true");
  });

  test("a kind of character can be chosen, and the arc check can be dismissed", async ({ page }) => {
    await open(page, "acting");
    await page.getByRole("tab", { name: /People/ }).click();
    const kind = page.getByRole("combobox", { name: "What kind of character" });
    await kind.selectOption("robot");
    await expect(kind).toHaveValue("robot");
    await page.getByRole("tab", { name: /Style/ }).click();
    await page.getByText("Emotional arc", { exact: false }).first().click();
    await expect(page.getByText(/goes from calm \(2\/10\) to furious/)).toBeVisible();
    await page.getByRole("button", { name: /^Dismiss:/ }).click();
    await expect(page.getByText(/Nothing stands out/)).toBeVisible();
  });
});
