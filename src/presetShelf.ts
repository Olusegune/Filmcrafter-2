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

/** The frame shape a preset asks for, if it asks for one (a vertical series is 9:16). */
export const presetAspect = (p: HomePreset): string | null => (typeof p.settings.aspect === "string" ? p.settings.aspect : null);

/** What a project card says about the film, for a person: "Story locked · 9:16 · Yesterday". Leaves out what is not known. */
export function cardMeta(state: string, aspect: string | null | undefined, when: string): string {
  return [state, aspect || "", when].filter(Boolean).join(" · ");
}

/** How many recent films to show before "Show all": enough to fill a screen, few enough that a long list stays quick. */
export const RECENT_SHOWN = 8;
