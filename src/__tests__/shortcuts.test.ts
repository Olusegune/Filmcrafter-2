import { describe, expect, it } from "vitest";
import doc from "../../docs/GETTING_STARTED.md?raw";
import { SHORTCUTS, find, isTyping, isTypingKey, matches } from "../shortcuts";

const key = (key: string, extra: Partial<KeyboardEvent> = {}) =>
  ({ key, code: key === " " ? "Space" : key.length === 1 ? `Key${key.toUpperCase()}` : key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra }) as KeyboardEvent;

describe("shortcuts", () => {
  it("never gives two shortcuts the same key", () => {
    const seen = new Map<string, string>();
    for (const s of SHORTCUTS) {
      expect(seen.get(s.spec), `${s.id} repeats ${s.spec}`).toBeUndefined();
      seen.set(s.spec, s.id);
    }
  });

  it("does not treat Ctrl+R, Ctrl+A or Ctrl+F as re-render, approve or full screen", () => {
    expect(find(key("r", { ctrlKey: true }))).toBeNull();
    expect(find(key("a", { metaKey: true }))).toBeNull();
    expect(find(key("f", { altKey: true }))).toBeNull();
    expect(find(key("r"))?.id).toBe("rerender");
  });

  it("tells m from Shift+M, and finds ? with Shift held", () => {
    expect(find(key("m"))?.id).toBe("mute");
    expect(find(key("M", { shiftKey: true }))?.id).toBe("shot_sound");
    expect(find(key("?", { shiftKey: true }))?.id).toBe("keys");
    expect(find(key("/", { ctrlKey: true }))?.id).toBe("keys");
  });

  it("maps J, K, L and the arrows", () => {
    expect(find(key("j"))?.id).toBe("back5");
    expect(find(key("k"))?.id).toBe("play_k");
    expect(find(key("l"))?.id).toBe("fwd5");
    expect(find(key("ArrowLeft"))?.id).toBe("prev");
    expect(find(key("ArrowLeft", { shiftKey: true }))?.id).toBe("back5s");
    expect(find(key(" "))?.id).toBe("play");
  });

  it("leaves plain keys and Ctrl+Z to a text box but keeps Ctrl+K", () => {
    expect(find(key("a"), { typing: true })).toBeNull();
    expect(find(key("z", { ctrlKey: true }), { typing: true })).toBeNull();
    expect(find(key("z", { ctrlKey: true }))?.id).toBe("undo");
    expect(find(key("Z", { ctrlKey: true, shiftKey: true }))?.id).toBe("redo");
    expect(find(key("y", { ctrlKey: true }))?.id).toBe("redo_y");
    expect(find(key("k", { ctrlKey: true }), { typing: true })?.id).toBe("command");
    expect(isTyping({ tagName: "INPUT" } as unknown as EventTarget)).toBe(true);
    expect(isTyping({ tagName: "SELECT" } as unknown as EventTarget)).toBe(true);
    expect(isTyping({ tagName: "BUTTON" } as unknown as EventTarget)).toBe(false);
  });

  it("matches a comma shortcut", () => {
    expect(matches(key(",", { ctrlKey: true }), "Mod+,")).toBe(true);
  });

  it("is the table in the documentation", () => {
    const table = doc.slice(doc.indexOf("## Keyboard shortcuts"));
    for (const s of SHORTCUTS) expect(table, `${s.label} (${s.keys}) is missing from docs/GETTING_STARTED.md`).toContain(`\`${s.keys}\``);
  });
});

describe("keys while a slider has focus", () => {
  const slider = { tagName: "INPUT", type: "range" } as unknown as EventTarget;
  const text = { tagName: "INPUT", type: "text" } as unknown as EventTarget;
  it("lets Space, J and K through after the scrub bar was dragged, but leaves a slider its own arrow keys", () => {
    expect(isTypingKey({ target: slider, key: " " })).toBe(false);
    expect(isTypingKey({ target: slider, key: "j" })).toBe(false);
    for (const k of ["ArrowLeft", "ArrowRight", "Home", "End", "PageUp"]) expect(isTypingKey({ target: slider, key: k })).toBe(true);
  });
  it("still treats a text box as typing for every key", () => {
    expect(isTypingKey({ target: text, key: " " })).toBe(true);
    expect(isTypingKey({ target: text, key: "j" })).toBe(true);
  });
});
