/** The words the Action scene screen uses. Pure, so they can be tested. */
export const ACTION_LABEL: Record<string, string> = { fight: "Fist fight", armed: "Armed duel", chase: "Foot chase", vehicle: "Vehicle chase", sport: "Sports moment" };
export const actionWords = (type: string) => ACTION_LABEL[type] ?? type;

const BEAT: Record<string, string> = { establish: "The place", action: "Action", reaction: "Reaction", insert: "Cut to a detail", aftermath: "How it ends" };
export const beatLabel = (kind: string) => BEAT[kind] ?? kind;

/** Who has the upper hand in a beat, in words. */
export const momentumWords = (m: "A" | "B" | "even", a?: string, b?: string): string =>
  m === "A" ? `${a ?? "First side"} has the upper hand` : m === "B" ? `${b ?? "Other side"} has the upper hand` : "Evenly matched";
