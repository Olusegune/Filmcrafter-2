/** Which shot to render first, before the rest: the one that shows the most of what can go wrong (a mouth to sync, a body to dance, a feeling to read). One cheap render of it tells you whether the project's settings work before you pay for the other shots. */
export type TestCandidate = { id: string; start: number; end: number; framing?: string; performers?: string[]; emotion?: string; text?: string };
export type Lyric = { start?: number | null; end?: number | null };

const CLOSE = /medium|close|\bcu\b|\bmcu\b|\bms\b|waist|chest|portrait/i;
const WIDE = /wide|establishing|aerial|insert|detail|silhouette|from behind|\bels?\b|\bws\b/i;
const DANCE = /\b(danc\w*|choreograph\w*|groov\w*|sway\w*|twirl\w*|shimmy\w*|strut\w*|footwork|routine)\b/i;

export function pickTestShot(shots: TestCandidate[], keyframes: Record<string, string>, rendered: Set<string>, lyrics: Lyric[]): { id: string; why: string[] } | null {
  let best: { id: string; score: number; why: string[] } | null = null;
  for (const s of shots) {
    if (!keyframes[s.id] || rendered.has(s.id) || !(s.end > s.start)) continue;     // a test needs an approved keyframe and no take yet
    const why: string[] = [];
    let score = 0;
    const heard = lyrics.reduce((a, l) => (l.start == null ? a : a + Math.max(0, Math.min(l.end ?? l.start, s.end) - Math.max(l.start, s.start))), 0);
    const who = (s.performers ?? []).length > 0;
    const framing = s.framing ?? "";
    if (who && heard >= 1) { score += 4; why.push("a mouth to sync to the song"); }
    if (who && CLOSE.test(framing) && !WIDE.test(framing)) { score += 2; why.push("a face close enough to judge"); }
    if (who && DANCE.test(s.text ?? "")) { score += 2; why.push("a dance move"); }
    if (who && s.emotion) { score += 1; why.push(`the feeling “${s.emotion}”`); }
    if (who) score += 1;
    if (s.end - s.start >= 2 && s.end - s.start <= 6) score += 1;                 // long enough to read, short enough to be cheap
    if (!best || score > best.score) best = { id: s.id, score, why };
  }
  return best && best.score > 0 ? { id: best.id, why: best.why } : null;
}
