// Geometric, 1.75px stroke, rounded ends (PRD §46). Monochrome; color comes from context.
type P = { size?: number };
const S = ({ size = 20, children }: P & { children: React.ReactNode }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);

/** FilmCrafter mark: two waveform strokes inside an open frame (PRD §47). */
export const Mark = ({ size = 22 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M8 3H4.5A1.5 1.5 0 0 0 3 4.5v15A1.5 1.5 0 0 0 4.5 21H8M16 3h3.5A1.5 1.5 0 0 1 21 4.5v15a1.5 1.5 0 0 1-1.5 1.5H16"
          stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" />
    <path d="M10 8v8M14 5.5v13" stroke="#E8B45C" strokeWidth={2.2} strokeLinecap="round" />
  </svg>
);
export const Home = (p: P) => <S {...p}><path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" /></S>;
export const Folder = (p: P) => <S {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></S>;
export const Assets = (p: P) => <S {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></S>;
export const Studio = (p: P) => <S {...p}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M3 20h18M8 20v-4M16 20v-4" /></S>;
export const Review = (p: P) => <S {...p}><path d="M4 12.5 9 17.5 20 6.5" /></S>;
export const Export = (p: P) => <S {...p}><path d="M12 15V3M7 8l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></S>;
export const Gear = (p: P) => <S {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 1.2 14H1a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 7a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 2.6V2.5a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.6 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></S>;
export const Note = (p: P) => <S {...p}><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></S>;
export const Play = (p: P) => <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.8l-12-7.5A1 1 0 0 0 7 4.5Z" /></svg>;
export const Pause = (p: P) => <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></svg>;
export const SkipBack = (p: P) => <S {...p}><path d="M19 20 9 12l10-8zM5 19V5" /></S>;
export const SkipFwd = (p: P) => <S {...p}><path d="m5 4 10 8-10 8zM19 5v14" /></S>;
export const Panel = (p: P) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></S>;
export const PanelBottom = (p: P) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 15h18" /></S>;
export const Close = (p: P) => <S {...p}><path d="M6 6l12 12M18 6 6 18" /></S>;
export const Check = (p: P) => <S {...p}><path d="M5 12.5 10 17.5 19 7" /></S>;
export const Circle = (p: P) => <S {...p}><circle cx="12" cy="12" r="7" strokeDasharray="3 3" /></S>;
export const Alert = (p: P) => <S {...p}><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></S>;
export const Lock = (p: P) => <S {...p}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></S>;
export const Script = (p: P) => <S {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></S>;
export const Volume = (p: P) => <S {...p}><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /></S>;
export const Mute = (p: P) => <S {...p}><path d="M4 9v6h4l5 4V5L8 9z" /><path d="m17 9 5 6M22 9l-5 6" /></S>;
export const ArrowRight = (p: P) => <S {...p}><path d="M5 12h14M13 6l6 6-6 6" /></S>;
export const ArrowLeft = (p: P) => <S {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></S>;
export const Upload = (p: P) => <S {...p}><path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></S>;
export const Doc = (p: P) => <S {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></S>;
export const Search = (p: P) => <S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></S>;
export const Wave = (p: P) => <S {...p}><path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0" /></S>;
export const Wand = (p: P) => <S {...p}><path d="m4 20 11-11M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM19 11l.6 1.4L21 13l-1.4.6L19 15l-.6-1.4L17 13l1.4-.6z" /></S>;
export const User = (p: P) => <S {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></S>;
export const Cube = (p: P) => <S {...p}><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" /></S>;
export const Mountain = (p: P) => <S {...p}><path d="m3 20 6-10 4 6 2-3 6 7z" /></S>;
export const Shirt = (p: P) => <S {...p}><path d="m8 3-5 3 2 5 3-1v11h8V10l3 1 2-5-5-3a4 4 0 0 1-8 0z" /></S>;
export const Dance = (p: P) => <S {...p}><circle cx="14" cy="4.5" r="1.8" /><path d="m7 21 4-6 3 2 1 4M11 15l1-5-4-1-3 3M12 10l4 2 4-3" /></S>;
export const Trash = (p: P) => <S {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></S>;
export const Film = (p: P) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4" /></S>;

// ---- camera, light and panel icons (the sidebar) ----
export const Camera = (p: P) => <S {...p}><path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" /><circle cx="12" cy="13" r="3.5" /></S>;
export const Lens = (p: P) => <S {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="M12 3v5.5M20.3 8.5l-5.1 3M18.6 18l-4.5-3.2M5.4 18l4.5-3.2M3.7 8.5l5.1 3" /></S>;
export const Light = (p: P) => <S {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6" /></S>;
export const Focus = (p: P) => <S {...p}><circle cx="12" cy="12" r="3" /><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /></S>;
export const Move = (p: P) => <S {...p}><path d="M4 12h16M8 8l-4 4 4 4M16 8l4 4-4 4" /></S>;
export const Angle = (p: P) => <S {...p}><path d="M4 20h16M4 20 17 6" /><path d="M10 20a6 6 0 0 0-1.8-4.3" /></S>;
export const FrameSize = (p: P) => <S {...p}><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" /><rect x="9" y="9" width="6" height="6" rx="1" /></S>;
export const Bolt = (p: P) => <S {...p}><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></S>;
export const ImageIcon = (p: P) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m4 18 5-5 4 4 3-3 4 4" /></S>;
export const Clapper = (p: P) => <S {...p}><rect x="3" y="6" width="13" height="12" rx="2.2" /><path d="m16 10.4 5-3v9.2l-5-3z" /></S>;
export const Layers = (p: P) => <S {...p}><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5M3 17.5 12 22l9-4.5" /></S>;
export const Mask = (p: P) => <S {...p}><path d="M4 5c3 1.5 13 1.5 16 0v6c0 5-3.6 9-8 9s-8-4-8-9z" /><path d="M8.5 10.5H10M14 10.5h1.5M9 15c1.8 1.4 4.2 1.4 6 0" /></S>;
export const Link = (p: P) => <S {...p}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></S>;
export const Sparkle = (p: P) => <S {...p}><path d="M11 3l1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8zM19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z" /></S>;
export const Coin = (p: P) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M14.5 9.2c-.5-.9-1.5-1.4-2.6-1.4-1.5 0-2.6.8-2.6 2 0 3 5.4 1.4 5.4 4.2 0 1.2-1.1 2-2.7 2-1.2 0-2.3-.5-2.8-1.5M12 6.5v1.3M12 16.2v1.3" /></S>;
export const Sliders = (p: P) => <S {...p}><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></S>;
export const Chevron = (p: P) => <S {...p}><path d="m6 9 6 6 6-6" /></S>;
export const Info = (p: P) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></S>;
export const Rocket = (p: P) => <S {...p}><path d="M5 19c0-3 1.5-4.5 3-5l-1-3c-1 .3-2 1-3 2.5L2 14c1-4 4-6 7-6 3-4.5 8-6 12-5-1 4-1.5 9-6 12 0 3-2 6-6 7l.5-2.5c1.5-1 2.5-2 2.5-3z" /></S>;
export const Eye = (p: P) => <S {...p}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" /></S>;
export const Refresh = (p: P) => <S {...p}><path d="M20 11a8 8 0 0 0-14.6-3.5M4 4v4h4M4 13a8 8 0 0 0 14.6 3.5M20 20v-4h-4" /></S>;
export const Mic = (p: P) => <S {...p}><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></S>;
