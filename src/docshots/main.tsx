/**
 * The screenshot harness: renders one real screen of the app with made-up data, so the guide's pictures (docs/img) can be regenerated and so a layout can be looked at without the desktop shell.
 *
 *   npm run dev                                  (the preview on http://localhost:1420)
 *   node scripts/docshots-edge.mjs               (every scene)   or   node scripts/docshots-edge.mjs review kt   (just those)
 *   http://localhost:1420/docshots.html?scene=review   (look at one in a browser)
 *
 * Nothing here ships in the app: only index.html is built. The pictures are placeholders made by make_samples.py; the direction and look texts are the app's own.
 * A scene can be told what to do once it is up: &click=<button text> presses a button, &drag=x0,y0,x1,y1 drags a box on the Fix a hand picture (fractions of the picture).
 */
import { createRoot } from "react-dom/client";
import { mockIPC, mockWindows } from "@tauri-apps/api/mocks";
import type { ReactNode } from "react";
import { RenderQueueSheet } from "../RenderQueue";
import { ReviewSheet } from "../Review";
import { KeyframeTools } from "../KeyframeTools";
import { HandFix } from "../HandFix";
import { RoutingSheet } from "../Routing";
import { SelectReview } from "../SelectReview";
import { DirectionLibrarySheet } from "../DirectionLibrary";
import { CreativeDirections } from "../Directions";
import { LookPicker } from "../Looks";
import { LightingSheet } from "../Lighting";
import { CleanupSheet } from "../Cleanup";
import { ModelChoice } from "../ModelChoice";
import { ComposeTab } from "../Compose";
import { TakeCompare } from "../Compare";
import { LayersPanel } from "../Layers";
import { LayerLanes } from "../LayerLanes";
import { ColourMatchSheet } from "../ColourMatch";
import { SupervisorSheet } from "../Supervisor";
import { PerformanceSheet } from "../Performance";
import { LibrarySheet } from "../Board";
import type { Job, LoadedProject, Shot } from "../api";
import directions from "./directions.json";
import styles from "../../analysis/pulseframe_analysis/styles.json";
import "../styles.css";
import "../wizard.css";
import "../motion.css";
import "../acting.css";
import "../sound.css";
import "../focus.css";
import "../polish.css";
import "../corners.css";

const DIR = "/src/docshots/img";
(window as unknown as { __PF_MOCK__: boolean }).__PF_MOCK__ = true;
const q = new URLSearchParams(location.search);
const scene = q.get("scene") ?? "review";
const now = Math.floor(Date.now() / 1000);

