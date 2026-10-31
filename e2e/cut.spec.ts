import { expect, test, type Page } from "@playwright/test";

// Driven on the screenshot harness (a made-up film held in memory): the timeline's cut lane, its toolbar and its keys are the real ones; the cut's backend is a small stand-in for the engine
// (whose own tests prove every edit, frame by frame). Nothing is rendered or charged.
const open = async (page: Page) => {
  await page.goto("/docshots.html?scene=cutedit");
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.evaluate(() => document.body.classList.remove("docshot"));
  await expect(page.getByRole("group", { name: "The cut" })).toBeVisible();
};
const clearToast = async (page: Page) => { await page.locator(".toast button", { hasText: "OK" }).click({ timeout: 2500 }).catch(() => {}); };   // the harness has no soundtrack file, so the player says it cannot play it
const clips = (page: Page) => page.locator(".tl-clipbody");
const names = (page: Page) => clips(page).evaluateAll((b) => b.map((x) => x.getAttribute("aria-label") ?? ""));
/** Put the playhead at a time by clicking the timeline's waveform row. */
const seek = async (page: Page, seconds: number) => {
  const first = await clips(page).first().boundingBox();
  const width = (await page.locator(".tl-clip").first().boundingBox())!.width;
  const pps = (width + 1) / 4.5;                                                  // the first shot is 4.5 s long
  const inner = (await page.locator(".tl-inner").boundingBox())!;
  await page.mouse.click(first!.x - 7 + seconds * pps, inner.y + 70);
};

test.describe("the cut lane", () => {
  test("shows the film's shots as clips with a toolbar, only in Edit mode", async ({ page }) => {
    await open(page);
    expect(await clips(page).count()).toBe(5);
    await expect(page.getByText(/As planned/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Film strip" }).click();
    await expect(page.getByRole("group", { name: "The cut" })).toHaveCount(0);
  });

  test("S cuts the chosen clip at the playhead and Ctrl+Z puts it back", async ({ page }) => {
    await open(page);
    await clips(page).first().click();
    await seek(page, 2);
    await page.keyboard.press("s");
    await expect.poll(() => clips(page).count()).toBe(6);
    await expect(page.getByText(/Edited/)).toBeVisible();
    await page.keyboard.press("Control+z");
    await expect.poll(() => clips(page).count()).toBe(5);
    await page.keyboard.press("Control+Shift+z");
    await expect.poll(() => clips(page).count()).toBe(6);
    await page.keyboard.press("Control+y");                                        // nothing left to do again: the key is quiet, the count stays
    await expect.poll(() => clips(page).count()).toBe(6);
  });

  test("Delete takes a clip out and leaves a gap, and Undo brings it back", async ({ page }) => {
    await open(page);
    await clips(page).nth(1).click();
    await page.keyboard.press("Delete");
    await expect.poll(() => clips(page).count()).toBe(4);
    expect((await names(page)).some((n) => n.startsWith("S01-02"))).toBe(false);
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect.poll(() => clips(page).count()).toBe(5);
  });

  test("Q trims the start of the chosen clip to the playhead and shows how far in it now starts", async ({ page }) => {
    await open(page);
    await clips(page).nth(1).click();                                              // S01-02, 4.5 s to 7.5 s
    await seek(page, 5.5);
    await page.keyboard.press("q");
    await expect(page.locator(".tl-clipin").first()).toBeVisible();
    const m = (await names(page))[1].match(/^S01-02 from 0:(\d+\.\d+) for 0:(\d+\.\d+)$/)!;
    expect(Number(m[1])).toBeGreaterThan(5);                                          // it now starts where the playhead was...
    expect(Number(m[1]) + Number(m[2])).toBeCloseTo(7.5, 1);                          // ...and still ends where it did
  });

  test("dragging the end handle trims, and Escape cancels a drag", async ({ page }) => {
    await open(page);
    const clip = page.locator(".tl-clip").first();
    const b = (await clip.boundingBox())!;
    const handle = clip.locator(".tl-handle.out");
    const h = (await handle.boundingBox())!;
    await page.mouse.move(h.x + 3, h.y + h.height / 2);
    await page.mouse.down();
    await page.mouse.move(h.x - 60, h.y + h.height / 2, { steps: 6 });
    await page.keyboard.press("Escape");
    await page.mouse.up();
    expect((await clip.boundingBox())!.width).toBeCloseTo(b.width, 0);              // nothing changed
    await page.mouse.move(h.x + 3, h.y + h.height / 2);
    await page.mouse.down();
    await page.mouse.move(h.x - 60, h.y + h.height / 2, { steps: 6 });
    await page.mouse.up();
    await expect.poll(async () => (await clip.boundingBox())!.width).toBeLessThan(b.width - 40);
  });

  test("B puts a marker at the playhead and Delete on it takes it away", async ({ page }) => {
    await open(page);
    await clips(page).first().click();
    await seek(page, 3);
    await page.keyboard.press("b");
    const marker = page.locator(".tl-marker");
    await expect(marker).toHaveCount(1);
    await marker.focus();
    await page.keyboard.press("Delete");
    await expect(marker).toHaveCount(0);
    expect(await clips(page).count()).toBe(5);                                      // Delete on a marker did not also take a clip out
  });

  test("a locked track refuses edits and says so, and the keyboard can nudge a clip", async ({ page }) => {
    await open(page);
    await clearToast(page);
    await page.getByRole("group", { name: "The cut" }).getByText("More", { exact: true }).click();
    await page.getByRole("button", { name: "Lock the track" }).click();
    await clips(page).first().click();
    await page.keyboard.press("s");
    await expect(page.locator(".tl-cuterr")).toContainText(/locked/);
    await page.getByRole("group", { name: "The cut" }).getByText("More", { exact: true }).click();                                // the menu closes after each choice
    await page.getByRole("button", { name: "Unlock the track" }).click();
    await clips(page).first().focus();
    await page.keyboard.press("Alt+ArrowRight");                                   // clips touch, so there is no room: it says why
    await expect(page.locator(".tl-cuterr")).toContainText(/no room/);
  });
});
