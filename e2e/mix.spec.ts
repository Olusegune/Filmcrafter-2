import { expect, test, type Page } from "@playwright/test";

// Driven on the screenshot harness: the Layers panel and its "Mix and effects" section are the real ones; the film behind them is made up (the engine's own tests check the pictures and the export).
const open = async (page: Page) => {
  await page.goto("/docshots.html?scene=layermix");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  const mix = page.locator("details.ly-mix");
  await expect(mix).toBeVisible();
  await mix.locator("summary").click();
  return mix;
};

test.describe("mix and effects on a layer", () => {
  test("starts closed and plain, and saying nothing is in use", async ({ page }) => {
    await page.goto("/docshots.html?scene=layermix");
    await expect(page.locator("details.ly-mix summary")).toHaveText("Mix and effects");
    await expect(page.locator("details.ly-mix")).not.toHaveAttribute("open", "");
  });

  test("choosing how it mixes is remembered, and the summary says it is in use", async ({ page }) => {
    const mix = await open(page);
    await mix.getByLabel("Mix with the picture").selectOption("multiply");
    await expect(page.locator("details.ly-mix summary")).toHaveText("Mix and effects (in use)");
    await expect(mix.getByLabel("Mix with the picture")).toHaveValue("multiply");
    await mix.getByLabel("Mix with the picture").selectOption("normal");
    await expect(page.locator("details.ly-mix summary")).toHaveText("Mix and effects");
  });

  test("a shape shows its size and softness only once chosen, and can be turned into a vignette", async ({ page }) => {
    const mix = await open(page);
    await expect(mix.getByLabel("Shape size")).toHaveCount(0);
    await mix.getByLabel("Show only through a shape").selectOption("ellipse");
    await expect(mix.getByLabel("Shape size")).toBeVisible();
    await mix.getByLabel("Hide the inside instead (a vignette)").check();
    await expect(mix.getByLabel("Hide the inside instead (a vignette)")).toBeChecked();
    await mix.getByLabel("Show only through a shape").selectOption("none");
    await expect(mix.getByLabel("Shape size")).toHaveCount(0);
  });

  test("a picture can have a colour cut out, with its controls appearing only then", async ({ page }) => {
    const mix = await open(page);
    await expect(mix.getByLabel("Colour to remove")).toHaveCount(0);
    await mix.getByLabel("Cut out a colour (a green screen)").check();
    await expect(mix.getByLabel("Colour to remove")).toBeVisible();
    await expect(mix.getByLabel("How much of it")).toBeVisible();
    await expect(mix.getByLabel("Take the colour off the edges")).toBeVisible();
    await mix.getByLabel("Cut out a colour (a green screen)").uncheck();
    await expect(mix.getByLabel("Colour to remove")).toHaveCount(0);
  });

  test("glow and blur are there for a picture, and the note says what the player does and does not show", async ({ page }) => {
    const mix = await open(page);
    await expect(mix.getByLabel("Glow", { exact: true })).toBeVisible();
    await expect(mix.getByLabel("Blur")).toBeVisible();
    await expect(mix.getByText(/The player shows how a layer mixes/)).toBeVisible();
  });
});

test.describe("a video clip layer", () => {
  const openClip = async (page: Page) => {
    await page.goto("/docshots.html?scene=layerclip");
    await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
    await page.evaluate(() => document.body.classList.remove("docshot"));
    await expect(page.getByLabel(/^Start the clip at/)).toBeVisible();
  };

  test("shows what a clip can be told: where to start, whether to loop, how wide and how opaque; and says its sound is not used", async ({ page }) => {
    await openClip(page);
    await expect(page.getByLabel("Start the clip at (seconds into it, of 12.4)")).toHaveValue("0");
    await expect(page.getByLabel("Play again from the start when it ends")).not.toBeChecked();
    await expect(page.getByLabel("Width")).toBeVisible();
    await expect(page.getByLabel("Opacity")).toBeVisible();
    await expect(page.getByText(/sound is not used/)).toBeVisible();
    await page.getByLabel("Play again from the start when it ends").check();
    await expect(page.getByLabel("Play again from the start when it ends")).toBeChecked();
    await page.getByLabel(/^Start the clip at/).fill("2.5");
    await page.getByLabel(/^Start the clip at/).blur();
    await expect(page.getByLabel(/^Start the clip at/)).toHaveValue("2.5");
  });

  test("offers a cut-out colour and a blend mode, but not the things a clip cannot do yet (rotate, scale, shadow, glow, blur, shapes)", async ({ page }) => {
    await openClip(page);
    for (const gone of ["Rotate", "Scale", "Soft shadow"]) await expect(page.getByLabel(gone, { exact: true })).toHaveCount(0);
    await page.locator("details.ly-mix summary").click();
    const mix = page.locator("details.ly-mix");
    await expect(mix.getByLabel("Mix with the picture")).toBeVisible();
    await expect(mix.getByLabel("Cut out a colour (a green screen)")).toBeVisible();
    for (const gone of ["Glow", "Blur", "Show only through a shape"]) await expect(mix.getByLabel(gone, { exact: true })).toHaveCount(0);
    await mix.getByLabel("Cut out a colour (a green screen)").check();
    await expect(mix.getByLabel("Colour to remove")).toBeVisible();
  });
});

