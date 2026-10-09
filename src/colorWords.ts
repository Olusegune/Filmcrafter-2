/** Colour names as colour: a palette written in words ("dusty orange", "neon pink", "ink black") drawn as swatches, so a direction can be seen at a glance instead of read.
 *  A word the app does not know still gets a calm, steady colour (the same word always gives the same one), never a gap. Pure. */

const WORDS: Record<string, string> = {
  black: "#16181c", ink: "#13151b", obsidian: "#0f1115", charcoal: "#2f343b", white: "#f1efe9", pearl: "#ece8e1", ivory: "#f3eedd", silk: "#f4f1ea", feather: "#f1efe9", whitewash: "#f0eee8",
  grey: "#8a8f98", gray: "#8a8f98", silver: "#c0c4cc", chrome: "#b9c2cc", stone: "#9a9488", concrete: "#9b9fa4", slate: "#5b6b82",
  red: "#d6373b", crimson: "#b81c3a", vermilion: "#e34234", scarlet: "#d62a2f", blood: "#8a0f1c", wine: "#6e1f35", brick: "#a8453a", terracotta: "#c8603f", coral: "#f26b5b", rust: "#a8502c",
  orange: "#e8872c", amber: "#f2a900", gold: "#d9a520", yellow: "#f0cf3c", marigold: "#f5a623", ochre: "#c58a2b", sunset: "#f0703a", tungsten: "#f2a64a", lamp: "#f4b860",
  sand: "#d8c08f", cream: "#f3e9cf", beige: "#d9c8a7", tan: "#c9a77a", brown: "#7a5236", kraft: "#b88a5a", timberland: "#b88a4a", felt: "#c9b8d0", paper: "#e6d8b8",
  pink: "#ee7ab0", magenta: "#d63aa6", fuchsia: "#e0309a",
  violet: "#7a4bd1", purple: "#7a3fb0", indigo: "#3f3fa6", lavender: "#b4a0e0", plum: "#6a2f6a",
  blue: "#2f6fdb", cobalt: "#1f4fc2", denim: "#4a6fa5", navy: "#1b2a5c", sky: "#7cc0ee", ocean: "#1d5f8f",
  turquoise: "#2cc0b5", teal: "#1e8f8f", cyan: "#27c2de", lagoon: "#2fb7c4", jade: "#2fa57a", emerald: "#1f9d63", green: "#3fa34d", olive: "#7a8a3a", meadow: "#7fbf5a", moss: "#5a7a3a",
  roof: "#b04a3a", sneakers: "#f1efe9", night: "#1c1a3a", neon: "#ff3fd0",
};
// whole phrases that name no single colour: drawn as the colours they describe
const PHRASES: Record<string, string[]> = {
  "black and white": ["#14161a", "#f1efe9"], "primary accents": ["#d6373b", "#f0cf3c", "#2f6fdb"], "primary colours": ["#d6373b", "#f0cf3c", "#2f6fdb"],
  "wax-print colour": ["#e8872c", "#2f6fdb", "#d6373b", "#f0cf3c"], "papel-picado colours": ["#ee7ab0", "#2cc0b5", "#f0cf3c", "#7a4bd1"],
  "vivid accent colours": ["#ff3fd0", "#27c2de", "#f0cf3c"], "one bold colour": ["#e8523a"],
};

type Hsl = [number, number, number];
const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));

function toHsl(hex: string): Hsl {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  if (!d) return [0, 0, l * 100];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [(h * 60 + 360) % 360, s * 100, l * 100];
}
const css = ([h, s, l]: Hsl) => `hsl(${Math.round(h)}, ${Math.round(clamp(s))}%, ${Math.round(clamp(l, 4, 96))}%)`;

// what a describing word does to a colour: [saturation x, lightness +/x]
const MODS: Record<string, (c: Hsl) => Hsl> = {
  dusty: ([h, s, l]) => [h, s * 0.55, l + 4], faded: ([h, s, l]) => [h, s * 0.5, l + 8], muted: ([h, s, l]) => [h, s * 0.5, l], washed: ([h, s, l]) => [h, s * 0.5, l + 12],
  deep: ([h, s, l]) => [h, s, l * 0.62], dark: ([h, s, l]) => [h, s, l * 0.55], rich: ([h, s, l]) => [h, s * 1.1, l * 0.8],
  light: ([h, s, l]) => [h, s, l + 18], pale: ([h, s, l]) => [h, s * 0.6, l + 24], pastel: ([h, s, l]) => [h, s * 0.6, l + 26],
  neon: ([h]) => [h, 100, 58], electric: ([h]) => [h, 95, 56], hot: ([h, , l]) => [h, 90, clamp(l, 50, 62)], vivid: ([h, s, l]) => [h, clamp(s * 1.2), l], bright: ([h, s, l]) => [h, s, l + 8],
  warm: ([h, s, l]) => [h < 60 || h > 300 ? h : h - 12, s, l], cool: ([h, s, l]) => [h > 150 && h < 260 ? h : h + 12, s, l],
};

function hashHue(text: string): number { let n = 7; for (const c of text) n = (n * 31 + c.charCodeAt(0)) % 360; return n; }

/** The flat colour or colours a name stands for (more than one for a phrase such as "black and white"). Always at least one. */
export function colours(name: string): string[] {
  const t = String(name ?? "").toLowerCase().replace(/[^a-z\- ]+/g, " ").replace(/\s+/g, " ").trim();
  if (PHRASES[t]) return PHRASES[t];
  const words = t.split(/[ -]+/).filter(Boolean);
  const idx = words.map((w) => w in WORDS).lastIndexOf(true);
  if (idx < 0) return [css([hashHue(t || "?"), 28, 46])];                              // an unknown word: a calm colour of its own
  let c = toHsl(WORDS[words[idx]]);
  for (const w of [...words.slice(0, idx), ...words.slice(idx + 1)]) if (MODS[w]) c = MODS[w](c);
  return [css(c)];
}

/** A CSS background for one named colour: a flat colour, or a split for a phrase that names several. */
export function swatch(name: string): string {
  const c = colours(name);
  if (c.length === 1) return c[0];
  const step = 100 / c.length;
  return `linear-gradient(135deg, ${c.map((x, i) => `${x} ${Math.round(i * step)}% ${Math.round((i + 1) * step)}%`).join(", ")})`;
}

/** A band of crisp colour blocks, one per colour in the palette (up to `max` blocks). */
export function paletteBand(names: string[], max = 5): string {
  const list = names.flatMap(colours).slice(0, max);
  if (!list.length) return "linear-gradient(135deg, #20262f, #171b22)";
  if (list.length === 1) return list[0];
  const step = 100 / list.length;
  return `linear-gradient(90deg, ${list.map((c, i) => `${c} ${Math.round(i * step)}% ${Math.round((i + 1) * step)}%`).join(", ")})`;
}
