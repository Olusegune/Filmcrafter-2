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
import { ModelPicker } from "../ModelPicker";
import { ModelChoice } from "../ModelChoice";
import { ComposeTab } from "../Compose";
import { TakeCompare } from "../Compare";
import { LayersPanel } from "../Layers";
import { LayerLanes } from "../LayerLanes";
import { ColourMatchSheet } from "../ColourMatch";
import { SupervisorSheet } from "../Supervisor";
import { PerformanceSheet } from "../Performance";
import { LibrarySheet } from "../Board";
import { Home } from "../Home";
import { NewFilm } from "../NewFilm";
import { FilmView } from "../FilmView";
import { CastWorld } from "../CastWorld";
import { ShotLab } from "../ShotLab";
import { MakeFilm } from "../MakeFilm";
import { FilmContinuity } from "../FilmContinuity";
import { AssistSheet } from "../AssistSheet";
import { ShotSuggestionSheet } from "../ShotSuggestionSheet";
import { Studio } from "../Studio";
import renderFixture from "./render-fixture.json";
import type { Job, LoadedProject, Shot } from "../api";
import directions from "./directions.json";
import styles from "../../analysis/filmcrafter_engine/styles.json";
import "../styles.css";
import "../studio-shared.css";
import "../motion.css";
import "../acting.css";
import "../sound.css";
import "../focus.css";
import "../polish.css";
import "../film.css";
import "../corners.css";
import "../ui-system.css";            // after everything: one set of controls, one focus ring

const DIR = "/src/docshots/img";
(window as unknown as { __PF_MOCK__: boolean }).__PF_MOCK__ = true;
const q = new URLSearchParams(location.search);
// ?n=300 makes the sample film that long, to see how the screens hold up (the engine's own numbers for a 300-shot film are in docs/QA.md)
const N = Math.max(0, Number(q.get("n")) || 0);
const bigId = (i: number) => `S${String(Math.floor(i / 8) + 1).padStart(2, "0")}-${String((i % 8) + 1).padStart(2, "0")}`;
const grow = <T extends { id: string; scene?: number }>(list: T[]): T[] => (N > list.length ? Array.from({ length: N }, (_, i) => ({ ...list[i % list.length], id: bigId(i), scene: Math.floor(i / 8) + 1 })) : list);
const scene = q.get("scene") ?? "review";
const now = Math.floor(Date.now() / 1000);

