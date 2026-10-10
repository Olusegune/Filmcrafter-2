import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";

const html = readFileSync("public/splash.html", "utf8");
const rust = readFileSync("src-tauri/src/lib.rs", "utf8");
const caps = readFileSync("src-tauri/capabilities/default.json", "utf8");

describe("the splash screen", () => {
  it("stays long enough to read: at least four seconds in the app, and its hairline runs for the same time", () => {
    const ms = Number(rust.match(/const SPLASH_MIN: std::time::Duration = std::time::Duration::from_millis\((\d+)\)/)![1]);
    expect(ms).toBeGreaterThanOrEqual(4000);
    const secs = Number(html.match(/animation: run ([\d.]+)s linear forwards/)![1]);
    expect(secs * 1000).toBe(ms);
  });

  it("has a close button and a button for the guide, both named for screen readers and softly rounded like the rest", () => {
    expect(html).toContain('id="x" type="button" aria-label="Close this and open the app"');
    expect(html).toContain('id="guide" type="button"');
    expect(html).toContain("Open the guide");
    expect(html).toMatch(/\.x, \.guide \{[^}]*border-radius: 6px/);
  });

  it("asks the app to close it, with or without opening the guide, and Escape closes it too", () => {
    expect(html).toContain('invoke("splash_close", { guide: !!guide })');
    expect(html).toContain('closeSplash(false)');
    expect(html).toContain('closeSplash(true)');
    expect(html).toContain('e.key === "Escape"');
  });

  it("does nothing if it is opened outside the app (no app to ask)", () => {
    expect(html).toMatch(/try \{ window\.__TAURI_INTERNALS__\.invoke\([^)]*\); \} catch \(e\) \{\}/);
  });

  it("the app lets the splash window ask, and has the command that closes it", () => {
    expect(caps).toContain('"splashscreen"');
    expect(rust).toContain("fn splash_close(");
    expect(rust).toMatch(/generate_handler!\[[^\]]*splash_close/);
  });

  it("closing it early waits for the main window rather than leaving nothing on screen", () => {
    expect(rust).toContain("while started.elapsed() < SPLASH_MIN && !SPLASH_SKIP.load(Ordering::Relaxed)");
    expect(rust).toContain("OPEN_GUIDE.swap(false, Ordering::Relaxed)");
  });

  it("the guide button opens the same documentation as the Help menu (the menu event the window already handles)", () => {
    const app = readFileSync("src/App.tsx", "utf8");
    expect(app).toContain('case "help": setHelp(true)');
    expect(rust.match(/app\.emit\("menu", "help"\)/g)!.length).toBe(2);                    // after the window is drawn, and when the splash is closed late
    expect(rust).not.toContain('app.emit("menu", "docs")');
  });

  it("respects reduced motion: the hairline does not run", () => {
    expect(html).toMatch(/prefers-reduced-motion: reduce\) \{ \.bar \{ animation: none/);
  });

  it("is FilmCrafter's alone: its own artwork, and nothing from the music app (its steps picture, its tagline, its images)", () => {
    expect(html).toContain('url("splash.jpg")');
    expect(html).not.toMatch(/onboarding\/|splash_steps|splash_scene|splash_dark|music into motion|v-steps/i);
    expect(existsSync("public/splash.jpg")).toBe(true);
    for (const f of ["splash_steps.jpg", "splash_scene.jpg", "splash_dark.jpg"]) expect(existsSync("public/onboarding/" + f)).toBe(false);
  });

  it("keeps the film strip still with reduced motion", () => {
    expect(html).toContain(".track, .reel { animation: none !important; }");
  });
});
