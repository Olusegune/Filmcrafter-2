import type { MaterialItem } from "./api";

/** The section a plan item is shown under, in the order a person thinks about them. */
export const SECTIONS: { id: string; title: string; types: MaterialItem["type"][]; hint: string }[] = [
  { id: "board", title: "Storyboard panels", types: ["storyboard"], hint: "Each panel becomes the chosen storyboard picture for its shot, and can guide the framing of that shot's hero picture." },
  { id: "assets", title: "Pictures of people, places and props", types: ["asset"], hint: "Added to the cast, place or prop they belong to, as references the pictures are made from." },
  { id: "list", title: "Shot list", types: ["shotrow", "newshot"], hint: "Fills in the shots' framing, movement, length, dialogue and notes. What you wrote yourself is never replaced unless you tick it." },
  { id: "notes", title: "Notes", types: ["note"], hint: "Kept with the film. A style, world or rules note can also be added to the Bible." },
  { id: "other", title: "Needs your answer", types: ["unsorted", "skip"], hint: "FilmCrafter could not tell what these are, or cannot use them." },
];

export const KIND_LABEL: Record<string, string> = { storyboard: "A storyboard panel", character: "A character", environment: "A place", prop: "A prop", skip: "Leave it out" };

export const typeWords = (it: MaterialItem): string => {
  if (it.type === "storyboard") return it.shot ? `Panel for ${it.shot_label ?? it.shot}${it.how ? `, matched by ${it.how}` : ""}` : "Which shot is this panel for?";
  if (it.type === "asset") return `${it.create ? "New " : ""}${it.kind === "environment" ? "place" : it.kind}: ${it.entry_name || it.name || "?"}${it.media_kind && it.media_kind !== "reference" ? ` · ${it.media_kind} view` : ""}`;
  if (it.type === "shotrow") return `Update shot ${it.title}`;
  if (it.type === "newshot") return it.title;
  if (it.type === "note") return it.target && it.target !== "keep" ? `Add to the Bible's ${it.target}` : "Keep as a note";
  return it.title;
};

export const canTick = (it: MaterialItem) => !it.blocked && it.type !== "unsorted" && it.type !== "skip";

export const summaryWords = (c: Record<string, number>): string => {
  const parts: string[] = [];
  const n = (k: string, one: string, many: string) => { if (c[k]) parts.push(`${c[k]} ${c[k] === 1 ? one : many}`); };
  n("storyboard", "storyboard panel", "storyboard panels");
  n("asset", "picture for the cast, places and props", "pictures for the cast, places and props");
  n("shotrow", "shot updated from the list", "shots updated from the list");
  n("newshot", "new shot", "new shots");
  n("note", "note", "notes");
  return parts.join(", ");
};