// ---------------------------------------------------------------- made-up data
const ids = N > 8 ? Array.from({ length: N }, (_, i) => bigId(i)) : ["S01-01", "S01-02", "S01-03", "S01-04", "S01-05", "S01-06", "S02-01", "S02-02"];
const shots: Shot[] = ids.map((id, i) => ({ id, scene: Number(id.slice(1, 3)), number: i + 1, start: i * 6.5, end: i * 6.5 + 6, beats: ["Sege looks at the sea."], source_shots: [], performers: ["Sege"], framing: ["Close-up", "Wide", "Medium", "Over the shoulder"][i % 4], state: "ready", renderer: "x" }));
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
  const [label, name, kelvin, level] = rows[i % rows.length];
  return [{ shot: id, scene: Number(id.slice(1, 3)), start: i * 2.2, end: i * 2.2 + 2, section: "verse", mood: label.toLowerCase(), label, valence: 0, arousal: 0, intensity: 0.4, user_set: false, held: i === 1,
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
const colourState = { enabled: true, strength: 0.7, reference: null, analysed: 12, adjusted: 2, cast: true, cast_strength: 0.85, cast_seen: { u: -14, v: 6, size: 15.2, label: "yellow", noticeable: true }, cast_fix: { u: 12, v: -5 }, denoise: false, grain: false, picture_care: true, rows: ids.map((id, i) => ({ shot: id, distance: i === 2 ? 0.34 : i === 5 ? 0.22 : 0.05 + (i % 3) * 0.02, bright: i === 2 ? 0.3 : -0.2, adjusted: i === 2 || i === 5, is_reference: false })) };

const filmText = ["INT. KITCHEN - MORNING", "", "Sarah pours tea. Her hands are not steady.", "", "SARAH", "(quietly)", "He said he would call.", "", "JOHN (O.S.)", "Did you say something?", "", "EXT. PLATFORM - NIGHT", "", "Rain on the roof. A train waits.", "", "SARAH", "I am going.", "", "JOHN", "Then go.", "", "INT. TRAIN - NIGHT", "", "Sarah sits. She looks at her phone. Nothing."].join(String.fromCharCode(10));
const filmScene = (number: number, heading: string, line: number, location: string, time: string, characters: string[], d: number, a: number, int_ext = "INT") => ({ number, heading, int_ext, location, time, characters, dialogue_lines: d, action_lines: a, words: 20, seconds: 48 + number * 6, line });
const filmStatus = { title: "Last Train", aspect_ratio: "16:9", mode: "simple", stage: "story", created: now,
  story: { kind: "screenplay", current: 2, locked: null, lock_history: [], as_is: null, original: "last-train.fountain" }, version: 2, text: filmText, kind: "screenplay", note: "Sharper ending", locked_here: false,
  found: { kind: "screenplay", words: 61, pages: 2.4, rung: "screenplay", seconds: 144, has_headings: true,
    scenes: [filmScene(1, "INT. KITCHEN - MORNING", 0, "KITCHEN", "MORNING", ["SARAH", "JOHN"], 2, 1), filmScene(2, "EXT. PLATFORM - NIGHT", 11, "PLATFORM", "NIGHT", ["SARAH", "JOHN"], 2, 1, "EXT"), filmScene(3, "INT. TRAIN - NIGHT", 21, "TRAIN", "NIGHT", [], 0, 1)],
    characters: [{ name: "SARAH", scenes: [1, 2], scene_count: 2, first_scene: 1 }, { name: "JOHN", scenes: [1, 2], scene_count: 2, first_scene: 1 }], locations: [{ name: "KITCHEN", scenes: [1] }, { name: "PLATFORM", scenes: [2] }, { name: "TRAIN", scenes: [3] }] },
  advice: [
    { id: "thin-3", topic: "structure", text: "Scene 3 (INT. TRAIN - NIGHT) has almost nothing in it. Is it a transition, or is something missing?", scene: 3, status: "open" },
    { id: "talky-1", topic: "visual storytelling", text: "Scene 1 is almost all dialogue. A look, a gesture or an object could carry some of it.", scene: 1, status: "open" },
    { id: "length", topic: "production", text: "About 2.4 minutes of script. The first pass works best on one scene or a short of 1 to 3 minutes; you can start with one scene.", scene: null, status: "dismissed" }],
  versions: [{ version: 1, kind: "screenplay", note: "As supplied", parent: null, origin: "imported", created: now - 3600, fingerprint: "a1", locked: false, words: 58 }, { version: 2, kind: "screenplay", note: "Sharper ending", parent: 1, origin: "written", created: now, fingerprint: "b2", locked: false, words: 61 }] };

const spatialEmpty = { entrances: "", exits: "", doors: "One door, left of the stove", windows: "Large window over the sink, morning light", landmarks: "A radio on the shelf", furniture: "Round table, four chairs", blocking: "", camera_zones: "", lighting: "", day_night: "" };
const bibleView = { sound_style: { sound: { philosophy: "Quiet and close, like being in the room.", realism: "", ambience: "Rain, always, low.", dialogue: "Voices stay clear above everything.", silence: "After the letter." }, music: { genre: "Chamber", instrumentation: "Solo piano, a music box", mood: "Tender", tempo: "", influences: "", palette: "", motifs: "A music box for Lila", intensity: "", silence: "" } }, rev: 4, updated: now, rules: { world: "A coastal town where it rains most evenings.", tone: "Quiet, restrained, a little sad.", rules: "Sarah never takes off her ring.", avoid: "Slapstick, bright neon." },
  philosophy: { visual: "Muted, lived-in.", cinematography: "Mostly locked-off, slow pushes.", lighting: "Motivated, low key, practical lamps.", acting: "Restraint: the feeling shows in the eyes.", colour: "Teal shadows, amber practicals.", continuity: "Sarah's coat is torn after scene 2." },
  style: { lane: "painterly animation", notes: "", traits: "Oil paint texture, soft edges, visible brush marks.", references: ["Quiet domestic painting", "Overcast seaside light"] },
  characters: [
    { id: "c_sarah", name: "Sarah", role: "Lead", age: "28", physical: "Tall, grey eyes, dark hair tied back", relationships: "John's partner", arc: "From waiting to leaving", voice: "Low, careful", notes: "", wardrobe: [{ id: "w1", name: "Red coat", notes: "Wool, torn pocket" }],
      states: [{ id: "s1", label: "Default", notes: "" }, { id: "s2", label: "Age 8", notes: "Hair in plaits", age: "8", wardrobe: "" }], media: [{ path: "s1.png", kind: "master", label: "Master" }, { path: "s2.png", kind: "front", label: "Front view" }], scenes: [1, 2], source: "story" },
    { id: "c_john", name: "John", role: "", age: "", physical: "", relationships: "", arc: "", voice: "", notes: "", wardrobe: [], states: [{ id: "s1", label: "Default", notes: "" }], media: [{ path: "s3.png", kind: "master", label: "Master" }], scenes: [1, 2], source: "story" }],
  environments: [{ id: "e_kitchen", name: "Kitchen", description: "A narrow family kitchen", notes: "", spatial: spatialEmpty, states: [{ id: "s1", label: "Morning", notes: "" }, { id: "s2", label: "Night", notes: "" }], media: [{ path: "s4.png", kind: "master", label: "Master" }], scenes: [1], source: "story" },
    { id: "e_platform", name: "Platform", description: "", notes: "", spatial: { ...spatialEmpty, doors: "", windows: "", landmarks: "", furniture: "" }, states: [{ id: "s1", label: "Night", notes: "" }], media: [], scenes: [2], source: "story" }],
  props: [{ id: "p_the-letter", name: "The letter", notes: "Cream envelope", states: [{ id: "s1", label: "Default", notes: "" }], media: [], scenes: [], source: "manual" }],
  lanes: ["photoreal cinematic", "photoreal CGI", "feature 3D", "stylized 3D", "graphic 3D", "low-poly 3D", "hand-drawn 2D", "2D animation", "painterly animation", "anime-inspired", "graphic comic-inspired animation", "stop motion", "clay", "miniature", "mixed media", "experimental animation"],
  families: [{ id: "photoreal", name: "Photorealistic", blurb: "Looks like it was filmed: real light, real skin, real places.", lanes: ["photoreal cinematic", "photoreal CGI"] },
    { id: "3d", name: "3D animation", blurb: "Computer-made characters and worlds, from storybook to cel-shaded.", lanes: ["feature 3D", "stylized 3D", "graphic 3D", "low-poly 3D"] },
    { id: "2d", name: "2D animation", blurb: "Drawn and painted: classic hand-drawn, anime, comic and watercolour.", lanes: ["hand-drawn 2D", "2D animation", "painterly animation", "anime-inspired", "graphic comic-inspired animation"] },
    { id: "hybrid", name: "Hybrid 2D/3D", blurb: "Mixed worlds: 3D with drawn accents, collage, paper theatre, parallax.", lanes: [] },
    { id: "craft", name: "Hands-on crafts", blurb: "Made by hand and shot frame by frame: stop motion, clay, paper, miniatures.", lanes: ["stop motion", "clay", "miniature", "mixed media", "experimental animation"] },
    { id: "art", name: "Art movements & experimental", blurb: "Painting movements, print and folk art, and experimental graphic looks.", lanes: [] }].map((f) => ({ ...f, looks: (styles as { styles: { id: string; name: string; description: string; family: string }[] }).styles.filter((s) => s.family === f.id).map(({ id, name, description }) => ({ id, name, description })) })),
  genres: (styles as { styles: { id: string; name: string; description: string; family: string }[] }).styles.filter((s) => s.family === "genre").map(({ id, name, description }) => ({ id, name, description })),
  family: "craft", look: "stop-motion", genre: "g-biblical-epic", principles_custom: false,
  principles_on: ["squash-stretch", "anticipation", "staging", "follow-through", "slow-in-out", "arcs", "secondary-action", "timing", "exaggeration", "solid-drawing", "appeal"],
  principles: [["squash-stretch", "Squash and stretch", "Soft things flatten on impact and lengthen in fast motion, keeping their volume."], ["anticipation", "Anticipation", "A small opposite move prepares the big one: a crouch before a jump."],
    ["staging", "Staging", "One idea reads at once: a clear silhouette, nothing competing."], ["pose-to-pose", "Pose to pose", "Strong key poses first, then the in-betweens."],
    ["follow-through", "Follow-through and overlapping action", "Loose parts keep going a beat longer and settle at different times."], ["slow-in-out", "Slow in and slow out", "Movements ease in and out; nothing moves at one constant speed."],
    ["arcs", "Arcs", "Natural movement travels along curves, not straight lines."], ["secondary-action", "Secondary action", "A blink, a breath, a fidget supports the main action."],
    ["timing", "Timing", "How long a moment lasts says what it means."], ["exaggeration", "Exaggeration", "Push poses and faces a little past real life so the feeling reads."],
    ["solid-drawing", "Solid drawing", "Bodies keep weight and volume from every angle."], ["appeal", "Appeal", "Characters are easy to read and good to look at."]].map(([id, name, plain]) => ({ id, name, plain, fits: true, default: id !== "pose-to-pose" })),
  media_kinds: ["master", "front", "reference"], need: [], counts: { characters: 2, environments: 2, props: 1, characters_with_pictures: 2 } };

const blockingPlanMock = { people: [{ name: "Sarah", x: 30, y: 36, facing: 20 }, { name: "John", x: 72, y: 34, facing: 190 }], props: [{ name: "Tea", x: 24, y: 24 }], camera: { x: 12, y: 46, aim: 342, fov: 42 } };
const voiceStatus = {
  people: 5, recorded: 2, missing: 3, problems: 1,
  shots: [
    { id: "S01-02", scene: 1, title: "Lila speaks.", seconds: 3, others: ["Chloe"], notes: ["Lila: 3.4 s recording, 3.0 s shot: the shot is lengthened to hold it"],
      people: [{ name: "Lila", key: "lila", lines: ["She eats the weirdest stuff."], recording: { file: "voice/S01-02/lila.wav", name: "LILA_S01-02.wav", seconds: 3.4, rms_db: -21.2, peak_db: -4.1 } }] },
    { id: "S01-03", scene: 1, title: "Friend #1 speaks to Lila.", seconds: 2, others: [],
      people: [{ name: "Friend #1", key: "friend-1", lines: ["Like what?"], recording: { file: "voice/S01-03/friend-1.wav", name: "friend1_S01-03_take2.wav", seconds: 1.6, rms_db: -23.0, peak_db: -6.0 } },
               { name: "Lila", key: "lila", lines: ["Yesterday? It looked like... spiced beans?"], recording: null }] },
    { id: "S01-05", scene: 2, title: "Ethan speaks.", seconds: 5.4, others: ["Chloe"],
      people: [{ name: "Ethan", key: "ethan", lines: ["Hey. You coming to the thing on Friday?"], recording: null }] },
    { id: "S02-01", scene: 2, title: "Chloe speaks to Ethan.", seconds: 3.4, others: [], people: [{ name: "Chloe", key: "chloe", lines: ["I might."], recording: null }] },
  ],
};

const pickerCatalog = [
  { model: "kling/3-0", title: "Kling · Kling 3.0", rec: 1, fresh: true, sees: true },
  { model: "kling/v3-turbo-image-to-video", title: "Kling · V3 Turbo Image to Video", sees: true },
  { model: "kling/3-0-omni-image-to-video", title: "Kling · Kling 3.0 Omni Image To Video", sees: true },
  { model: "bytedance/seedance-2", title: "Bytedance · seedance-2", rec: 2, sees: true },
  { model: "bytedance/seedance-2-5", title: "Bytedance · Bytedance Seedance 2.5", rec: 3, fresh: true, sees: true },
  { model: "minimax/h3-image-to-video", title: "MiniMax · MiniMax H3 Image-to-Video", sees: true },
  { model: "wan/3-0-video", title: "Wan · Wan 3.0 - Video", sees: true },
  { model: "happyhorse/image-to-video", title: "HappyHorse · HappyHorse-1-1 image-to-video", sees: true },
  { model: "google/veo3-1", title: "Google · Veo 3.1", rec: 4, sees: true },
  { model: "runway/gen4", title: "Runway · Gen-4 Turbo", sees: true },
] as never[];
const blockingMock = { id: "S01-02", scene: 1, framing: "over the shoulder", plan: blockingPlanMock, suggested: null, has_previous: true, people: ["Sarah", "John"], room: { w: 100, h: 70 },
  text: "Blocking as the camera sees it: John screen-right, facing screen-left. Camera over Sarah's shoulder.",
  scene_shots: [{ id: "S01-01", framing: "wide", plan: { ...blockingPlanMock, camera: { x: 50, y: 66, aim: 270, fov: 65 } } }, { id: "S01-02", framing: "over the shoulder", plan: blockingPlanMock }, { id: "S01-03", framing: "over the shoulder", plan: { ...blockingPlanMock, camera: { x: 90, y: 20, aim: 190, fov: 40 } } }],
  crossings: [] as { shot: string; previous: string; message: string; fix: string }[] };
const continuityMock = { open: 3, shots: 6, findings: [
  { id: "f1", kind: "character", shot: "S02-03", other: "", severity: "likely", status: "open", text: "Sarah may have changed outfit: red coat in S02-02, grey cardigan in S02-03.", suggestion: "If the change is meant, ignore this. If not, set them to the same outfit." },
  { id: "f2", kind: "direction", shot: "S01-03", other: "", severity: "look", status: "open", text: "The camera is on the other side of the line between Sarah and John than in S01-02, so they may swap sides on screen.", suggestion: "Move the camera back to the other side of the dashed line, or cut away to an insert or a wide shot first." },
  { id: "f3", kind: "state", shot: "S01-04", other: "", severity: "note", status: "open", text: "S01-04 doesn't say how it begins. S01-03 ends: \"She puts the cup down.\".", suggestion: "Use that as how this shot begins.", apply: { opening_state: "She puts the cup down." } },
  { id: "f4", kind: "prop", shot: "S01-04", other: "", severity: "note", status: "noted", text: "The letter is in S01-03 but not listed in S01-04.", suggestion: "Add it to the next shot's props." }] } as never;
const shotCard = (id: string, scene: number, index: number, title: string, framing: string, duration: number, chars: string[], over: Record<string, unknown> = {}) => ({ id, scene, index, title, status: "draft", edited: false, story_purpose: title,
  camera: { framing, angle: "eye level", position: "", lens: "", movement: "locked off", focus: "", why: "" }, locks: { storyboard: false, keyframe: false }, duration, characters: chars, has_dialogue: chars.length > 0, environment: "Kitchen", ...over });
const shotsView = { title: "Last Train", story_version: 2, seconds: 21.5, scenes: [{ number: 1, shots: 4, seconds: 14.5 }, { number: 2, shots: 2, seconds: 7 }],
  shots: [shotCard("S01-01", 1, 1, "Show where we are: Kitchen (INT, Morning).", "wide", 4, []), shotCard("S01-02", 1, 2, "Sarah speaks to John.", "over the shoulder", 4.5, ["SARAH", "JOHN"], { locks: { storyboard: true, keyframe: false } }),
    shotCard("S01-03", 1, 3, "John speaks to Sarah.", "over the shoulder", 3, ["JOHN", "SARAH"]), shotCard("S01-04", 1, 4, "A detail that matters: letter.", "insert", 3, []),
    shotCard("S02-01", 2, 1, "Show where we are: Platform (EXT, Night).", "establishing", 4, []), shotCard("S02-02", 2, 2, "Sarah speaks.", "close-up", 3, ["SARAH"])],
  enums: { framing: ["establishing", "wide", "medium", "close-up", "extreme close-up", "over the shoulder", "point of view", "insert"], angle: ["eye level", "low", "high", "dutch", "overhead"], lens: ["wide (24mm)", "normal (35mm)", "portrait (50mm)", "telephoto (85mm+)", "macro"],
    movement: ["locked off", "push in", "pull out", "pan", "tilt", "dolly", "tracking", "orbit", "crane", "handheld", "rack focus", "subject tracking"], focus: ["deep", "shallow", "rack", "follow"] } };
const shotContract = { id: "S01-02", scene: 1, index: 2, story_version: 2, title: "Sarah speaks to John", status: "draft", edited: true, story_purpose: "Sarah lets slip that she is waiting for a call, and John does not notice.", action: "",
  dialogue: [{ speaker: "SARAH", line: "He said he would call.", paren: "quietly" }], characters: [{ name: "SARAH", character_id: "c_sarah", state_id: "s1", wardrobe_id: null }, { name: "JOHN", character_id: "c_john", state_id: "s1", wardrobe_id: null }],
  environment: { id: "e_kitchen", name: "Kitchen", state_id: "s1" }, props: [], blocking: "Sarah at the sink, John at the table behind her, looking at his phone.",
  performance: { emotional_intention: "Held-back dread", beats: [{ character: "Sarah", what: "Holds the cup too tightly", want: "He calls", need: "To accept he will not", fear: "Being alone", hiding: "That she has packed", subtext: "Stay", start: "Hopeful", turn: "Doubt", end: "Resolve" }], micro_animation: "A slow breath, a swallow before she speaks." },
  camera: { framing: "over the shoulder", angle: "eye level", position: "Behind John's left shoulder, on Sarah", lens: "portrait (50mm)", movement: "locked off", focus: "shallow", why: "Her face is where the story is." }, lighting: { description: "Low morning light through the window over the sink", time: "Morning", why: "Soft light makes the dread quieter." },
  opening_state: "Sarah holds the cup with both hands.", closing_state: "She puts the cup down.", continuity: "Ring on her left hand. Letter by the sink.", reference_assets: [], sound: "Kettle ticking as it cools.", generation: { duration: 4.5, aspect: "", notes: "" }, locks: { storyboard: true, keyframe: false } };
const shotSuggestion = { camera: { framing: "over the shoulder", angle: "low", position: "", lens: "portrait (50mm)", movement: "handheld", focus: "shallow", why: "Tension is felt up close: a tight frame, a slightly low angle and a small unsteadiness keep the audience uneasy." }, lighting: { description: "Hard, low-key light from one side; deep shadow on the rest of the face.", why: "Contrast and shadow say something is being held back." }, from: "the feeling of the shot" };

const opt = (job: string, image: string, state = "ready", model = "Nano Banana") => ({ job, image, state, model, provider: "kie", created: 1, ok: state === "ready" });
const mkShot = (id: string, scene: number, title: string, framing: string, d: number, sb: string | null, kf: string | null, lockedSb = false, lockedKf = false, takes: unknown[] = []) => ({ id, scene, title, duration: d, framing,
  storyboard: { options: sb ? [opt(id + "a", sb), opt(id + "b", "s2.png")] : [], chosen: sb, locked: lockedSb }, keyframe: { options: kf ? [opt(id + "k", kf)] : [], chosen: kf, locked: lockedKf }, video: { takes, approved: null } });
const makeStatus = { render_dir: DIR, active: 1, synced: true, soundtrack: { kind: "silence" }, counts: { shots: 6, storyboard: 4, keyframe: 2, video: 1 },
  shots: [mkShot("S01-01", 1, "Show where we are: Kitchen", "wide", 4, "s1.png", "s1.png", true, true, [{ job: "v1", video: null, state: "ready", model: "Seedance", provider: "kie", created: 1, approved: true, ok: false }]),
    mkShot("S01-02", 1, "Sarah speaks to John", "over the shoulder", 4.5, "s3.png", "s3.png", true), mkShot("S01-03", 1, "John speaks to Sarah", "over the shoulder", 3, "s4.png", null),
    mkShot("S01-04", 1, "A detail that matters: letter", "insert", 3, "s5.png", null), mkShot("S02-01", 2, "Show where we are: Platform", "establishing", 4, null, null), mkShot("S02-02", 2, "Sarah speaks", "close-up", 3, null, null)] };

// ---------------------------------------------------------------- the made-up backend
mockWindows("main");
mockIPC((cmd, a) => {
  const x = (a ?? {}) as { action?: string; data?: Record<string, unknown> };
  switch (cmd) {
    case "film_choreography": return x.action === "types" ? { types: [{ id: "fight", label: "Fist fight", blurb: "Two people, no weapons.", needs_b: true, good_for: "Close, handheld shots." }, { id: "chase", label: "Foot chase", blurb: "One runs, one follows.", needs_b: true, good_for: "Tracking shots." }], outcomes: [{ id: "a_wins", label: "The first side wins" }, { id: "draw", label: "Neither wins" }], intensity: [{ id: "grounded", label: "Grounded" }, { id: "heightened", label: "Heightened" }], limits: { min_beats: 4, max_beats: 14 }, advice: [] }
      : x.action === "list" ? { plans: [] }
      : { id: "ch-demo0001", type: "fight", scene: 1, place: "Platform", weapon: "", sides: { a: ["Sarah"], b: ["John"] }, intensity: "grounded", outcome: "a_wins", geography: "Sarah enters screen-left and John screen-right and they stay that way. Cross the line only on a cutaway.", people: ["Sarah", "John"], seconds: 12.5, warnings: ["Contact is cut around on purpose: the blow and the landing are separate shots."], after: "S01-02", applied: [], status: "draft",
          beats: [{ n: 1, phase: "establish", kind: "establish", actor: null, momentum: "even", text: "Platform: Sarah and John, a few paces apart.", seconds: 4, framing: "establishing", movement: "locked off", angle: "eye level", lens: "wide (24mm)", sound: "wind, distance", title: "Fist fight 1/4", carrying: "" },
                  { n: 2, phase: "strike", kind: "action", actor: "Sarah", momentum: "A", text: "Sarah throws a heavy right hand at John's jaw", seconds: 3, framing: "medium", movement: "handheld", angle: "eye level", lens: "normal (35mm)", sound: "a dull thud", title: "Fist fight 2/4", carrying: "" },
                  { n: 3, phase: "land", kind: "reaction", actor: "John", momentum: "A", text: "John's head snaps to the side and he staggers a step (Carrying: John has a split lip.)", seconds: 2.5, framing: "close-up", movement: "handheld", angle: "eye level", lens: "portrait (50mm)", sound: "a grunt", title: "Fist fight 3/4", carrying: "John has a split lip" },
                  { n: 4, phase: "aftermath", kind: "aftermath", actor: "Sarah", momentum: "A", text: "Sarah stands over John, breathing hard; it is over", seconds: 3, framing: "wide", movement: "pull out", angle: "high", lens: "wide (24mm)", sound: "silence settling", title: "Fist fight 4/4", carrying: "" }] };
    case "film_placecare": return { places: [{ id: "e_playground", name: "Lincoln Middle School - Playground - Day", scenes: [1, 5], has_description: false, has_layout: false, has_picture: false, missing: true }, { id: "e_hall", name: "Hallway", scenes: [2], has_description: true, has_layout: false, has_picture: false, missing: false }], missing: ["e_playground"], filled: x.action === "draft" ? [{ id: "e_playground", name: "Lincoln Middle School - Playground - Day", description: "From the story: ..." }] : undefined, note: "" };
    case "film_pacing": return { film: { shots: 8, seconds: 31.5, asl: 3.9, shortest: 1.2, longest: 7 }, scenes: [{ number: 1, shots: 5, seconds: 21, asl: 4.2, shortest: 2, longest: 7, bars: [{ id: "S01-01", seconds: 4 }, { id: "S01-02", seconds: 7 }, { id: "S01-03", seconds: 3 }, { id: "S01-04", seconds: 5 }, { id: "S01-05", seconds: 2 }] }, { number: 2, shots: 3, seconds: 10.5, asl: 3.5, shortest: 1.2, longest: 6, bars: [{ id: "S02-01", seconds: 3.3 }, { id: "S02-02", seconds: 1.2 }, { id: "S02-03", seconds: 6 }] }],
      findings: [{ level: "fix", shot: "S01-03", scene: 1, what: "S01-03 lasts 3.0 s but its dialogue needs about 5.8 s.", why: "People speak at about 2.5 words a second, with a breath either side; a shorter shot means the voice is cut off or hurried.", tip: "Lengthen the shot to 5.8 s, or cut the line." }, { level: "note", shot: "S02-01", scene: 2, what: "Scene 2 does not open on a wide shot.", why: "A wide first shot tells the audience where they are.", tip: "Make the first shot wide or establishing." }], counts: { fix: 1, look: 0, note: 1 }, note: "Advice only." };
    case "film_composition": return x.action === "set" ? { in_prompt: true } : { size: "close", shot: "S01-02", in_prompt: true, horizon: null, grid: [0.333, 0.667], text: "", points: [{ name: "Sarah", x: 0.333, y: 0.333 }],
      lines: [{ text: "The eyes sit on the upper third line, with just enough headroom.", why: "A close-up is about the eyes." }, { text: "Leave look room on the right, in front of the face.", why: "Space in front of a face lets the thought go somewhere." }] };
    case "confirm_spend": return "docshot-token";
    case "plugin:dialog|open": return ["C:/boards/storyboard"];
    case "library": if (x.action === "library") return { items: [
        { id: "c1", kind: "character", name: "Sege", files: ["s1.png", "s2.png"], notes: "Mid-thirties, linen shirt, bracelet", sheet: true }, { id: "c2", kind: "character", name: "Amara", files: ["s3.png"], sheet: true },
        { id: "s1", kind: "set", name: "Kitchen, morning", files: ["s4.png"], notes: "Warm light, radio on" }, { id: "s2", kind: "set", name: "Night train platform", files: ["s5.png"] },
        { id: "p1", kind: "prop", name: "Red toy car", files: ["s6.png"] }, { id: "st1", kind: "style", name: "Painterly warm", files: ["s2.png"] }],
        assign: { project: ["c1", "st1"], scenes: { "2": { add: ["s1"] } }, shots: {} } };
      if (x.action === "bible") return { world: "", tone: "", rules: "", avoid: "" };
      if (x.action === "storyboard") return { plan: "p", shots: ids.map((id, i) => ({ id, scene: N > 8 ? Number(id.slice(1, 3)) : 1, start: i * 6, end: i * 6 + 5, beat: "", performers: [], status: "ready", locked: false, approved: null, thumb_src: `t${i}.png`, thumb_source: "keyframe", preview: null, keyframe: still(i), versions: [], references: [] })), library: { items: [], assign: { project: [], scenes: {}, shots: {} } } }; if (x.action === "thumbs") return Object.fromEntries(((x.data?.srcs as string[]) ?? []).map((s, i) => [s, still(i + s.length)])); return null;
    case "list_styles": return styles.styles;
    case "direction_library":
      if (x.action === "list") return { directions, current: "hayao-miyazaki" };
      if (x.action === "match") return { matches: ["hayao-miyazaki", "isao-takahata", "hirokazu-kore-eda", "pete-docter", "agnes-varda", "satyajit-ray"].map((id, i) => ({ id, score: 1, why: i < 3 ? ["genre: drama", "mood: tender", "low energy"] : [] })), story: { energy: "low", moods: ["tender", "family"], genres: ["drama", "coming-of-age"], words: 900 } };
      return null;
    case "supervisor": return { items: [
      { id: "i1", shot: "S01-02", source: "keyframe check", severity: "major", title: "Fused hands", detail: "The held hands are fused into one mass; the fingers can't be told apart.", fix: "Redraw with the hands apart and five fingers each.", kind: "image", render: null, actions: ["fix", "regenerate", "accept", "ignore"], status: "open" },
      { id: "i2", shot: "S02-02", source: "take review", severity: "minor", title: "Soft left hand", detail: "The left hand is soft and slightly out of focus.", fix: "", kind: "video", render: null, actions: ["regenerate", "accept", "ignore"], status: "open" },
      { id: "i4", shot: "S01-02", source: "keyframe check", severity: "minor", title: "Extra finger on the left hand", detail: "A sixth finger shows on the hand holding the cup.", fix: "", kind: "image", render: null, actions: ["regenerate", "accept", "ignore"], status: "open" },
      { id: "i5", shot: "S02-03", source: "continuity", severity: "minor", title: "Jump cut", detail: "The camera barely moves between this shot and the one before.", fix: "", kind: "video", render: null, actions: ["fix", "accept", "ignore"], status: "open" },
      { id: "i3", shot: "S01-04", source: "continuity", severity: "info", title: "Jacket colour changes", detail: "The jacket is blue here and green in the shot before.", fix: "", kind: "image", render: null, actions: ["accept", "ignore"], status: "open" }],
      groups: [{ id: "g1", scene: "2", title: "Continuity: jump cut", kind: "video", action: "fix", items: ["i5", "i2"], shots: ["S02-02", "S02-03"], render: null }], summary: { open: 5, major: 1, minor: 3, info: 1, decided: 2, ready: false } };
    case "director_audit": return x.action === "audit" ? { planned: 70, directed: 76, ok: false, drops: [], uncovered: [], merges: [
      { shot: "S01-02", scene: 1, start: 13, end: 15, duration: 2, check: true, risks: ["different people are the focus of each beat", "two separate lyric or dialogue lines fall in one shot (only one can be lip-synced)"], note: "All scripted beats are preserved in order; the final match cut also carries the aftermath so the scene lands without an extra cut.",
        sources: [{ id: "S01-02", cue: ["Survival instinct"], people: ["Amara", "Sege"], description: "Wide establishing shot of the warm kitchen with Amara preparing tea. Then: close-up of Amara smiling at Sege." }, { id: "S01-03", cue: [], people: ["Sege"], description: "Over Sege's shoulder as his imaginary duplicate packs behind him." }] },
      { shot: "S01-05", scene: 1, start: 27, end: 29, duration: 2, check: false, risks: ["each of the 2 actions gets under 2 seconds"], note: "", sources: [{ id: "S01-05", cue: [], people: [], description: "Rapid push into the dark childhood corridor." }, { id: "S01-06", cue: [], people: ["Young Sege"], description: "Low medium shot of Young Sege sitting with the red toy car." }] },
      { shot: "S02-01", scene: 2, start: 31, end: 33, duration: 2, check: false, risks: [], note: "", sources: [{ id: "S02-01", cue: [], people: ["Sege"], description: "Intimate profile of their kiss." }, { id: "S02-02", cue: [], people: ["Amara"], description: "Close-up of Amara laughing gently." }] }] } : null;
    case "review_backlog": return { unchecked: 0 };
    case "lipsync_check": return { shots: 0 };
    case "acting": if (x.action === "beats_get") return { beats: [{ t0: 0, t1: 2.5, what: "Sarah holds the cup with both hands", note: "" }, { t0: 2.5, t1: 4.2, what: "She sets it down without looking at him", note: "" }], seconds: 4.2, source: "written" }; return { arc: { sections: ["verse", "chorus", "bridge"], characters: ["Sege", "Amara"], arcs: { Sege: { points: [], source: null }, Amara: { points: [], source: null } } }, business: { Sege: [], Amara: [] } };
    case "performance": return { profiles: [{ id: "natural", label: "Natural", blurb: "Truthful, everyday acting. Small motivated gestures; the default." }, { id: "restrained", label: "Restrained", blurb: "Held back, internal. Emotion shows in the eyes and breath, not the face." }, { id: "expressive", label: "Expressive", blurb: "Open and readable. Clear faces and gestures, still grounded." }, { id: "dramatic", label: "Dramatic", blurb: "Heightened, cinematic. Big emotional beats, strong poses, held moments." }, { id: "energetic", label: "Energetic", blurb: "High energy for up-tempo songs: movement, rhythm, performance to camera." }], default: "dramatic", set: true, scenes: {}, characters: {}, shots: {} };
    case "list_projects": return [
      { dir: "f1", title: "Last Train", kind: "film", state: "Story locked", modified: now },
      { dir: "f2", title: "The Lighthouse Keeper", kind: "film", state: "Story: idea", modified: now - 86400 * 2 },
      { dir: "p1", title: "Exit Plan", state: "directed", modified: now - 86400 * 9, song: "song.wav" }];
    case "hidden_count": return 0;
    case "key_status": return { openai: true, fal: true, kie: true, google: false, elevenlabs: false, midjourney: false };
    case "engine_status": return { ready: true, gpu: false, dev: true, python: "" };
    case "film_bible": return bibleView;
    case "model_registry": return x.action === "in_use" ? { models: [], warnings: [] } : x.action === "refresh" ? { results: { elevenlabs: { ok: true, models: 6 }, kie: { ok: false, error: "no network" } }, kept: "Anything that could not be refreshed keeps what it had." }
      : { models: 32, providers: { elevenlabs: { refreshed: now - 86400, stale: false, last_error: null }, kie: { refreshed: null, stale: true, last_error: null }, openrouter: { refreshed: null, stale: true, last_error: null } }, note: "" };
    case "film_outdated": return { takes: [{ shot: "S01-03", take: "v1", kind: "voice_changed", why: "The voice was replaced after this take was made, so the mouth may not match it.", speakers: ["Lila"], kept: false, options: ["lipsync_pass", "new_take"], note: "" }], cues: [], film: null, unchecked_takes: 2, clean: false };
    case "film_mix": {
      if (x.action === "preview") return { file: "cache/audio-preview/scene1.wav", seconds: 14.5, cues: 1, skipped: [], ducked: true, solo: (x.data as { solo?: string } | undefined)?.solo ?? null, voices: true };
      return { schema: 1, ducking_db: -12, duck_attack: 0.15, duck_release: 0.6, target_lufs: null, peak_db: -1, mute_lanes: [], solo: null };
    }
    case "film_audiogen": {
      if (x.action === "providers") return { providers: [{ id: "elevenlabs_sfx", label: "ElevenLabs sound effects", kind: "sfx", cost_known: true, cost_words: "about 11 credits per second you ask for", duration: [0.5, 30], loop: true, instrumental: false, has_key: true, rights: "not_established", rights_note: "Commercial rights for sound made this way were not established.", checked: "2026-10-14" },
        { id: "elevenlabs_music", label: "ElevenLabs Music", kind: "music", cost_known: false, cost_words: "ElevenLabs does not publish what a piece of music uses of your plan", duration: [3, 600], loop: false, instrumental: true, has_key: true, rights: "not_established", rights_note: "Commercial rights for sound made this way were not established.", checked: "2026-10-14" }] };
      if (x.action === "estimate") return { provider: "elevenlabs_sfx", label: "ElevenLabs sound effects", kind: "sfx", key: "k", cached: null, unit: "elevenlabs_credits", amount: 22, basis: "about 11 credits per second x 2 s (an estimate)", cost_known: true, needs_unknown_cost_accepted: false, needs_rights_ack: true, rights_note: "Commercial rights for sound made this way were not established.", has_key: true };
      if (x.action === "pending") return { tasks: [] };
      return { assets: [], blocking: [], ok: true };
    }
    case "film_cues": {
      const base = { cues: [{ id: "q-1a2b3c4d", kind: "ambience", asset_id: "a-sfx-1a2b3c4d", asset_name: "Rain on the roof", asset_file: "audio/sfx/a-sfx-1a2b3c4d.wav", asset_seconds: 42.5, scene: 1, shot: null, start: 0, duration: null, gain_db: -14, fade_in: 1, fade_out: 2,
          loop: true, ducking: "auto", approval: "approved", note: "", source: "manual", fresh: [], needs_sound: false, created: now, updated: now },
        { id: "q-5e6f7a8b", kind: "sfx", asset_id: null, asset_name: null, asset_file: null, asset_seconds: null, plan: { description: "A kettle clicking off", search: "kettle" }, scene: 1, shot: "S01-02", start: 1.2, duration: null, gain_db: 0, fade_in: 0, fade_out: 0,
          loop: false, ducking: "auto", approval: "approved", note: "", source: "quick", fresh: [], needs_sound: true, created: now, updated: now }],
        dialogue: [{ id: "voice:S01-02:lila", kind: "dialogue", derived: true, scene: 1, shot: "S01-02", speaker: "Lila", file: "voice/lila.wav", duration: 3.4, start: 0, source: "recording", text: "It looked weird." }], removed: [],
        scenes: { "1": { seconds: 14.5, shots: [{ id: "S01-01", seconds: 4, sound: "" }, { id: "S01-02", seconds: 4.5, sound: "A kettle clicks off, quietly" }] }, "2": { seconds: 7, shots: [{ id: "S02-01", seconds: 4, sound: "" }] } }, counts: { cues: 2, needs_sound: 1, suggested: 0 } };
      if (x.action === "quick" || x.action === "director_suggest") return { scene: 1, source: x.action === "quick" ? "quick" : "director", ideas: [{ kind: "ambience", what: "Rain falling", why: "The scene mentions rain.", search: "rain", shot: null, loop: true, matches: [{ asset_id: "a-sfx-1a2b3c4d", name: "Rain on the roof", score: 5, why: ["rain"], approved: true, seconds: 42.5 }] },
        { kind: "sfx", what: "Pencil on paper", why: "She draws.", search: "pencil", shot: "S01-02", loop: false, matches: [] }] };
      if (x.action === "director_estimate") return { calls: 1, usd: 0.004, local: false, note: "", sends: "this scene's shots" };
      return base;
    }
    case "film_voice_direct": {
      if (x.action === "scene_plan") return { scene: 1, speakers: [{ name: "Lila", key: "lila", voice: "Warm Northern Woman", has_voice: true, approved: false, lines: 2 }, { name: "Chloe", key: "chloe", voice: null, has_voice: false, approved: false, lines: 1 }],
        lines: [{ shot: "S01-02", speaker: "Lila", key: "lila", text: "It looked weird.", written: "It looked weird.", spoken_version: false, state: "missing", seconds: null, characters: 16, credits: 16, cached: false },
          { shot: "S01-03", speaker: "Chloe", key: "chloe", text: "I know.", written: "I know.", spoken_version: false, state: "no_voice", seconds: null }], missing: 1, no_voice: ["Chloe"], estimate: { characters: 16, credits: 16, basis: "" } };
      if (x.action === "table_read") return { scene: 1, lines: [{ shot: "S01-02", speaker: "Lila", key: "lila", text: "It looked weird.", file: null, seconds: null, source: null }], seconds: 0, silent: 1 };
      if (x.action === "performance") return { lines: [] };
      return {};
    }
    case "film_audio": {
      const a = (id: string, kind: string, name: string, category: string, seconds: number, approval: string, extra: Record<string, unknown> = {}) => ({ id, kind, name, description: "", category, file: `audio/${kind}/${id}.wav`, original_name: `${name}.wav`, sha1: id, bytes: 1000, seconds, source: "imported",
        tags: [], places: [], props: [], characters: [], scenes: [], shots: [], genre: "", mood: "", tempo: "", generation: {}, licence: { source: "", note: "", commercial: "unknown" }, approval, added: now, updated: now, exists: true, ...extra });
      const all = [a("a-sfx-1a2b3c4d", "sfx", "Rain on the roof", "weather", 42.5, "approved", { places: ["Kitchen"], tags: ["rain", "night"] }), a("a-sfx-5e6f7a8b", "sfx", "Kettle click", "foley", 1.4, "pending", { props: ["Kettle"] }),
        a("a-music-9c0d1e2f", "music", "Lila's music box", "theme", 96, "pending", { genre: "Chamber", mood: "Tender", characters: ["Lila"] })];
      return { assets: all, removed: 0, removed_items: [], categories: { sfx: [{ id: "foley", name: "Foley" }, { id: "ambience", name: "Environmental ambience" }, { id: "weather", name: "Weather" }, { id: "custom", name: "Custom" }], music: [{ id: "score", name: "Background score" }, { id: "theme", name: "Character or recurring theme" }, { id: "custom", name: "Custom" }] }, counts: { sfx: 2, music: 1 } };
    }
    case "film_make": return x.action === "progress" ? { story: { kind: "screenplay", locked: true, as_is: true }, cast: { characters: 2, places: 2, pictures: 2, style: true }, shots: { count: 6, edited: 1 }, make: { shots: 6, storyboard: 4, keyframe: 2, video: 1 } } : N > 8 ? { ...makeStatus, shots: grow(makeStatus.shots as never[]), counts: { ...(makeStatus as { counts: object }).counts, shots: N } } : makeStatus;
    case "film_check": return continuityMock;
    case "film_spending": return { lines: [
      { step: "pictures", label: "Pictures", provider: "kie", unit: "kie_credits", unit_name: "Kie credits", operations: 6, reported: 24, reported_operations: 6, estimated: 0, estimated_operations: 0 },
      { step: "video", label: "Video", provider: "kie", unit: "kie_credits", unit_name: "Kie credits", operations: 2, reported: 328, reported_operations: 2, estimated: 0, estimated_operations: 0 },
      { step: "voices", label: "Voices", provider: "elevenlabs", unit: "elevenlabs_credits", unit_name: "ElevenLabs credits", operations: 4, reported: 9, reported_operations: 3, estimated: 3, estimated_operations: 1 },
      { step: "sound_effects", label: "Sound effects", provider: "elevenlabs", unit: "elevenlabs_credits", unit_name: "ElevenLabs credits", operations: 2, reported: 33, reported_operations: 2, estimated: 0, estimated_operations: 0 }],
      totals: [{ unit: "kie_credits", unit_name: "Kie credits", operations: 8, reported: 352, estimated: 0 }, { unit: "elevenlabs_credits", unit_name: "ElevenLabs credits", operations: 6, reported: 42, estimated: 3 }],
      uncertain: [], limits: { elevenlabs_credits: 150 }, problems: [], operations: 14, note: "Amounts marked reported came from the provider's own reply; estimates are our guess from the published price. Not tracked here: the writing helper (planning with a language model)." };
    case "film_materials": return x.action === "apply" ? { applied: [{ id: "a", type: "storyboard", title: "storyboard/S01-01.png", what: "Panel for S01-01 (also the framing reference for its hero picture)" }], failed: [], skipped: [], changed_since_scan: [], message: "1 added to the film. Nothing was bought or sent anywhere." } : { token: "0123456789ab", problems: ["board.pdf: page 004 has no picture inside it (it is drawn as lines or text). Export those pages as pictures (PNG or JPG) and bring them in as files."], counts: { storyboard: 2, asset: 1, shotrow: 1, note: 1 },
      shots: [{ id: "S01-01", scene: 1, title: "Kitchen" }, { id: "S01-02", scene: 1, title: "Tea" }, { id: "S02-01", scene: 2, title: "Yard" }],
      items: [
        { id: "f1", type: "storyboard", title: "storyboard/S01-01.png", rel: "boards/storyboard/S01-01.png", on: true, blocked: "", notes: [], shot: "S01-01", shot_label: "S01-01 · Kitchen", how: "the file name" },
        { id: "f2", type: "storyboard", title: "storyboard/panel 2.png", rel: "boards/storyboard/panel 2.png", on: false, blocked: "", notes: ["This shot already has a chosen panel. Tick to use this one instead; the old one stays in the film."], shot: "S01-02", shot_label: "S01-02 · Tea", how: "their order", replaces: true },
        { id: "f3", type: "asset", title: "characters/Sarah/front.png", rel: "boards/characters/Sarah/front.png", on: true, blocked: "", notes: [], kind: "character", name: "Sarah", entry: "sarah", entry_name: "Sarah", create: false, media_kind: "front" },
        { id: "f4r1", type: "shotrow", title: "S01-01 · Kitchen", rel: "shots.csv", on: true, blocked: "", notes: [], shot: "S01-01", changes: [{ label: "Framing", old: "wide", new: "close-up" }, { label: "Movement", old: "", new: "push in" }, { label: "Length (s)", old: 3, new: 4 }] },
        { id: "f5", type: "note", title: "tone.md", rel: "notes/tone.md", on: true, blocked: "", notes: [], target: "tone", excerpt: "Warm, patient, handheld. The kitchen is always lit from the window.", length: 64 },
        { id: "f6", type: "unsorted", title: "mystery.png", rel: "boards/mystery.png", on: false, blocked: "Say what this picture is: a storyboard panel, or a picture of a character, a place or a prop.", notes: [] }] };
    case "film_voice": return voiceStatus;
    case "film_cast_voice":
      if (x.action === "library") return { voices: [{ voice_id: "AbCdEfGh1234", name: "Warm Northern Woman", category: "premade", description: "Gentle, unhurried", labels: { accent: "british", age: "old" }, preview_url: "" }, { voice_id: "ZyXwVu987654", name: "Bright Girl", category: "premade", description: "", labels: { age: "young" }, preview_url: "" }], next: null };
      if (x.action === "ledger") return { limits: { elevenlabs_credits: 500 }, count: 3, by_unit: { elevenlabs_credits: { operations: 2, estimated: 58, reported: 0, unreported_operations: 2, estimated_unreported: 58 }, voice_slot: { operations: 1, estimated: 1, reported: 0, unreported_operations: 1, estimated_unreported: 1 } },
        unresolved: [{ id: "u1", at: 1790000000, updated: 1790000000, action: "speak", person: "Lila", shot: "S01-03", status: "uncertain", estimate: { unit: "elevenlabs_credits", amount: 29, basis: "" }, actual: { unit: "elevenlabs_credits", amount: null, reported: false, source: null }, note: "" }],
        recent: [{ id: "u1", at: 1790000000, updated: 1790000000, action: "speak", person: "Lila", shot: "S01-03", status: "uncertain", estimate: { unit: "elevenlabs_credits", amount: 29, basis: "" }, actual: { unit: "elevenlabs_credits", amount: null, reported: false, source: null }, note: "" }] };
      if (x.action === "estimate") return { rows: [{ shot: "S01-03", speaker: "Lila", ok: true, characters: 52, credits: 52, cached: false, text: "[tired] Yesterday? It looked like... spiced beans?" }], characters: 52, credits: 52, basis: "" };
      if (x.action === "takes") return { person: "Lila", shot: "S01-03", takes: [
        { file: "voice/_generated/S01-03-b.mp3", text: "[tired] Yesterday? It looked like... spiced beans?", model: "eleven_v4", voice_name: "Warm Northern Woman", at: 1790000200, current: true },
        { file: "voice/_generated/S01-03-a.mp3", text: "Yesterday? It looked like... spiced beans?", model: "eleven_v4", voice_name: "Warm Northern Woman", at: 1790000100, current: false }] };
      return { key: true, models: [{ id: "eleven_v4", label: "Eleven v4 (most expressive: put [laughs], [whispers], [sad]... in the words)" }, { id: "eleven_v4_turbo", label: "Eleven v4 Turbo (expressive, half the credits)" }, { id: "eleven_v3", label: "Eleven v3 (expressive, less steady than v4)" }, { id: "eleven_multilingual_v2", label: "Multilingual v2 (steady, best for long lines; no tags)" }, { id: "eleven_flash_v2_5", label: "Flash v2.5 (fast, half the credits; no tags)" }],
        people: { lila: { name: "Lila", voice_id: "AbCdEfGh1234", voice_name: "Warm Northern Woman", model: "eleven_v4", stability: 0.5, similarity: 0.75, style: 0, speed: 1, made: "library" } },
        plan: { tier: "starter", used: 1200, limit: 30000, left: 28800, can_clone: true, slots_used: 3, slots: 10 }, plan_error: "" };
    case "film_shots": return x.action === "shot" ? { shot: { ...shotContract, plan: blockingPlanMock, ...(/click=Blocking/.test(location.search) ? { locks: { storyboard: false, keyframe: false } } : {}) } } : x.action === "suggest" ? shotSuggestion : x.action === "blocking" ? blockingMock : x.action === "principles" ? { look: "stop-motion", family: "craft", screen_craft: false, picture: [], video: [{ id: "anticipation", name: "Anticipation", plain: "A small opposite move prepares the big one." }, { id: "follow-through", name: "Follow-through and overlapping action", plain: "Loose parts keep going a beat longer." }, { id: "staging", name: "Staging", plain: "One idea reads at once." }, { id: "slow-in-out", name: "Slow in and slow out", plain: "Movements ease in and out." }] } : N > 8 ? { ...shotsView, shots: grow(shotsView.shots as never[]), scenes: Array.from({ length: Math.ceil(N / 8) }, (_, k) => ({ number: k + 1, shots: 8, seconds: 40 })), seconds: N * 5 } : shotsView;
    case "film":
      if (x.action === "read_file") return { name: "last-train.fountain", text: filmText, truncated: false };
      if (x.action === "preview") return { kind: "screenplay", words: 61, scenes: 3, characters: 2, locations: 3, seconds: 144, has_headings: true };
      return filmStatus;
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
      { provider: "kie", model: "wan/3-0-video", label: "Wan 3.0", price_usd: 0.45, cheaper: true, saves_usd: 0.45, strength: "Low price. FilmCrafter's Balanced video choice.", warning: "" }] };
    case "routing":
      if (x.action === "pick") return (x.data as { kind?: string } | undefined)?.kind === "video" ? { provider: "kie", model: "wan/3-0-video", label: "Wan 3.0", free: false, mode: "balanced", verified: true, price_usd: 0.45 } : { provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", free: false, mode: "balanced", verified: true, price_usd: 0.03 };
      if (x.action === "models") return { video: [row("Seedance 2", "kie", "bytedance/seedance-2", 0.9, true, { strength: "Takes a start and an end picture, can also use reference pictures, video and sound, and can speak lines.", consider: "For shots that must land on an end frame and shots with sung or spoken lines.", watch: "Costs more per shot." }), row("Wan 3.0", "kie", "wan/3-0-video", 0.45, true, { strength: "Low price. FilmCrafter's Balanced video choice.", consider: "For a whole video on a budget.", watch: "" }), row("Kling", "kie", "kling-2.6/image-to-video", 0.7, true), row("Hailuo 2.3", "fal", "fal-ai/minimax/hailuo-2.3/standard/image-to-video", 0.5, false)],
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
  home: () => <Home onNewFilm={noop} onOpen={noop} onChooseProject={noop} onSettings={noop} onHelp={noop} />,
  newfilm: () => <NewFilm onClose={noop} onCreated={noop} />,
  newfilmwrite: () => <NewFilm file="last-train.fountain" onClose={noop} onCreated={noop} />,
  studio: () => <Studio project={{ dir: DIR, ...(renderFixture as object), directed: null, jobs: [], keyframes: {}, concepts: null, treatment: null, song_path: DIR + "/soundtrack.wav", doc: null } as never} onHome={noop} onSettings={noop} onReload={noop} />,
  studiovoice: () => <Studio project={{ dir: DIR + "/render", ...(renderFixture as object), directed: null, jobs: [], keyframes: {}, concepts: null, treatment: null, song_path: DIR + "/soundtrack.wav", doc: null } as never} onHome={noop} onSettings={noop} onReload={noop} />,
  make: () => <div style={{ width: "min(1240px, 100vw)", height: 760, display: "flex", background: "#090b0f" }}><MakeFilm dir="f1" tab="keyframe" onTab={noop} /></div>,
  export: () => <div style={{ width: "min(1240px, 100vw)", height: 760, display: "flex", background: "#090b0f" }}><MakeFilm dir="f1" tab="deliver" onTab={noop} /></div>,
  continuity: () => <div style={{ width: 1100, height: 640, display: "flex", background: "#090b0f" }}><FilmContinuity dir="f1" onGo={noop} onChanged={noop} /></div>,
  assist: () => <AssistSheet dir="f1" kind="character" id="c_sarah" name="Sarah" bible={bibleView as never} onClose={noop} onApplied={noop}
    proposal={{ role: "Lead: the one who waits", age: "28", physical: "Tall, grey eyes, dark hair tied back, a ring she never takes off", relationships: "John's partner; her mother's only daughter", arc: "From waiting for a call to deciding to leave", voice: "Low, careful, says less than she means", notes: "Keeps her hands busy when she is hiding something" }} />,
  shotsuggest: () => <ShotSuggestionSheet shot="S01-02" current={shotContract as never} onClose={noop} onUse={noop}
    proposal={{ emotional_intention: "A held-back dread that neither of them names", beats: [{ character: "Sarah", what: "Holds the cup with both hands", want: "To be asked", hiding: "That she has packed", start: "calm", turn: "he does not look up", end: "still" }], micro_animation: "Steam rises; she blinks slowly",
      camera: { framing: "over the shoulder", angle: "low", lens: "portrait (50mm)", movement: "locked off", focus: "shallow", why: "Low and close keeps us with Sarah's silence." }, lighting: { description: "Low window light from the left", why: "Morning light is soft and slow." } }} />,
  shotvoice: () => <div style={{ width: "min(1240px, 100vw)", height: 780, display: "flex", background: "#090b0f" }}><ShotLab dir="f1" /></div>,
  shots: () => <div style={{ width: "min(1240px, 100vw)", height: 780, display: "flex", background: "#090b0f" }}><ShotLab dir="f1" /></div>,
  cast: () => <div style={{ width: "min(1200px, 100vw)", height: Number(q.get("h")) || 760, display: "flex", background: "#090b0f" }}><CastWorld dir="f1" /></div>,
  film: () => <FilmView dir="f1" onHome={noop} onSettings={noop} />,
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
  selectreview: () => <SelectReview dir={DIR} shots={ids.map((id, i) => ({ id, scene: N > 8 ? Number(id.slice(1, 3)) : 1, start: i * 6, end: i * 6 + 5, framing: ["Close-up", "Wide", "Medium", "Over the shoulder"][i % 4], beat: "", performers: [], status: "ready", locked: false, approved: null, thumb_src: null, thumb_source: "keyframe", preview: null, keyframe: still(i), versions: [], references: [] })) as never} sections={[{ label: "verse", group: "Verse 1", start: 0, end: 24 }, { label: "chorus", group: "Chorus", start: 24, end: 48 }] as never} initial={ids.slice(0, 4)} onClose={noop} onQueued={noop} />,
  compare: () => <div className="sheet glass viewer-sheet" style={{ width: 920 }}><div className="vs-head"><h2 className="num">Shot S01-03</h2></div><CompareLazy /></div>,
  directionlibrary: () => <DirectionLibrarySheet dir={DIR} onClose={noop} onApplied={noop} />,
  directions: () => <div style={{ maxWidth: 1180, margin: "0 auto", padding: 24 }}><CreativeDirections project={project} onPlanned={noop} onSettings={noop} /></div>,
  looks: () => <LookPicker value={{ style: "auto" }} director={false} onCancel={noop} onSave={noop} />,
  lighting: () => <LightingSheet dir={DIR} onClose={noop} />,
  cleanup: () => <CleanupSheet dir={DIR} onClose={noop} onChanged={noop} />,
  modelpicker: () => card(<><h2>Choose your video model</h2><p className="sub">Recommended models first, everything else behind All models.</p><div style={{ width: 360 }}><ModelPicker catalog={pickerCatalog} value="bytedance/seedance-2" label="Model" onChange={noop} onRefresh={noop} /></div></>),
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
  const full = scene === "home" || scene === "film" || scene === "studio";                               // whole-window screens are photographed at a desktop window size
  document.title = full ? "1440,900" : `${w},${h}`;
}, 2600);
