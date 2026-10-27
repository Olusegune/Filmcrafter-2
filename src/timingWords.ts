/** The strip's scale: seconds from the earliest voice (a J cut starts before the picture) to the latest end (a voice that runs on), so every shot's strip uses the same ruler. */
export type Scale = { from: number; to: number };

export const scaleOf = (rows: { lead: number; seconds: number; tail: number; end: number }[]): Scale => {
  const from = -Math.max(0, ...rows.map((r) => r.lead));
  const to = Math.max(1, ...rows.map((r) => Math.max(r.seconds + r.tail, r.end)));
  return { from, to };
};

/** Where a span sits on the strip, in percent, never off either edge and never so thin it cannot be seen. */
export const barStyle = (s: Scale, start: number, seconds: number): { left: string; width: string } => {
  const span = Math.max(0.001, s.to - s.from);
  const left = Math.min(100, Math.max(0, ((start - s.from) / span) * 100));
  const width = Math.min(100 - left, Math.max(0.8, (seconds / span) * 100));
  return { left: `${left.toFixed(2)}%`, width: `${width.toFixed(2)}%` };
};
