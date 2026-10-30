import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// The new screens are driven on the screenshot harness (docshots.html), which answers the app's backend calls with made-up data held in memory: no engine, no provider, nothing is charged.
// The harness page hosts the real inspector (header, tabs and Shot tab) with the real "Look for this shot" panel and the real look picker.
const scene = (name: string) => `/docshots.html?scene=${name}`;

async function openShotTab(page: import("@playwright/test").Page, name = "shotlook") {
  await page.goto(scene(name));
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));              // the harness un-scrolls long lists so a screenshot shows them whole; the app scrolls them inside the sheet
  await expect(page.locator(".inspector-head")).toBeVisible();
  await page.locator(".insp-tabs").getByRole("tab", { name: "Shot" }).click();        // the inspector remembers the last tab it was on: click the Shot tab first
}

test.describe("a look for one shot", () => {
  test("the Shot tab sets and clears a look for that shot, and the header chip follows", async ({ page }) => {
    await openShotTab(page);
    const chip = page.locator(".look-chip");
    await expect(chip).toHaveText("Claymation");
    await expect(chip).not.toHaveClass(/gold/);
    await page.getByText("Look for this shot", { exact: true }).click();              // the panel is folded until the shot has a look of its own
    const pick = page.getByRole("combobox", { name: "Look for this shot" });
    await expect(pick).toHaveValue("");
    await expect(pick.locator("option").first()).toHaveText("Same as its film (Claymation)");
    await pick.selectOption("anime");
    await expect(pick).toHaveValue("anime");
    await expect(chip).toHaveText("Shonen action anime");
    await expect(chip).toHaveClass(/gold/);
    await expect(page.getByText(/The whole picture is made in this look, the characters too/)).toBeVisible();
    const keep = page.getByLabel(/Keep the characters as they look in the film/);
    await expect(keep).not.toBeChecked();
    await keep.check();
    await expect(page.getByText(/Only the world is made in this look; the characters keep their own look/)).toBeVisible();
    await keep.uncheck();
    await pick.selectOption("");                                                       // the first option takes the look away again
    await expect(pick).toHaveValue("");
    await expect(chip).toHaveText("Claymation");
    await expect(chip).not.toHaveClass(/gold/);
  });

  test("a shot that already has a look of its own opens its panel, and the look-changed note never offers a render without a price", async ({ page }) => {
    await openShotTab(page, "shotlook-own");
    await expect(page.getByRole("combobox", { name: "Look for this shot" })).toHaveValue("anime");
    const note = page.locator(".flag", { hasText: "The video's look changed after this shot was made" });
    await expect(note).toBeVisible();
    await expect(note).toContainText("the price is shown first");
    await expect(note.getByRole("button", { name: "make a new take" })).toBeVisible();   // it only points at the Video tab; nothing is queued from here
  });

  test("the Look chip opens the picker for this shot only", async ({ page }) => {
    await openShotTab(page, "shotlook-own");
    await page.locator(".look-chip").click();
    const dialog = page.getByRole("dialog", { name: "Choose a look for shot S01-04" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("a new take shows its price first")).toBeVisible();
    await expect(dialog.getByLabel(/Your notes/)).toHaveCount(0);                      // the film's notes belong to the film's look
    await dialog.getByRole("button", { name: /^Same as its film/ }).click();           // back to what the shot inherits
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".look-chip")).toHaveText("Claymation");
    await page.locator(".look-chip").click();
    await dialog.getByRole("radio", { name: /Film noir/ }).click();
    await dialog.getByRole("button", { name: /^Use Film noir/ }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".look-chip")).toHaveClass(/gold/);
  });

  test("Escape closes the picker and changes nothing", async ({ page }) => {
    await openShotTab(page);
    await page.locator(".look-chip").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".look-chip")).toHaveText("Claymation");
  });

  test("nothing here can be reached by a render: no button on the panel or the picker says render, generate or make", async ({ page }) => {
    await openShotTab(page, "shotlook-own");
    await page.locator(".look-chip").click();
    const names = await page.getByRole("dialog").getByRole("button").allInnerTexts();
    expect(names.join(" ").toLowerCase()).not.toMatch(/render|generate|make a/);
  });
});

test.describe("accessibility of the new screens", () => {
  for (const name of ["shotlook-own", "shotlookpicker"]) {
    test(`${name} has no WCAG A or AA violations`, async ({ page }) => {
      await openShotTab(page, name === "shotlookpicker" ? "shotlook" : name);
      if (name === "shotlookpicker") await page.locator(".look-chip").click();
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    });
  }
});
