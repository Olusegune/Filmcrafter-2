/** The presets the Home screen shows, read straight from the engine's own list (the same file the Presets sheet uses), so there is one set of definitions and the two can never disagree. Pure, so it can be tested. */
import registry from "../analysis/filmcrafter_engine/presets_builtin.json";

export type HomePreset = {
  id: string; type: string; group: string; name: string; description: string; use?: string; thumbnail: string | null;
  includes: string[]; settings: Record<string, unknown>; series?: string | null;
};

export const ALL: HomePreset[] = (registry as unknown as { presets: HomePreset[] }).presets;
export const byId = (id: string): HomePreset | undefined => ALL.find((p) => p.id === id);

/** The presets shown first on Home: a spread of what people make (a series, an animation, a look, a history film, a documentary, a short). */
export const FEATURED_IDS = ["vertical_micro_drama", "animated_short", "storybook_2_5d_style", "historical_explainer", "documentary", "youtube_shorts"];
export const featured = (): HomePreset[] => FEATURED_IDS.map(byId).filter((p): p is HomePreset => !!p);

export const TYPE_LABEL: Record<string, string> = { production: "Format", visual: "Look", performance: "Acting", editing: "Editing", color: "Colour", delivery: "Delivery" };
export const TYPES = ["production", "visual", "performance", "editing", "color", "delivery"];

/** What a preset brings along: the presets it stacks, by name. */
export const stackedNames = (p: HomePreset): string[] => p.includes.map((id) => byId(id)?.name).filter((n): n is string => !!n);

/** The presets that match a search and a type ("all" for every type); the search looks at the name, the description and the use. */
export function find(list: HomePreset[], query: string, type: string): HomePreset[] {
  const q = query.trim().toLowerCase();
  return list.filter((p) => (type === "all" || p.type === type) && (!q || `${p.name} ${p.description} ${p.use ?? ""}`.toLowerCase().includes(q)));
}

/** The layer presets that can be added to a production preset when a film is set up, by what each changes (the later one wins over the earlier). */
export const SETUP_LAYERS: { key: "visual" | "acting" | "editing" | "color"; label: string; type: string }[] = [
  { key: "visual", label: "Visual style", type: "visual" }, { key: "acting", label: "Acting", type: "performance" },
  { key: "editing", label: "Editing", type: "editing" }, { key: "color", label: "Colour", type: "color" }];
export const layerChoices = (type: string): HomePreset[] => ALL.filter((p) => p.type === type);

/** Lengths offered when a film is set up (seconds), with the preset's own length first in the list when it is not one of them. */
export const LENGTHS = [30, 60, 90, 120, 180, 300, 600];
export const lengthOptions = (hint: number | null): number[] => (hint && !LENGTHS.includes(hint) ? [...LENGTHS, hint].sort((a, b) => a - b) : LENGTHS);
export const lengthWords = (s: number): string => (s < 120 ? `${s} seconds` : `${Math.round((s / 60) * 10) / 10} minutes`);
export const presetLength = (p: HomePreset): number | null => (typeof p.settings.duration_hint_s === "number" ? p.settings.duration_hint_s : null);

/** The stack to remember for a film set up from a preset: the preset first, then each chosen layer preset (a later one wins). Choosing nothing for a layer leaves it to the preset. */
export const setupStack = (p: HomePreset, chosen: Partial<Record<"visual" | "acting" | "editing" | "color", string>>): string[] =>
  [p.id, ...SETUP_LAYERS.map((l) => chosen[l.key]).filter((id): id is string => !!id && !!byId(id))];

/** The frame shape a preset asks for, if it asks for one (a vertical series is 9:16). */
export const presetAspect = (p: HomePreset): string | null => (typeof p.settings.aspect === "string" ? p.settings.aspect : null);

/** What a project card says about the film, for a person: "Story locked · 9:16 · Yesterday". Leaves out what is not known. */
export function cardMeta(state: string, aspect: string | null | undefined, when: string): string {
  return [state, aspect || "", when].filter(Boolean).join(" · ");
}

/** How many recent films to show before "Show all": enough to fill a screen, few enough that a long list stays quick. */
export const RECENT_SHOWN = 8;
