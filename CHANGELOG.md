# Changelog

## 0.10.0 (2026-10-10)

- **Blocking diagrams.** A new **Blocking** tab on each shot: a top-down floor plan with people (and the way they face), the camera and its cone of view, props, the line between the first two people, and ghost markers for the other shots' cameras. Drag anything; **Suggest a layout** places people and camera from who is in the shot, its framing and the shot before; **Same floor as the shot before** carries the people over.
- **The 180-degree line.** If a shot's camera is on the other side of the line from the shot before, the line turns red with a note, and the Continuity check lists it (advice only).
- **The plan reaches the prompts.** It is turned into words as the camera sees it ("John screen-right, facing screen-left. Camera over Sarah's shoulder.") and added to the shot's continuity notes in the render project, so pictures and video are made with people where you put them. A locked storyboard fixes the plan.
- Tests: the plan's cleaning, suggestions for each framing, the words, the line, saving and clearing, locking, the render project, the check, the screen's arithmetic and its markup.

## 0.9.0 (2026-10-10)

- **The in-app guide (F1) is now the FilmCrafter guide.** It was still PULSEFRAME's 1,000-line music-video guide, and it could not show the film screenshots. The new guide covers before you start, the steps, the look and the animation principles, the Studio, the Supervisor, every keyboard shortcut and what to do when something goes wrong. The old guide is kept in `docs/legacy`.
- **Music-first screens removed.** The setup wizard, the listening screen, the production planner, shows and Producer-package import are gone, with the shell commands only they used (12 of 106) and the Producer planner engine module. A music project that was never finished now says it belongs in PULSEFRAME; a finished one still opens in the Studio.
- **Each shot shows the animation principles it will carry** (or, for a photorealistic film, its screen craft), on the Acting tab, from what happens in the shot and the film's look.
- **A new film starts with natural acting and automatic lip-sync**, so small real motion is in the prompt from the first render (these were only set for old music projects).
- **Hand-off check.** `scripts/make_handoff_sample.py` makes a small hand-off folder with real clips to try in Resolve, Premiere or Final Cut; `scripts/resolve_check.py` imports one into a running DaVinci Resolve Studio and compares it with the manifest.
- `STATUS.md` rewritten to say what is verified and what is not.
- Quieter: only the most restrained acting profile leaves out exaggeration (Natural no longer does).

## 0.8.0 (2026-10-10)

- **Looks: about 100 of them, in six kinds of film.** Photorealistic, 3D animation, 2D animation, Hybrid 2D/3D, Hands-on crafts, and Art movements & experimental, each with looks from the style library (Hyperrealism, Film noir, Painterly 3D, Clay-look 3D, Watercolour storybook, Shonen action anime, Felt and wool stop-motion, Ukiyo-e, Art Deco and many more). Pick the kind, then the look; every look explains itself.
- **Genre feel, layered on any look.** Epic fantasy, dark fantasy, solarpunk, gothic horror, magical realism, biblical epic and more are added on top of the look, never in place of it.
- **A chosen look is injected strongly.** It leads every picture and every video prompt by name, is kept in the full wording, closes with a style lock that is the last thing dropped from a long prompt, and carries its own "never look like" list. Photorealistic looks are exempt from the rewording that stops drawn looks drifting to photographs.
- **The twelve principles of animation.** In Rules & style; for each shot the few that fit what happens (anticipation before a jump, follow-through on a coat) are added to the prompt, never all twelve. Different sets for drawn, 3D, crafts and photorealistic (screen craft). A quiet acting profile leaves out exaggeration.
- **A filmmaker's approach works in any look.** Applying a direction (for example Ryan Coogler) to a stop-motion film keeps stop motion and adds the filmmaker's camera, light, movement and pace to every shot's prompt as traits, never a name.
- **Hands, bodies and faces are checked in the film's Pictures step.** *Check hands & faces* (price first), a flag on the card, and a question before locking a flagged picture or making a video from one.
- **Home drop card:** taller and sleeker, with four rolling film strips with sprocket holes, a vignette, crop marks, a slow scan line and a breathing call to action; still with reduced motion.
- **Film language in the Studio:** Acting arcs say film and scenes, the playback error says soundtrack, lip-sync says speaking shots. The Studio top bar no longer runs under the inspector.
- **Sturdier:** a progress reply with a part missing no longer blanks the film screen. New `PF_QA=1 node scripts/docshots-edge.mjs` opens every harness screen in headless Edge and reports any console error or exception.
- The Shots screen uses the same premium panel language as Cast & World.

