// The Studio's keyboard shortcuts, in one place: the key handler, the `?` sheet and the documentation table all read this list,
// so they cannot disagree (src/__tests__/shortcuts.test.ts checks the documentation against it).

export type ShortcutGroup = "Playback" | "Shots" | "Panels" | "Sound" | "Project";

export type Shortcut = {
  id: string;
  /** What is pressed, as `Mod+Shift+key`. `Mod` is Ctrl (Windows, Linux) or Cmd (Mac). Letters are lower case; others use KeyboardEvent.key or `Space`. */
  spec: string;
  /** What it is called in the sheet and the documentation. */
  keys: string;
  label: string;
  group: ShortcutGroup;
  /** Handled by the desktop menu bar, not the Studio's key handler (listed so the sheet is complete). */
  menu?: boolean;
  /** Still works while a text box has focus (Ctrl+K). Everything else leaves the box alone, so Ctrl+Z there undoes typing, not a layer. */
  typingOk?: boolean;
};

export const SHORTCUTS: Shortcut[] = [
  { id: "play", spec: "Space", keys: "Space", label: "Play / pause", group: "Playback" },
  { id: "play_k", spec: "k", keys: "K", label: "Play / pause (with J and L)", group: "Playback" },
  { id: "back5", spec: "j", keys: "J", label: "Back 5 seconds", group: "Playback" },
  { id: "fwd5", spec: "l", keys: "L", label: "Forward 5 seconds", group: "Playback" },
  { id: "back5s", spec: "Shift+ArrowLeft", keys: "Shift+←", label: "Back 5 seconds", group: "Playback" },
  { id: "fwd5s", spec: "Shift+ArrowRight", keys: "Shift+→", label: "Forward 5 seconds", group: "Playback" },
  { id: "start", spec: "Home", keys: "Home", label: "Go to the start", group: "Playback" },
  { id: "end", spec: "End", keys: "End", label: "Go to the end", group: "Playback" },
  { id: "mute", spec: "m", keys: "M", label: "Mute the player", group: "Playback" },
  { id: "focus", spec: "f", keys: "F", label: "Full screen: just the video (Esc leaves)", group: "Playback" },

  { id: "prev", spec: "ArrowLeft", keys: "←", label: "Previous shot", group: "Shots" },
  { id: "next", spec: "ArrowRight", keys: "→", label: "Next shot", group: "Shots" },
  { id: "prev_flag", spec: ",", keys: ",", label: "Previous shot that needs attention", group: "Shots" },
  { id: "next_flag", spec: ".", keys: ".", label: "Next shot that needs attention", group: "Shots" },
  { id: "undo_shot", spec: "Mod+Shift+u", keys: "Ctrl+Shift+U", label: "Undo the last change to a shot (approve, keyframe, end frame, motion, lock)", group: "Shots" },
  { id: "redo_shot", spec: "Mod+Shift+y", keys: "Ctrl+Shift+Y", label: "Redo it", group: "Shots" },
  { id: "approve", spec: "a", keys: "A", label: "Approve this shot's new keyframe or take", group: "Shots" },
  { id: "frames", spec: "e", keys: "E", label: "Open this shot's Compose tab (start and end, references, motion)", group: "Shots" },
  { id: "rerender", spec: "r", keys: "R", label: "Re-render this shot (shows the price first)", group: "Shots" },

  { id: "layers", spec: "y", keys: "Y", label: "Open or close the Layers panel", group: "Panels" },
  { id: "add_text", spec: "t", keys: "T", label: "Add a text layer at the playhead", group: "Panels" },
  { id: "hide_layer", spec: "h", keys: "H", label: "Hide or show the selected layer", group: "Panels" },
  { id: "command", spec: "Mod+k", keys: "Ctrl+K", label: "Director Command", group: "Panels", typingOk: true },
  { id: "inspector", spec: "Mod+i", keys: "Ctrl+I", label: "Show or hide the inspector", group: "Panels", menu: true },
  { id: "timeline", spec: "Mod+j", keys: "Ctrl+J", label: "Show or hide the timeline", group: "Panels" },
  { id: "timeline_compact", spec: "Mod+Shift+j", keys: "Ctrl+Shift+J", label: "Compact or full-height timeline", group: "Panels" },
  { id: "palette", spec: "Mod+Shift+p", keys: "Ctrl+Shift+P", label: "Command palette: find any action or shot", group: "Panels" },
  { id: "keys", spec: "?", keys: "?", label: "This list (also Ctrl+/)", group: "Panels" },
  { id: "undo", spec: "Mod+z", keys: "Ctrl+Z", label: "Undo the last change to the layers (while the Layers panel is open)", group: "Panels" },
  { id: "redo", spec: "Mod+Shift+z", keys: "Ctrl+Shift+Z", label: "Redo it", group: "Panels" },
  { id: "redo_y", spec: "Mod+y", keys: "Ctrl+Y", label: "Redo it (same as Ctrl+Shift+Z)", group: "Panels" },

  { id: "shot_sound", spec: "Shift+m", keys: "Shift+M", label: "Turn this shot's own sound on or off", group: "Sound" },

  { id: "docs", spec: "F1", keys: "F1", label: "Documentation", group: "Project", menu: true },
  { id: "new", spec: "Mod+n", keys: "Ctrl+N", label: "New music video", group: "Project", menu: true },
  { id: "open", spec: "Mod+o", keys: "Ctrl+O", label: "Open project", group: "Project", menu: true },
  { id: "save", spec: "Mod+s", keys: "Ctrl+S", label: "Save", group: "Project", menu: true },
  { id: "save_as", spec: "Mod+Shift+s", keys: "Ctrl+Shift+S", label: "Save as", group: "Project", menu: true },
  { id: "export", spec: "Mod+e", keys: "Ctrl+E", label: "Export", group: "Project", menu: true },
  { id: "mode_simple", spec: "Mod+1", keys: "Ctrl+1", label: "Simple mode", group: "Project", menu: true },
  { id: "mode_director", spec: "Mod+2", keys: "Ctrl+2", label: "Director Mode", group: "Project", menu: true },
  { id: "settings", spec: "Mod+,", keys: "Ctrl+,", label: "Settings", group: "Project", menu: true },
];