// ---------------------------------------------------------------- made-up data
const ids = ["S01-01", "S01-02", "S01-03", "S01-04", "S01-05", "S01-06", "S02-01", "S02-02"];
const shots: Shot[] = ids.map((id, i) => ({ id, scene: id.startsWith("S01") ? 1 : 2, number: i + 1, start: i * 6.5, end: i * 6.5 + 6, beats: ["Sege looks at the sea."], source_shots: [], performers: ["Sege"], framing: ["Close-up", "Wide", "Medium", "Over the shoulder"][i % 4], state: "ready", renderer: "x" }));
const still = (n: number) => `s${(n % 6) + 1}.png`;
const issue = (kind: string, severity: "minor" | "major", detail: string) => ({ kind, severity, detail, fix: "" });
const mk = (id: string, shot: string, created: number, over: Record<string, unknown> = {}): Job => ({ id, shot_id: shot, plan: "production", provider: "kie", model: "bytedance/seedance-2", state: "ready", kind: "video", output: `v${(created % 3) + 1}.mp4`, created, updated: created, overrides: {}, cost: 50, cost_unit: "credits", ...over } as unknown as Job);
const reviewJobs: Job[] = [
  mk("a1", "S01-03", 100, { review: { reviewed: true, status: "good", summary: "Looks good.", issues: [] } }),
  mk("a2", "S01-03", 200, { review: { reviewed: true, status: "needs_attention", summary: "The mood is strong, but the shot is framed as a full facial close-up instead of the specified ear-cheek-jaw detail.", issues: [issue("framing", "major", "The frames show Sege's full face and eyes, with a lot of bedroom background, rather than a tight close-up on his ear, cheek, beard, and jaw."), issue("wardrobe", "minor", "Sege's green outer shirt collar is prominent, while the shot calls for the white undershirt collar visible against his neck."), issue("anatomy", "major", "The held hands are fused into one mass; the fingers can't be told apart.")] } }),
  mk("b1", "S02-02", 100, { review: { reviewed: true, status: "good", summary: "Looks good.", issues: [] } }),
  mk("b2", "S02-02", 200, { review: { reviewed: true, status: "needs_attention", summary: "The emotional beat is present, but the shot is too wide and the scar is not clearly revealed.", issues: [issue("framing", "major", "This is a medium view of Sege from the waist up, not the requested static close-up on his hand, open shirt edge, and scar."), issue("wardrobe", "minor", "The white undershirt covers most of Sege's chest, so the open linen shirt does not clearly reveal the faint scar.")] } }),
  mk("c1", "S01-01", 100, { review: { reviewed: true, status: "needs_attention", summary: "Sege's hands look wrong in this take.", issues: [issue("anatomy", "major", "Fingers on the left hand are fused.")] } }),
  mk("d1", "S01-02", 100, { review: { reviewed: true, status: "minor", summary: "Slightly dark but usable.", issues: [issue("look", "minor", "The light is a little darker than the look asks for.")] } }),
  mk("e1", "S01-04", 100, { review: { reviewed: true, status: "good", summary: "Looks good.", issues: [] } }),
  mk("f1", "S02-01", 100, { review: { reviewed: true, status: "minor", summary: "Good, with a small continuity slip.", issues: [issue("wardrobe", "minor", "The jacket is slightly lighter than in the previous shot.")] } }),
];
const queueJobs: Job[] = [
  mk("q1", "S01-01", 1, { created: now - 200, updated: now - 5, state: "submitted", output: null, submitted: now - 90, progress: 0.4 }), mk("q2", "S01-02", 2, { created: now - 150, updated: now - 150, state: "queued", output: null }),
  mk("q3", "S01-03", 3, { created: now - 400, updated: now - 120, state: "failed", output: null, error: "The provider had an internal error. Nothing was sent or charged. Provider said: 500 Internal Server Error", error_kind: "service", estimate_usd: 0.9 }),
  mk("q4", "S02-01", 4, { created: now - 500, updated: now - 60 }),
];
const lightShots = ids.flatMap((id, i) => {
  const rows = [["Calm", "Golden hour", 5600, 1], ["Calm", "Golden hour", 5600, 1], ["Tension", "Single hard key", 5600, 2], ["Tension", "Single hard key", 5600, 2], ["Tension", "Single hard key", 5600, 2], ["Hope", "Golden hour", 4500, 1], ["Joy", "Golden hour", 4800, 1], ["Nostalgia", "Golden hour", 3400, 2]] as const;
  const [label, name, kelvin, level] = rows[i];
  return [{ shot: id, scene: id.startsWith("S01") ? 1 : 2, start: i * 2.2, end: i * 2.2 + 2, section: "verse", mood: label.toLowerCase(), label, valence: 0, arousal: 0, intensity: 0.4, user_set: false, held: i === 1,
    why: `${label} (read from the feeling and words of the shot; the song is quiet here) → ${name.toLowerCase()}, neutral, gentle contrast.`,
    design: { label: name, kelvin, level, wording: `${name.toLowerCase()} sunlight, warm low rays and long shadows; neutral colour (about ${kelvin} K); key large and soft from a window; gentle contrast; colour accents: pale neutral` } }];
});
const lightingPlan = { count: lightShots.length, user_set: 0, shots: lightShots, scenes: [{ scene: 1, heading: "INT. SEGE'S BEDROOM - BEFORE DAWN", from: "Calm", to: "Hope", arc: "Calm → Tension → Hope", terms: [] }, { scene: 2, heading: "INT. SEGE'S KITCHEN / CHILDHOOD HOME - MORNING", from: "Joy", to: "Nostalgia", arc: "Joy → Calm → Nostalgia", terms: [] }] };
const cleanupItems = Array.from({ length: 12 }, (_, i) => ({ path: `v${(i % 3) + 1}.mp4`, name: `take-${i}.mp4`, kind: "video" as const, size: (3 + (i % 5)) * 1.2e6, shot: ids[i % ids.length], model: ["image-to-video", "seedance-2-mini", "video-to-video-lipsync", "3-0-video"][i % 4], created: now - 5000, cost: null, cost_unit: null, what: "older take" }));
const cleanupScan = { items: cleanupItems, bytes: 4.2e7, kept: 31, rendering: 0, trash: { batches: 1, files: 4, bytes: 9e6 } };
const row = (label: string, provider: string, model: string, price: number | null, verified: boolean, extra: Record<string, unknown> = {}) => ({ label, provider, model, price_usd: price, verified, strength: "Keeps people looking like themselves from your reference pictures, at a low price.", consider: "For a whole project on a budget, and when the same characters appear in many shots.", watch: "Check hands and faces on important shots.", ...extra });
const project: LoadedProject = { dir: DIR, project: { title: "Exit Plan", state: "ready", song: "song.wav" }, song_path: null, song_map: null, production: null, directed: null, jobs: [],
  concepts: { concepts: [
    { title: "The Long Way Home", premise: "A son walks the streets of his childhood at dawn, remembering the people who raised him, until the song's last chorus brings him to his mother's door.", mood: "Tender, nostalgic", performance_approach: "Performance woven into memory: he sings to no one, then to everyone.", cinematic_style: "Handheld, warm, shallow focus; long takes that drift with him.", palette: ["faded amber", "dusty blue", "cream", "deep green"], environment: "Lagos streets at dawn, a market, a kitchen with the radio on.", wardrobe: "A worn linen shirt, white undershirt, a bracelet.", movement: "Slow walking, small gestures, a held hand.", narrative_level: "narrative", hero_frame: "Sege in the doorway, morning light on his face, a woman's hand reaching for his.", suggested_look: "painterly" },
    { title: "One Room, One Night", premise: "The whole song in a single bedroom lit by the city outside: a man who cannot sleep, a partner who can, and the distance between them.", mood: "Intimate, restless", performance_approach: "Close, quiet, mostly on his face.", cinematic_style: "Static frames, hard single-source light, slow push-ins.", palette: ["night blue", "tungsten amber", "charcoal"], environment: "A bedroom above a city, rain on the window.", wardrobe: "A white tee, bare feet.", movement: "Barely any: breathing, turning, a hand on a sheet.", narrative_level: "hybrid", hero_frame: "His eye, open in the dark, the skyline reflected in it.", suggested_look: "cinematic" },
    { title: "Carnival of Small Things", premise: "The song as a parade: everyday objects and neighbours dancing through the neighbourhood, with Sege leading it, part conductor and part passenger.", mood: "Joyful, bright", performance_approach: "Big, rhythmic, ensemble.", cinematic_style: "Wide, symmetrical, saturated, whip pans on the beat.", palette: ["marigold", "hot pink", "turquoise", "primary accents"], environment: "A neighbourhood in festival, rooftops, a street market.", wardrobe: "Bright layered clothes, fabric prints.", movement: "Dancing, walking in step, throwing colour.", narrative_level: "performance", hero_frame: "Sege on a rooftop, the whole street below in colour, arms wide.", suggested_look: "vivid" },
  ] } };