## 0.7.0 (2026-10-10)

- **Direction library: great filmmakers.** The music-video traditions are replaced by 48 filmmakers from North America, Latin America, Europe, Asia, Africa, the Middle East and Oceania (Brad Bird, Hayao Miyazaki, Ryan Coogler, Agnes Varda, Bong Joon-ho, Ousmane Sembene, Asghar Farhadi, Taika Waititi and more). Each is a visual brief (camera, light, palette, editing, movement, design, a suggested look and acting profile) with what they are known for and a respect note: an approach to learn from, never a copy.
- **Matching follows your story**, not a song's tempo: mood, genre and energy are found in your script ("Fits your story", "Best for your story").
- **Production Supervisor, shot by shot.** Findings are grouped by shot with a large picture, a strip of the shots that need you (coloured by severity), clickable Major / Minor / Notes / Decided tiles, batch fixes with a stack of thumbnails, and Director changes below. Click a picture to review the shot.
- **Simpler shot inspector.** Compose (prompt, references, start and end frames) and Media (your own files) now sit behind an **Advanced** button; the tabs you use every day (Shot, Keyframe, Video) are what you see. It remembers your choice.
- **A calmer, more premium look.** Cast & World gets an underline tab bar, portrait tiles with a gold marker, one raised editor panel and quieter fields. The Make wall has squarer cards, bigger screens, a yellow **Make** button, a sticky bar with "n of N done", and a taller film strip. **Export** is three numbered panels with a readiness line (no strip).

## 0.6.0 (2026-10-10)

- **One Studio instead of three steps.** The steps are now **Story, Cast & World, Shots, Studio, Export**. Making the film (pictures, video, review) is one place seen two ways, **Cards | Timeline**; the separate Storyboard, Make film and Review steps are gone.
- **Panels are optional.** The cards have **Pictures** (first), **Video**, and **Panels (optional)**. A picture no longer needs a storyboard panel first; a video still needs its picture.
- **Export is its own step** (soundtrack, export, hand-off to an editor).
- The studio's top bar has **Cards | Timeline** and **‹ Film**; the separate amber Storyboard button is gone.

## 0.5.1 (2026-10-10)

- **Fixed: the Storyboard button in the studio went Home.** The path pattern that finds a film from its render folder only understood forward slashes, and Windows paths use backslashes. It is now one tested helper for both (`filmPaths.ts`), also used when a `.filmcrafter` document is opened.
- **Optional writing help, more of it.** **Write it for me** on the story ladder drafts the next step (idea to synopsis to treatment to outline to screenplay); it opens in the new-version sheet for you to read and edit before it is saved as a new version. **Help me write this shot** (Acting and Camera tabs) suggests feeling, acting beats, small motion, camera and light with reasons; you choose which parts to use. Both show what they send and the price first.
- **Studio in film language:** the rail says Looks, the inspector says Dialogue, and "Direct my video" is gone from the command list on a film.
- Tests: the next step of a story, the shot suggestion (only real camera words kept), film paths.

## 0.5.0 (2026-10-10)

- **One world, one layout.** Cast & World, Rules & style and Make film share one centred frame; Rules & style is two columns that use the width; textareas are a sensible height.
- **You always know where you are and what is next.** Each step along the top shows how far it is (locked, 11 · 7, 12/48 …) and turns green when done; **Back / Next** and a one-line hint run along the bottom of every step.
- **Optional writing help in Cast & World.** **Help me write** on a character, place or prop, and **Help me write this** for the world and visual style. It shows what it will send and the price (free on a local model), asks for a yes, then shows a suggestion next to what you have: tick what you want, edit the words, and what you already wrote is marked yours and kept unless you choose the suggestion. It never changes anything by itself.
- **Studio:** the **Storyboard** button is amber with an icon and takes you straight to the storyboard wall (it opened Cast & World before).
- Tests: the writing helper (9), progress for the badges (3), and Back/Next/badge logic.

## 0.4.2 (2026-10-10)

- **Fixed: a PDF screenplay was read one word to a line.** The real cause was the PDF reader, not the screen. PDFs are now read by printed line (the layout reader), the dash that came out as a replacement mark is repaired, and a title page is no longer taken for a scene or a speaking character. A film that was read badly shows a notice with **Read the file again**, which makes a new version and leaves the old one untouched.
- **Fixed: no way back to the storyboard from the timeline view.** The studio's top bar now has **Cards | Timeline** and a **Storyboard** button at the top left, on every window size, and Storyboard takes you straight to the storyboard wall.
- Tests: title pages, one-word-per-line detection, PDF tidying, reading the original again.