export const GROUPS: ShortcutGroup[] = ["Playback", "Shots", "Panels", "Sound", "Project"];

/** True while the person is typing or choosing in a control, so plain keys must be left to it. */
export function isTyping(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  if (el.isContentEditable) return true;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/** Like isTyping for a key press: a slider (the scrub bar, the volume) keeps focus after you drag it, and the keys it uses itself (arrows, Home, End, Page Up/Down) stay its own, but Space, J, K and the rest still play and pause. */
export function isTypingKey(e: { target: EventTarget | null; key: string }): boolean {
  const el = e.target as HTMLInputElement | null;
  if (!isTyping(el)) return false;
  if (el?.tagName === "INPUT" && el.type === "range") return /^(Arrow|Home$|End$|Page)/.test(e.key);
  return true;
}

type Parsed = { mod: boolean; shift: boolean; key: string };
function parse(spec: string): Parsed {
  const parts = spec.split("+");
  const key = parts[parts.length - 1];
  const mods = parts.slice(0, -1);
  return { mod: mods.includes("Mod"), shift: mods.includes("Shift"), key };
}

/** Does this key press match the spec? A plain key never matches while Ctrl, Cmd or Alt is held (Ctrl+R is not "re-render"). */
export function matches(e: Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">, spec: string): boolean {
  const p = parse(spec);
  if (e.altKey) return false;
  const mod = e.ctrlKey || e.metaKey;
  if (p.mod !== mod) return false;
  const named = p.key.length > 1 && p.key !== "?";
  const pressed = p.key === "Space" ? e.code === "Space" : named ? e.key === p.key : e.key.toLowerCase() === p.key.toLowerCase();
  if (!pressed) return false;
  // Shift is part of the character for "?" and capital letters; it only has to agree where the spec asks for it.
  if (p.shift) return e.shiftKey;
  if (p.key.length === 1 && p.key !== "?") return !e.shiftKey;   // "m" is mute, "Shift+M" is not
  if (named) return !e.shiftKey || p.key.startsWith("F");
  return true;
}

/** The shortcut a key press means in the Studio's own handler (menu items are handled by the desktop menu). */
export function find(e: Parameters<typeof matches>[0], opts: { typing?: boolean } = {}): Shortcut | null {
  const slash = (e.ctrlKey || e.metaKey) && e.key === "/";
  if (slash) return SHORTCUTS.find((s) => s.id === "keys") ?? null;
  const plainOnly = opts.typing;
  for (const s of SHORTCUTS) {
    if (s.menu) continue;
    if (plainOnly && !s.typingOk) continue;          // typing: only Ctrl+K still works; the rest is left to the box
    if (matches(e, s.spec)) return s;
  }
  return null;
}