const layer = (id: string, kind: string, text: string, start: number | null, end: number | null, over: Record<string, unknown> = {}) => ({ id, kind, text, source: "own", start, end, x: 0.5, y: 0.5, size: 0.08, width: 0.6, color: "#ffffff", fade: 0.3, enabled: true, placed: start !== null, reason: "", explicit: true, explicit_end: true, ...over });
const layerList = [layer("l1", "text", "Exit Plan", 2, 7), layer("l2", "icon", "Heart", 4, 9, { icon: "heart" }), layer("l3", "fill", "Warm tint", 0, 30, { color: "#e8b45c", opacity: 0.18 }), layer("l4", "text", "Lagos, 2019", 12, 16)];
const colourState = { enabled: true, strength: 0.7, reference: null, analysed: 12, adjusted: 2, rows: ids.map((id, i) => ({ shot: id, distance: i === 2 ? 0.34 : i === 5 ? 0.22 : 0.05 + (i % 3) * 0.02, bright: i === 2 ? 0.3 : -0.2, adjusted: i === 2 || i === 5, is_reference: false })) };

// ---------------------------------------------------------------- the made-up backend
mockWindows("main");
mockIPC((cmd, a) => {
  const x = (a ?? {}) as { action?: string; data?: Record<string, unknown> };
  switch (cmd) {
    case "library": if (x.action === "library") return { items: [
        { id: "c1", kind: "character", name: "Sege", files: ["s1.png", "s2.png"], notes: "Mid-thirties, linen shirt, bracelet", sheet: true }, { id: "c2", kind: "character", name: "Amara", files: ["s3.png"], sheet: true },
        { id: "s1", kind: "set", name: "Kitchen, morning", files: ["s4.png"], notes: "Warm light, radio on" }, { id: "s2", kind: "set", name: "Night train platform", files: ["s5.png"] },
        { id: "p1", kind: "prop", name: "Red toy car", files: ["s6.png"] }, { id: "st1", kind: "style", name: "Painterly warm", files: ["s2.png"] }],
        assign: { project: ["c1", "st1"], scenes: { "2": { add: ["s1"] } }, shots: {} } };
      if (x.action === "bible") return { world: "", tone: "", rules: "", avoid: "" };
      if (x.action === "storyboard") return { plan: "p", shots: ids.map((id, i) => ({ id, scene: 1, start: i * 6, end: i * 6 + 5, beat: "", performers: [], status: "ready", locked: false, approved: null, thumb_src: `t${i}.png`, thumb_source: "keyframe", preview: null, keyframe: still(i), versions: [], references: [] })), library: { characters: [], places: [], props: [], styles: [] } }; if (x.action === "thumbs") return Object.fromEntries(((x.data?.srcs as string[]) ?? []).map((s, i) => [s, still(i + s.length)])); return null;
    case "list_styles": return styles.styles;
    case "direction_library":
      if (x.action === "list") return { directions, current: "wong-kar-wai-mood" };
      if (x.action === "match") return { matches: ["french-new-wave", "wong-kar-wai-mood", "lagos-nights", "cairo-cinema", "chinese-wuxia", "bollywood-spectacle", "ghibli-pastoral", "thai-dreamlike"].map((id, i) => ({ id, score: 1, why: i < 3 ? ["tempo 120 BPM fits", "mid energy", "mood: romantic"] : [] })), song: { bpm: 120, energy: "mid", moods: ["Romantic", "Intimate"] } };
      return null;
    case "supervisor": return { items: [
      { id: "i1", shot: "S01-02", source: "keyframe check", severity: "major", title: "Fused hands", detail: "The held hands are fused into one mass; the fingers can't be told apart.", fix: "Redraw with the hands apart and five fingers each.", kind: "image", render: null, actions: ["fix", "regenerate", "accept", "ignore"], status: "open" },
      { id: "i2", shot: "S02-02", source: "take review", severity: "minor", title: "Soft left hand", detail: "The left hand is soft and slightly out of focus.", fix: "", kind: "video", render: null, actions: ["regenerate", "accept", "ignore"], status: "open" },
      { id: "i3", shot: "S01-04", source: "continuity", severity: "info", title: "Jacket colour changes", detail: "The jacket is blue here and green in the shot before.", fix: "", kind: "image", render: null, actions: ["accept", "ignore"], status: "open" }],
      groups: [], summary: { open: 3, major: 1, minor: 1, info: 1, decided: 0, ready: false } };
    case "director_audit": return x.action === "audit" ? { planned: 70, directed: 76, ok: false, drops: [], uncovered: [], merges: [
      { shot: "S01-02", scene: 1, start: 13, end: 15, duration: 2, check: true, risks: ["different people are the focus of each beat", "two separate lyric or dialogue lines fall in one shot (only one can be lip-synced)"], note: "All scripted beats are preserved in order; the final match cut also carries the aftermath so the scene lands without an extra cut.",
        sources: [{ id: "S01-02", cue: ["Survival instinct"], people: ["Amara", "Sege"], description: "Wide establishing shot of the warm kitchen with Amara preparing tea. Then: close-up of Amara smiling at Sege." }, { id: "S01-03", cue: [], people: ["Sege"], description: "Over Sege's shoulder as his imaginary duplicate packs behind him." }] },
      { shot: "S01-05", scene: 1, start: 27, end: 29, duration: 2, check: false, risks: ["each of the 2 actions gets under 2 seconds"], note: "", sources: [{ id: "S01-05", cue: [], people: [], description: "Rapid push into the dark childhood corridor." }, { id: "S01-06", cue: [], people: ["Young Sege"], description: "Low medium shot of Young Sege sitting with the red toy car." }] },
      { shot: "S02-01", scene: 2, start: 31, end: 33, duration: 2, check: false, risks: [], note: "", sources: [{ id: "S02-01", cue: [], people: ["Sege"], description: "Intimate profile of their kiss." }, { id: "S02-02", cue: [], people: ["Amara"], description: "Close-up of Amara laughing gently." }] }] } : null;
    case "review_backlog": return { unchecked: 0 };
    case "lipsync_check": return { shots: 0 };
    case "acting": return { arc: { sections: ["verse", "chorus", "bridge"], characters: ["Sege", "Amara"], arcs: { Sege: { points: [], source: null }, Amara: { points: [], source: null } } }, business: { Sege: [], Amara: [] } };
    case "performance": return { profiles: [{ id: "natural", label: "Natural", blurb: "Truthful, everyday acting. Small motivated gestures; the default." }, { id: "restrained", label: "Restrained", blurb: "Held back, internal. Emotion shows in the eyes and breath, not the face." }, { id: "expressive", label: "Expressive", blurb: "Open and readable. Clear faces and gestures, still grounded." }, { id: "dramatic", label: "Dramatic", blurb: "Heightened, cinematic. Big emotional beats, strong poses, held moments." }, { id: "energetic", label: "Energetic", blurb: "High energy for up-tempo songs: movement, rhythm, performance to camera." }], default: "dramatic", set: true, scenes: {}, characters: {}, shots: {} };
    case "overlays": return x.action === "list" ? layerList : null;
    case "colour_match": return colourState;
    case "lighting": return lightingPlan;
    case "cleanup": return cleanupScan;
    case "keyframe_set":
      if (x.action === "check_plan") return { flagged: [{ shot: "S01-02", image: "s2.png", state: "fail", locked: false, detail: "The held hands are fused into one mass; the fingers can't be told apart." }, { shot: "S02-02", image: "s3.png", state: "look", locked: false, detail: "The left hand is soft." }], shots: ["S01-01", "S01-04", "S02-02"], already: ["S01-02"], skipped: [], usd_est: 0.06, can_check: true, unavailable: "" };
      if (x.action === "remake_plan") return { shots: ["S01-02"], skipped: [], usd_est: 0.1 };
      if (x.action === "remodel_plan") return { target: { provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", price_usd: 0.03 }, shots: ["S01-02", "S01-05", "S02-01"], from: [], skipped: [{ shot: "S01-04", reason: "your own picture" }], used: [{ provider: "kie", model: "google/nano-banana-edit", count: 9 }, { provider: "kie", model: "gpt/gpt-image-2-5-flare-image-to-image", count: 3 }], usd_est: 0.75 };
      if (x.action === "swap_status") return { making: 1, ready: 2, failed: 0, shots_ready: [], reasons: {} };
      return null;
    case "frames":
      if (x.action === "get") return { "S01-01": { start: "s1.png", start_mode: "keyframe", end: "s2.png", end_mode: "own", end_state: "She turns to face him, the light behind her.", next: "S01-02", prev: null, next_has_start: false } };
      if (x.action === "support") return { title: "Seedance 2", shots: { "S01-01": { model: "bytedance/seedance-2", swapped: false, supports_end: true, proven: true, end: "project:s2.png" } } };
      if (x.action === "options") return { shots: {}, active: 0 };
      return null;
    case "hand_fix": return x.action === "plan" ? { model: { label: "Nano Banana", price_usd: 0.03 }, variants: 1, usd_est: 0.03 } : null;
    case "retry_cheaper": return { can: true, original_usd: 0.9, options: [
      { provider: "fal", model: "fal-ai/wan/v2.2-a14b/image-to-video/turbo", label: "Wan 2.2 Turbo", price_usd: 0.1, cheaper: true, saves_usd: 0.8, strength: "A cheap, quick Wan; proven to land on an end picture.", warning: "" },
      { provider: "kie", model: "wan/3-0-video", label: "Wan 3.0", price_usd: 0.45, cheaper: true, saves_usd: 0.45, strength: "Low price. PULSEFRAME's Balanced video choice.", warning: "" }] };
    case "routing":
      if (x.action === "pick") return (x.data as { kind?: string } | undefined)?.kind === "video" ? { provider: "kie", model: "wan/3-0-video", label: "Wan 3.0", free: false, mode: "balanced", verified: true, price_usd: 0.45 } : { provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", free: false, mode: "balanced", verified: true, price_usd: 0.03 };
      if (x.action === "models") return { video: [row("Seedance 2", "kie", "bytedance/seedance-2", 0.9, true, { strength: "Takes a start and an end picture, can also use reference pictures, video and sound, and can speak lines.", consider: "For shots that must land on an end frame and shots with sung or spoken lines.", watch: "Costs more per shot." }), row("Wan 3.0", "kie", "wan/3-0-video", 0.45, true, { strength: "Low price. PULSEFRAME's Balanced video choice.", consider: "For a whole video on a budget.", watch: "" }), row("Kling", "kie", "kling-2.6/image-to-video", 0.7, true), row("Hailuo 2.3", "fal", "fal-ai/minimax/hailuo-2.3/standard/image-to-video", 0.5, false)],
        image: [row("Nano Banana", "kie", "google/nano-banana-edit", 0.03, true, { sees_references: true }), row("GPT Image 2.5 Flare", "kie", "gpt/gpt-image-2-5-flare-image-to-image", 0.25, true, { sees_references: true, strength: "Follows detailed instructions closely and draws clean, readable text. Sees your character sheets.", consider: "For hero shots and anything with writing in it.", watch: "Costs the most of the picture models." }), row("Seedream 4.5", "kie", "seedream/4-5-edit", 0.06, true, { sees_references: true })], advice: "Use one picture model for the whole project. Two models draw people, light and colour differently, so mixing them across keyframes can make a character look different from shot to shot." };
      return { mode: "balanced", chosen: true, budget_usd: 25, spent_usd: 7.4, remaining_usd: 17.6, online: true, auto_retry: false, pins: {},
        modes: [{ id: "local", label: "Local First", blurb: "Only this computer: ComfyUI, a local AI model, moving stills. Free and works offline." }, { id: "cheapest", label: "Cheapest", blurb: "The lowest real price per shot among proven models." }, { id: "balanced", label: "Balanced", blurb: "The cheapest proven cloud models." }, { id: "premium", label: "Premium", blurb: "The best proven models." }],
        video: { provider: "kie", model: "wan/3-0-video", label: "Wan 3.0", free: false, mode: "balanced", verified: true, price_usd: 0.45 }, image: { provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", free: false, mode: "balanced", verified: true, price_usd: 0.03 },
        brain: { provider: "openai", local: false }, works_offline: ["Moving stills and your own media", "Export"],
        consistency: { image_models: [{ provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", count: 9 }, { provider: "kie", model: "gpt/gpt-image-2-5-flare-image-to-image", label: "GPT Image 2.5 Flare", count: 3 }], mixed: true, pinned: false, advice: "" } };
    case "compose": {
      if (x.action === "library_list") return [
        { id: "a1b2c3d4e5", name: "Slow walk", seconds: 8.2, width: 1080, height: 1920, added: now, thumb: null, tags: ["walk", "slow"], path: `${DIR}/v1.mp4` },
        { id: "b2c3d4e5f6", name: "Salsa step", seconds: 12.4, width: 1080, height: 1920, added: now, thumb: null, tags: ["dance"], path: `${DIR}/v2.mp4` },
        { id: "c3d4e5f6a7", name: "Runway turn", seconds: 6, width: 1080, height: 1920, added: now, thumb: null, tags: ["walk", "fashion"], path: `${DIR}/v3.mp4` }];
      if (x.action === "models") return { start_end: [], references: [], motion: [] };
      if (x.action === "state") return { shot: "S01-01", shot_seconds: 6, video: null, video_seconds: null, image: "s1.png", image_is_start: true, orientation: "video", quality: "std", background: "video", note: "", notes: [], ready: false, missing: ["a motion video"], prompt: { mode: "auto", text: "", only: false } };
      return null;
    }
    default: return null;
  }
});

// ---------------------------------------------------------------- the scenes
const noop = () => {};
const keys = { openai: true, fal: true, kie: true, google: false, elevenlabs: false } as never;
const take = (id: string, _shot: string, n: number, over: Record<string, unknown> = {}) => ({ id, n, state: "ready", provider: "kie", model: "bytedance/seedance-2", output: `v${n}.mp4`, kind: "video", created: n, cost: n === 1 ? 50 : 38, cost_unit: "credits", approved: n === 1, ...over });
const card = (children: ReactNode, width = 480) => <div className="sheet glass" style={{ width }}>{children}</div>;
const scenes: Record<string, () => ReactNode> = {
  layers: () => <div style={{ width: 380, padding: 16 }} className="glass"><LayersPanel dir={DIR} selected="l1" onSelect={noop} onClose={noop} time={3} docked /></div>,
  layerlanes: () => <div style={{ width: 900, height: 120, position: "relative", background: "#10131a", overflow: "hidden" }}><LayerLanes dir={DIR} pps={40} duration={30} selected="l1" onSelect={noop} snap={[]} top={0} time={3} onSeek={noop} /></div>,
  library: () => <LibrarySheet dir={DIR} scenes={[{ number: 1, heading: "BEDROOM - BEFORE DAWN" }, { number: 2, heading: "KITCHEN - MORNING" }, { number: 3, heading: "MARKET - DAY" }]} onClose={noop} onChanged={noop} />,
  supervisor: () => <SupervisorSheet dir={DIR} onClose={noop} onReview={noop} onChanged={noop} />,
  acting: () => <PerformanceSheet dir={DIR} scenes={[{ number: 1, heading: "INT. SEGE'S BEDROOM - BEFORE DAWN" }, { number: 2, heading: "INT. SEGE'S KITCHEN - MORNING" }]} characters={["Sege", "Amara", "Young Sege"]} onClose={noop} onChanged={noop} />,
  colourmatch: () => <ColourMatchSheet dir={DIR} onClose={noop} />,
  review: () => <ReviewSheet dir={DIR} shots={shots} jobs={reviewJobs} inUse={{ "S01-03": "a1", "S02-02": "b1" }} keys={keys} onSelect={noop} onJobs={noop} onClose={noop} />,
  queue: () => <RenderQueueSheet dir={DIR} jobs={queueJobs} shots={shots} onJob={noop} onShow={noop} onReview={noop} onClose={noop} />,
  retry: () => <RenderQueueSheet dir={DIR} jobs={queueJobs} shots={shots} onJob={noop} onShow={noop} onReview={noop} onClose={noop} />,
  keyframetools: () => <KeyframeTools dir={DIR} onClose={noop} />,
  handfix: () => <HandFix dir={DIR} shot="S01-02" image="s2.png" onClose={noop} />,
  planbudget: () => <RoutingSheet dir={DIR} onClose={noop} />,
  selectreview: () => <SelectReview dir={DIR} shots={ids.map((id, i) => ({ id, scene: 1, start: i * 6, end: i * 6 + 5, framing: ["Close-up", "Wide", "Medium", "Over the shoulder"][i % 4], beat: "", performers: [], status: "ready", locked: false, approved: null, thumb_src: null, thumb_source: "keyframe", preview: null, keyframe: still(i), versions: [], references: [] })) as never} sections={[{ label: "verse", group: "Verse 1", start: 0, end: 24 }, { label: "chorus", group: "Chorus", start: 24, end: 48 }] as never} initial={ids.slice(0, 4)} onClose={noop} onQueued={noop} />,
  compare: () => <div className="sheet glass viewer-sheet" style={{ width: 920 }}><div className="vs-head"><h2 className="num">Shot S01-03</h2></div><CompareLazy /></div>,
  directionlibrary: () => <DirectionLibrarySheet dir={DIR} onClose={noop} onApplied={noop} />,
  directions: () => <div style={{ maxWidth: 1180, margin: "0 auto", padding: 24 }}><CreativeDirections project={project} onPlanned={noop} onSettings={noop} /></div>,
  looks: () => <LookPicker value={{ style: "auto" }} director={false} onCancel={noop} onSave={noop} />,
  lighting: () => <LightingSheet dir={DIR} onClose={noop} />,
  cleanup: () => <CleanupSheet dir={DIR} onClose={noop} onChanged={noop} />,
  modelchoice: () => card(<><h2>Choose your picture model</h2><p className="sub">Choosing one fixes it for the whole project, which keeps your characters looking the same in every picture.</p><ModelChoice dir={DIR} kind="image" /></>, 560),
  compose: () => card(<ComposeTab dir={DIR} shot="S01-01" keys={keys} />, 460),
};
function CompareLazy() {
  const versions = [take("t1", "S01-03", 1), take("t2", "S01-03", 2, { model: "wan/3-0-video", cost: 22 })] as never[];
  return <TakeCompare left={versions[0]} right={versions[1]} src={(v: { output: string | null }) => (v.output ? `${DIR}/${v.output}` : null)} busy={false} locked={false} onUse={noop} onSwap={noop} />;
}

document.body.classList.add("docshot");
const root = createRoot(document.getElementById("root")!);
root.render(scenes[scene] ? scenes[scene]() : <p>Unknown scene: {scene}</p>);

// ---------------------------------------------------------------- scripted steps, then report the size of the page for the screenshot
const press = (text: string) => { const b = [...document.querySelectorAll("button, summary, [role=tab]")].find((e) => (e.textContent ?? "").trim().toLowerCase().startsWith(text.toLowerCase())); (b as HTMLElement | undefined)?.click(); };
setTimeout(() => {
  q.getAll("click").forEach((t, i) => setTimeout(() => press(t), i * 350));                 // one after another, so the screen can update between them
  const css = q.get("clickcss");
  if (css) (document.querySelector(css) as HTMLElement | null)?.click();
  const drag = q.get("drag");
  if (drag) {
    const [x0, y0, x1, y1] = drag.split(",").map(Number);
    const stage = document.querySelector(".hf-stage") as HTMLElement | null;
    if (stage) {
      const r = stage.getBoundingClientRect();
      const ev = (type: string, x: number, y: number) => stage.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: r.left + x * r.width, clientY: r.top + y * r.height, pointerId: 1 }));
      ev("pointerdown", x0, y0);                                                     // spaced out, so the screen can update between them as it does for a real mouse
      setTimeout(() => ev("pointermove", x1, y1), 120);
      setTimeout(() => ev("pointerup", x1, y1), 260);
    }
  }
}, 900);
setTimeout(() => {
  const rootEl = document.getElementById("root")!;
  const sheet = document.querySelector(".sheet") as HTMLElement | null;
  const first = (sheet ?? rootEl.firstElementChild) as HTMLElement | null;
  const w = Math.ceil((first?.getBoundingClientRect().width ?? 1000) + 48);
  const outer = (document.querySelector(".overlay") ?? first) as HTMLElement | null;
  const h = Math.ceil(outer?.getBoundingClientRect().height ?? rootEl.getBoundingClientRect().height);
  document.title = `${w},${h}`;
}, 2600);
