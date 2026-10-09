import * as I from "./icons";

/** More pictures for cards that were only words: a direction, a look, a style. Same 1.75 px stroke as the rest (icons.tsx). */
type P = { size?: number };
const S = ({ size = 20, children }: P & { children: React.ReactNode }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);
export const Mic = (p: P) => <S {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" /></S>;
export const Moon = (p: P) => <S {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></S>;
export const Sun = (p: P) => <S {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" /></S>;
export const Globe = (p: P) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></S>;
export const Road = (p: P) => <S {...p}><path d="M8 3 4 21M16 3l4 18M12 4v3M12 10.5v3M12 17v3" /></S>;
export const Sword = (p: P) => <S {...p}><path d="M14.5 4.5 20 4l-.5 5.5L10 19l-5-5ZM5 14l-2 5 5-2M12 12l-4 4" /></S>;
export const Scissors = (p: P) => <S {...p}><circle cx="6" cy="6.5" r="2.5" /><circle cx="6" cy="17.5" r="2.5" /><path d="M8 8l12 9M8 16 20 7" /></S>;
export const Heart = (p: P) => <S {...p}><path d="M12 20s-8-4.6-8-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 8 2.8C20 15.4 12 20 12 20Z" /></S>;
export const Star = (p: P) => <S {...p}><path d="m12 3 2.7 5.6 6.1.8-4.4 4.3 1 6.1L12 17l-5.4 2.8 1-6.1L3.2 9.4l6.1-.8Z" /></S>;
export const Brush = (p: P) => <S {...p}><path d="M18.5 3.5a2.1 2.1 0 0 1 3 3L12 16l-3-3ZM9 13c-3 0-5 1.8-5 4.5C4 19 3 20 2 20.5c2.5.8 7 .8 8.5-2 .8-1.5.3-3.5-1.5-5.5Z" /></S>;
export const Flame = (p: P) => <S {...p}><path d="M12 3c1 4 5 5.5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 .3 1.2 1 2 2 2-.5-3 0-6 1-8Z" /></S>;
export const Leaf = (p: P) => <S {...p}><path d="M5 19C5 10 10 5 20 4c0 10-5 15-14 15ZM5 19l8-8" /></S>;
export const Skyline = (p: P) => <S {...p}><path d="M3 21h18M5 21V10h4v11M9 21V5h5v16M14 21v-8h5v8M11 8h1M11 12h1M7 14h0M16.5 16h0" /></S>;
export const Cutout = (p: P) => <S {...p}><path d="M4 5h9l3 3v4h4v7H8v-4H4Z" /><path d="M8 15V9h5" /></S>;

type Icon = (p: P) => React.ReactElement;

/** Which picture suits a direction, from its name, origin, summary and mood. First match wins; the globe when nothing says more. */
const RULES: [RegExp, Icon][] = [
  [/stop.?motion|claymation|clay|felt|puppet|handmade|craft|diorama|brick/i, Scissors],
  [/cut.?out|paper|collage|2\.?5d/i, Cutout],
  [/road|highway|motel|americana|diner|desert/i, Road],
  [/one.?take|concert|stage|live|performance|mic\b|karaoke|studio session/i, Mic],
  [/martial|wuxia|sword|samurai|kung|chambara/i, Sword],
  [/nights?\b|neon|noir|club|after dark|moonlit|midnight/i, Moon],
  [/new wave|nouvelle|silent|cinema|classic|hollywood|1[89]\d0s|noir film/i, I.Film],
  [/love|romance|romantic|tender|wedding|intimate/i, Heart],
  [/dance|afrobeats?|carnival|bollywood|dancehall|amapiano|choreo|samba|salsa|hip.?hop/i, I.Dance],
  [/skyline|rooftop|urban|street|city/i, Skyline],
  [/paint|watercolou?r|impression|ink\b|oil\b|illustrat|abstract|sketch|mural/i, Brush],
  [/forest|mountain|ocean|sea\b|village|rural|landscape|savannah|pastoral|nature|garden/i, Leaf],
  [/futur|sci.?fi|cyber|space|robot|android|retro.?future/i, I.Rocket],
  [/fashion|couture|runway|glam|editorial|catwalk/i, I.Shirt],
  [/punk|rock|metal|rage|fire|riot|grunge/i, Flame],
  [/sun\b|golden|summer|tropical|festival|beach|warm/i, Sun],
  [/dream|surreal|fantasy|magic|myth|fairy|folklore/i, I.Sparkle],
  [/documentary|verit|handheld|raw|candid/i, I.Camera],
];

export function directionGlyph(...text: (string | undefined | null)[]): Icon {
  const t = text.filter(Boolean).join(" · ");
  return RULES.find(([rx]) => rx.test(t))?.[1] ?? Globe;
}

/** The look styles (3D, 2D, stop motion…): a picture for each family. */
const LOOKS: [RegExp, Icon][] = [
  [/photoreal|live-action/i, I.Camera],
  [/3d|cgi|low-poly/i, I.Cube],
  [/stop-motion|clay|puppet|brick|diorama|paper-stop/i, Scissors],
  [/anime|manga/i, Star],
  [/cutout|2-5d|motion-comic|silhouette/i, Cutout],
  [/paint|sand|glass|watercolour|rotoscope/i, Brush],
  [/2d|cel|cartoon|rubber|western|digital|limited|whiteboard|pixel|graphics/i, I.Wand],
  [/afro|mixed/i, I.Sparkle],
];

export function lookGlyph(id: string, name?: string): Icon {
  const t = `${id} ${name ?? ""}`;
  return LOOKS.find(([rx]) => rx.test(t))?.[1] ?? I.Film;
}

/** A small square badge holding the picture, for the head of a card. */
export function Badge({ icon: Ic, size = 18 }: { icon: Icon; size?: number }) {
  return <span className="glyph-badge" aria-hidden="true"><Ic size={size} /></span>;
}
