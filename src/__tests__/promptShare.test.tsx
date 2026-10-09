import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { budgetNote, budgetOf, groupOf, type PromptBlock } from "../promptShare";
import { PromptBudget } from "../PromptBudget";

const b = (text: string, kept = true, priority = 8): PromptBlock => ({ text, kept, priority });

describe("where the prompt's words go", () => {
  it("sorts blocks by what they are for", () => {
    expect(groupOf("Close on Beatrice touching her glasses.", true)).toBe("acting");
    expect(groupOf("Emotion: embarrassed realization, played heightened and visible. Performance: she touches the frame.")).toBe("acting");
    expect(groupOf("Play it truthfully: motivated small gestures.")).toBe("acting");
    expect(groupOf("Beatrice says: \"I knew that.\" The words are clearly voiced.")).toBe("acting");
    expect(groupOf("Choreography: Royal Arrival")).toBe("acting");
    expect(groupOf("Characters: Beatrice; Zara.")).toBe("locks");
    expect(groupOf("Locked design, keep exactly: Beatrice: 60.")).toBe("locks");
    expect(groupOf("References: the first reference image is the approved keyframe.")).toBe("locks");
    expect(groupOf("Blocking (keep across the scene): Beatrice screen-left.")).toBe("locks");
    expect(groupOf("Always: Same home geometry.")).toBe("locks");
    expect(groupOf("Camera: close shot; 75 mm.")).toBe("camera");
    expect(groupOf("Lighting: warm.")).toBe("camera");
    expect(groupOf("Look: Match the visual style.")).toBe("style");
    expect(groupOf("World: A warm stylized 3D Afrobeat family satire.")).toBe("style");
    expect(groupOf("No on-screen text, no subtitles, no watermark.")).toBe("rules");
  });

  it("adds up what is sent and counts what was dropped", () => {
    const r = budgetOf([b("A".repeat(100), true, 10), b("Locked design, keep exactly: " + "x".repeat(70)), b("Camera: " + "y".repeat(42)), b("Look: dropped", false, 3)]);
    expect(r.total).toBe(100 + 99 + 50);
    expect(r.dropped).toBe(1);
    const pct = Object.fromEntries(r.shares.map((s) => [s.id, s.pct]));
    expect(pct.acting).toBe(40);
    expect(pct.locks).toBe(40);
    expect(pct.camera).toBe(20);
    expect(pct.style).toBe(0);                                              // the dropped Look block is not counted
  });

  it("says so when the acting is buried, and when blocks were left out", () => {
    const buried = budgetOf([b("Short action.", true, 10), b("Locked design, keep exactly: " + "x".repeat(400)), b("World: " + "w".repeat(300))]);
    expect(budgetNote(buried)).toContain("is what happens and how it is played");
    const fine = budgetOf([b("A".repeat(300), true, 10), b("Camera: close.")]);
    expect(budgetNote(fine)).toBe("");
    expect(budgetNote(budgetOf([b("a", true, 10), b("Look: x", false, 3)]))).toContain("left out to fit this model's length limit");
  });

  it("draws a bar and a legend, or nothing when there is no prompt", () => {
    expect(renderToStaticMarkup(<PromptBudget blocks={null} />)).toBe("");
    expect(renderToStaticMarkup(<PromptBudget blocks={[]} />)).toBe("");
    const html = renderToStaticMarkup(<PromptBudget blocks={[b("A".repeat(60), true, 10), b("Camera: " + "y".repeat(32))]} />);
    expect(html).toContain("Where the prompt&#x27;s words go");
    expect(html).toContain("Action and acting");
    expect(html).toContain('role="img"');
    expect(html).toContain('width:60%');
  });
});