## 0.4.1 (2026-10-10)

- **Fixed: PULSEFRAME's splash screen sometimes showed on launch.** FilmCrafter had inherited its two opening designs (one of them the music app's "steps" picture, on every other launch). There is now one opening: FilmCrafter's own artwork, with a film strip rolling past and a slow sweep of light. A test keeps the music app's pictures out.
- **Fixed: an imported screenplay showed one word per line.** The script column shrank to the width of a word (an auto margin on a flex child). It is centred by padding now, and a test guards it.
- **New: a living film strip on the Home screen.** Two rows of frames roll past behind the drop card; drag a screenplay over it and they speed up and glow. Still with reduced motion.

## 0.4.0 (2026-10-10)

- **Cards | Timeline** on the same film: the story-first cards, or the full studio timeline, one click apart.
- **Film strip** in Make film: shots as blocks along time; drag an edge to change a shot's length, drag a block to reorder.
- The studio on a film no longer shows "Who sings" or the dance direction; lip-sync reads "speaking shots follow the voice".
- Hand-off checked with the real OpenTimelineIO library (OTIO and CMX 3600 EDL parse, same cut).

## 0.3.0 (2026-10-10)

- **Studio tools.** The full PULSEFRAME studio opens on a film from the film workspace: the timeline (scenes as sections, cuts as the grid, dialogue as a lane of words, the soundtrack as the waveform, shots as cards, layers on their own lanes), Supervisor, Review, Acting, Continuity, Lighting, Colour match, Clean up, Layers, Library and Export. Home returns to the film.
- Song-first parts are hidden on a film (Autopilot, Direct My Video, the song guide, tempo); labels say Timeline, Soundtrack and Scenes.
- `scripts/live_test.py`: one real picture through a real provider, price first, nothing without `--yes`.

## 0.2.0 (2026-10-10)

The first version that takes a film from a screenplay to an exported file.

- **Story:** a screenplay (or an idea, synopsis, treatment or outline) is kept exactly as given; scenes, speaking characters and places are read from it; versions; Story Lock; suggestions that never edit the script.
- **Production Bible, Cast and World:** characters, places and props with related states, wardrobe, your own pictures, place layouts, rules and a visual style; filled from the story, then yours; every change is kept in a history.
- **Shots:** the story broken down into a draft of shots, each a Shot Contract (purpose, people and states, place, action, dialogue, acting beats, camera, light, continuity); suggestions with reasons; split, join, duplicate, move, take out.
- **Making the film:** storyboard panels, hero keyframes and video through the proven render engine, with choose and lock at each stage, your own pictures and video, a soundtrack, and export. Every generation shows its price and waits for a yes.
- **Continuity Director:** advisory findings ("may have changed") with reasons; your decisions are kept.
- **Hand-off:** EDL, OpenTimelineIO, Final Cut Pro XML, shot manifest, subtitles, copied takes and soundtrack.
- **Simple and Pro** modes on the same film; **Director Command** (Ctrl+K) for plain phrases about a shot.
- New app icon from the FilmCrafter mark.
- Tests: 90 new engine tests including a whole film from screenplay to export with no provider and no spend.

## 0.1.0 (unreleased)

- **Story-first Home and creation flow.** Home is about stories: drop a screenplay, press New film, or start from an idea. New film asks how your story begins (screenplay, idea or logline, synopsis, treatment, scene outline), takes pasted text or a file (Fountain, text, Markdown, PDF, Word), shows what was found, and keeps the story exactly as given (the chosen file is copied untouched into the film). A film opens in the story workspace: scenes, the script as written, versions, Story Lock, suggestions that never edit the script, characters and places. New engine module `story.py` (film.json, script versions, analysis, lock history), a `film` shell command, a film kind in Recent.
- Removed: the music-first Home (Create from song, Make a song, New show, Producer package), the animated drop wave.
- Tests: `test_story.py` (16 engine tests), `story.test.tsx`.

- Seeded from PULSEFRAME 1.36.0 (see docs/architecture/BASELINE.md). Identifiers renamed (product, bundle id, engine package, key service). Music-specific modules are still present and are removed in Phase 0 steps listed in docs/architecture/PHASE0_PLAN.md.
