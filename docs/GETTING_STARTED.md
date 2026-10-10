# FilmCrafter guide

FilmCrafter turns a story into a film. You bring a screenplay, a logline or an idea; FilmCrafter breaks it into shots, helps you set the cast, the places and the look, makes the pictures and the video with the AI models you choose, checks them, and exports the finished film or hands it to an editor. **Your story is kept exactly as you gave it, every generation shows its price first and waits for your yes, and chosen and locked work is never replaced.**

## Before you start

- **Install** with the `.exe` or `.msi` installer. The first launch sets up the engine (a few minutes, once).
- **Keys.** Open **Settings** (the gear, or Ctrl+,) and paste the keys for the services you want to use: a picture and video provider (fal or Kie), and optionally an AI brain for the optional writing help and for checking pictures (OpenAI or OpenRouter), or a local one (Ollama, LM Studio, ComfyUI). Keys are stored in the system keychain, never in a film's folder.
- **Without any key** you can still write and structure a whole film (story, cast, shots), bring your own pictures and videos, edit the timeline and export, all free.
- **Money.** Pictures and video are billed by the provider. FilmCrafter shows the price of every generation before it starts, and the Plan & budget sheet (Settings) sets a limit.
- **Where films live.** Each film is a folder in `Documents\FilmCrafter` that you can open, copy and back up like any other. In the Studio, *File > Save As…* makes another copy.

## The steps of a film

Along the top: **Story, Cast & World, Shots, Studio, Export**. Each shows how far it is and turns green when done; **Back / Next** and a one-line hint run along the bottom. **Simple** mode goes straight from the cast to the studio; **Pro** adds the Shots workspace.

## Home

![Home: drop a screenplay, start a new film, or start from an idea. Behind the card a gold car is chased around a night road while camera rigs follow it](img/film/home.png)

- **Drop a screenplay** on the window (Fountain, text, Markdown, PDF or Word), press **New film**, or press **Start from an idea**.
- **Open project** opens a film or an older project. Older music-video projects and shows still open from **Recent**.

## New film

![New film: how does your story begin?](img/film/newfilm.png)

Say how your story begins: a screenplay, an idea or logline, a synopsis, a treatment, or a scene outline. Then bring it: paste it, or choose a file.

![New film: the story, with what was found in it](img/film/newfilm-story.png)

Under the story you see what was found (scenes, speaking characters, places, rough length). **The story is saved exactly as given**, and the file you chose is kept untouched in the film's folder.

## The story workspace

![The story: scenes on the left, the script in the middle, what was noticed on the right](img/film/film.png)

- **Scenes** (left): click one to jump to it in the script.
- **The script** (middle): shown as written. Pick any **version** at the top.
- **The story** (right): *Use story as it is* sets every suggestion aside and leaves the script alone. *Lock this version* fixes the story the rest of the film will be made from.
- **What I noticed**: suggestions about structure, pacing, visual storytelling and how hard the film will be to make. They are advice only. *I'll deal with it* and *Dismiss* just keep track; **nothing ever edits your script**.
- **Versions**: a change to the story is always a **new version**; earlier versions and a locked version are never changed. To move on after a lock, write a new version and lock that one.

If your story is not a screenplay yet (an idea, a synopsis, a treatment or an outline), the story panel shows where it is on the way to one (logline, synopsis, treatment, beats, outline, screenplay). Write or paste the next step as a new version; when the screenplay is written, lock it.

## Cast & World: the Production Bible

Open **Cast & World** along the top. The first time, FilmCrafter fills it from your story (the speaking characters and the places); **Add from the story** brings in anything new later and never changes what you wrote.

![Characters: pictures, traits, wardrobe, and related states](img/film/cast.png)

- **Characters, Places, Props**: each is one entry with **states** (Sarah at 8, at 28, at 70; the kitchen by day and by night). Bring your own artwork (the first picture is the master); it is copied into the film and the original is left alone. Places have a layout (doors, windows, landmarks, where actors can stand and the camera can go) so a set doesn't change between shots.
- **Rules & style**: the visual style, the rules of the world, and how the film is made (cinematography, lighting, movement, sound).

![Rules and style: six kinds of film, a look within one, an optional genre feel, and the twelve principles of animation](img/film/bible.png)

### Choosing the look

1. **Pick the kind of film**: *Photorealistic*, *3D animation*, *2D animation*, *Hybrid 2D/3D*, *Hands-on crafts* (stop motion, clay, felt, paper), or *Art movements & experimental*.
2. **Pick the look** inside it, about 100 in all (Hyperrealism, Documentary realism, Film noir, Painterly 3D, Clay-look 3D, Watercolour storybook, Shonen action anime, Felt and wool stop-motion, Ukiyo-e, Art Deco and more). Hover for what each one is.
3. **Optionally add a genre feel** on top of any look: epic fantasy, dark fantasy, solarpunk, gothic horror, magical realism, biblical epic and others. It is layered on the look, never in place of it.

The look is **written into every picture and video prompt**, with its name first (models weigh the first words most), a fuller description, a *style lock* sentence that is the last thing dropped if a prompt gets long, and a list of what it must never look like. For a drawn, 3D or crafted look, words elsewhere in the prompt that ask for a photograph are reworded so they cannot pull the picture back to photorealism; photorealistic looks are left alone.

### Animation principles

The twelve principles of animation (squash and stretch, anticipation, staging, pose to pose, follow-through, slow in and out, arcs, secondary action, timing, exaggeration, solid drawing, appeal) are in **Rules & style**. For each shot, the few that fit what happens in it are added to its prompt (a jump gets anticipation and squash and stretch; a coat in the wind gets follow-through), never all twelve. Drawn and 3D looks use most of them, crafts fewer, and photorealistic films keep only the ones that are also good acting and camera craft. Switch any on or off, or press *Use the style's own choice*. A quiet acting profile (Restrained, Natural) leaves exaggeration out unless you chose it.

### A filmmaker's approach, in any look

The **Direction library** (Studio, *Directions*, or from the film) has 48 filmmakers from North America, Latin America, Europe, Asia, Africa, the Middle East and Oceania. Each is a visual approach turned into traits: camera, light, colour, editing, movement, design, a suggested look and an acting profile. They are not copies of any film, and the traits (never the filmmaker's name) are sent to the models. **A direction works with any look**: apply Ryan Coogler's approach to a stop-motion film and the look stays stop motion while every shot gets his long moving takes, warm natural light on skin and groups moving together. Matching follows your story (genre, mood, energy), not a tempo.

![The Direction library: filmmakers by region, matched to your story](img/film/directionlib.png)

Taking an entry out never destroys it: the Bible before each change is kept (the newest 30).

## Shots

Open **Shots** along the top and press **Break down the story**. FilmCrafter drafts the shots for every scene, like a director's first pass: a wide to open the scene, coverage for each exchange of dialogue, an insert for a detail that matters. It is a starting point: change anything.

![The shots of each scene, and one shot's contract](img/film/shots.png)

Each shot is a **Shot Contract** that doesn't depend on any AI model:

- **Story**: what the shot is for, what happens, the dialogue, who is in it (linked to the Cast), where, how long.
- **Acting**: what the audience should feel, then beats: what each person wants, needs, fears and hides, and how it shows; small living motion that comes from the feeling, never random idling.
- **Camera**: framing, angle, lens, movement, focus, where the camera is, and why. **Suggest from the feeling** proposes camera and light with a reason, and applies nothing until you press **Use this**.
- **Light** and **Continuity**: the light and why, blocking, how the shot begins and ends, what must stay the same, sound.

![Camera: choices come with a reason](img/film/shots-camera.png)

![The Acting tab: the feeling and acting beats, and the animation principles this shot will carry](img/film/shots-acting.png)

Move, duplicate, split, join and take out shots freely (a shot you take out is moved aside, not deleted). Running the breakdown again only drafts scenes that have no shots; shots you have edited are never changed. A shot whose storyboard is locked can't have its framing, people or place changed until you unlock it.

## The Studio: one place to make the film

Along the top of a film there are five steps: **Story, Cast & World, Shots, Studio, Export**. The **Studio** is where pictures and video are made, and you can see it two ways with the **Cards | Timeline** switch at the top right (or press **‹ Film** in the timeline to go back to the story, cast and shots):

- **Cards**: a wall of cards, one per shot, with the film strip along the top.
- **Timeline**: the full editing studio (scenes, cuts, dialogue lane, soundtrack waveform, layers, Supervisor, Review, Lighting, Colour match, Clean up).

![The cards: pictures to choose from and lock, the film strip across the top, the yellow Make buttons, Check hands & faces in the bar and a flag on a card whose picture has wrong hands or a face](img/film/make.png)

On the cards, three tabs follow the work:

1. **Pictures.** Make a few pictures of each shot, choose one and **lock** it; it is where the video starts. Or use your own picture. A picture needs nothing before it. **Check hands & faces** looks once at each chosen picture for wrong hands, bodies and faces (about two cents each, price shown first); problems appear on the card, and locking a flagged picture or making a video from one asks you first.
2. **Video.** Each shot is brought to life from its locked picture (or bring your own video). Compare takes and **approve** the one to use. A shot's video is available once its picture is chosen.
3. **Panels (optional).** A cheaper first pass: a quick picture of each shot's composition. Choose one and lock it, and the picture is then made from it. Skip it if you like.

### Production Supervisor

![The Production Supervisor: findings shot by shot, with a picture and a strip of the shots that need you](img/film/supervisor.png)

Every quality finding in one place, **shot by shot**, each with its picture. The strip along the top shows only the shots that need you, coloured by severity (red major, gold minor, blue notes). The tiles count Major, Minor, Notes and Decided and filter the list. Click a picture to review the shot. *Fix* re-renders with the correction and *Regenerate* re-renders as planned, both showing the price first; batch fixes (such as a run of jump cuts in a scene) show a stack of the shots they cover. Director changes are listed below.

In the **Timeline**, the inspector keeps the everyday tabs (Shot, Keyframe, Video) in view; **Compose** (prompt, references, start and end frames) and **Media** (your own files) sit behind **Advanced**.

![The Studio's shot inspector: Shot, Keyframe and Video are in view; Compose and Media wait behind Advanced](img/film/studio-shot.png)

![With Advanced open: Compose (prompt, references, start and end frames) and Media appear, and the button now says Fewer](img/film/studio-advanced.png)

**Export** is the last step: choose a soundtrack (music, a dialogue mix, an ADR track you made elsewhere; it is copied in untouched) or keep silence, then export the film or write a hand-off folder for an editor.

![Export: a readiness line, then three numbered panels: soundtrack, export the film, hand off to an editor](img/film/export.png)

**Money.** Every generation shows the provider's price first and waits for your yes. Nothing is made until you press **Make**. Chosen and locked work is never replaced by a new generation. Pictures and video go through the same render engine PULSEFRAME uses: your provider keys, budgets, queues and retries all apply, and a render that was running when you closed the app picks up where it left off.

Under the hood the film builds a render project (in the film's `render` folder) from the Shot Contracts and the Bible, so the pictures and clips are made with the characters, places, style, camera, light and acting you set.

### Blocking: a top-down plan of each shot

![The Blocking tab: where people stand and face, where the camera is and what it sees, and the line between the first two people](img/film/shots-blocking.png)

Open a shot in **Shots** and choose **Blocking**. It is a floor plan seen from the ceiling: each person is a dot with an arrow for the way they face, the camera is gold with a cone for what its lens takes in, and the dashed line runs between the first two people. Small grey circles are the cameras of the other shots in the scene.

- **Suggest a layout** places the people and the camera from who is in the shot, its framing (a wide from the near wall, an over-the-shoulder behind one person looking at the other, a close-up on whoever speaks) and the shot before it. It is a free first draft; drag anything to change it. **Same floor as the shot before** keeps the people where they were.
- **Drag** a person, the camera, a prop or the small round handles to turn a person or aim the camera. The slider sets how wide the lens sees. Double-click a person's handle to turn them around.
- **The 180-degree line.** Keep the camera on one side of the dashed line between two people, or they appear to swap sides on screen between shots. If a shot's camera is on the other side from the shot before, the line turns red, a note appears, and the Continuity check lists it too. It is advice: crossing the line is sometimes right.
- **What it does for the film.** The plan is turned into words as the camera sees it ("John screen-right, facing screen-left. Camera over Sarah's shoulder") and added to that shot's prompts, so pictures and video are made with the people where you put them. If the storyboard is locked the plan is fixed too.

## Continuity check

In **Shots**, press **Continuity check**. FilmCrafter reads the shots in order and says where something **may** have changed: a person's outfit or state, the place or time of day inside one scene, a prop that appears and then vanishes, how a shot begins compared with how the last one ended, which shoulder the camera looks over, and people who have no pictures (so their face could drift).

![The Continuity check: findings in order of how likely they are, each with a reason and what to do, including the camera crossing the line](img/film/continuity.png)

Every finding says why. **It's meant** sets one aside; **I'll fix it** keeps track; **Use that** applies a plain suggestion (such as how a shot begins). It never blocks anything and never changes the film on its own.

## Writing help in Cast & World (optional)

On a character, place or prop press **Help me write**; on **Rules & style** press **Help me write this**. FilmCrafter shows what it will send (your story and what the Bible already says) and the price (free if you use a local model), and waits for your yes. The suggestion appears next to what you have: tick what you want, change any words, and press **Use**. Whatever you already wrote is marked **yours** and is kept unless you tick the suggestion. It never changes anything on its own, and you can ignore it completely.

![A suggestion for a character: each part is shown beside what you have now, and you tick what to use](img/film/assist.png)

![A suggestion for a shot: the feeling and acting, the camera and the light, each with its reason, and you choose which parts to use](img/film/shot-suggestions.png)

On the story ladder (when your story is not yet a screenplay), **Write it for me** drafts the next step: it opens for you to read and edit, and is saved as a new version only when you press Save. In **Shots**, the Acting and Camera tabs have **Help me write this shot**: it suggests the feeling, acting beats, small motion, camera and light, each with a reason; tick the parts you want.

## Finding your way

Each step along the top shows how far it is and turns green when done (the story is locked, there are people and a style, every shot has a storyboard panel…). **Back** and **Next** along the bottom take you through the steps in order, with one line on what to do here.

## Cards or timeline: the same film two ways

Along the top of a film, **Cards | Timeline** switches how you see the same shots:

- **Cards** is the story-first workspace: story, cast, shots, storyboard, keyframes, video. A **film strip** runs across the top of Make film: drag a block's right edge to make a shot shorter or longer, drag a block to move it. The cards, the shot list and the studio all follow.
- **Timeline** is the full editing studio (below). Pick whichever fits the moment; nothing is lost by switching.

## Studio tools: the full editing studio on your film

The film workspace is the story-first front door. For everything PULSEFRAME's studio does well, press **Studio tools** at the top of the film. It opens the full studio on your film:

![The studio on a film: scenes along the top of the timeline, the dialogue as a lane of words, the shots as cards, layers on their own lanes](img/film/studio.png)

- **Timeline**: the scenes are the sections, the cuts are the grid, the dialogue is the lane of words, the soundtrack is the waveform, and the shots are cards. Add text, pictures, icons and shapes as **layers** on their own lanes, and drag them up and down to put them in front or behind.
- **Supervisor, Review, Acting, Continuity, Lighting, Colour match, Clean up, Layers, Library, Export**, with the same tools you know. Pictures and takes you choose in the film workspace show up here, and the other way round.
- **Home** takes you back to the film.

Because the studio began as a music-video tool, a few music-first parts are hidden on a film, and the odd label may still read that way. A few tools still speak in song terms; they are being turned into film terms one by one.

## Keyboard shortcuts

The same list is in the Studio: press `?` or `Ctrl+/`.

**Playback**

| Press | Does |
|---|---|
| `Space` | Play / pause |
| `K` | Play / pause (with J and L) |
| `J` | Back 5 seconds |
| `L` | Forward 5 seconds |
| `Shift+←` | Back 5 seconds |
| `Shift+→` | Forward 5 seconds |
| `Home` | Go to the start |
| `End` | Go to the end |
| `M` | Mute the player |
| `F` | Full screen: just the video (Esc leaves) |

**Shots**

| Press | Does |
|---|---|
| `←` | Previous shot |
| `→` | Next shot |
| `,` | Previous shot that needs attention |
| `.` | Next shot that needs attention |
| `Ctrl+Shift+U` | Undo the last change to a shot (approve, keyframe, end frame, motion, lock) |
| `Ctrl+Shift+Y` | Redo it |
| `A` | Approve this shot's new keyframe or take |
| `E` | Open this shot's Compose tab (start and end, references, motion) |
| `R` | Re-render this shot (shows the price first) |

**Panels**

| Press | Does |
|---|---|
| `Y` | Open or close the Layers panel |
| `T` | Add a text layer at the playhead |
| `H` | Hide or show the selected layer |
| `Ctrl+K` | Director Command |
| `Ctrl+I` | Show or hide the inspector |
| `Ctrl+J` | Show or hide the timeline |
| `Ctrl+Shift+J` | Compact or full-height timeline |
| `Ctrl+Shift+P` | Command palette: find any action or shot |
| `?` | This list (also Ctrl+/) |
| `Ctrl+Z` | Undo the last change to the layers (while the Layers panel is open) |
| `Ctrl+Shift+Z` | Redo it |
| `Ctrl+Y` | Redo it (same as Ctrl+Shift+Z) |

**Sound**

| Press | Does |
|---|---|
| `Shift+M` | Turn this shot's own sound on or off |

**Project**

| Press | Does |
|---|---|
| `F1` | Documentation |
| `Ctrl+N` | New music video |
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+E` | Export |
| `Ctrl+1` | Simple mode |
| `Ctrl+2` | Director Mode |
| `Ctrl+,` | Settings |

## When something goes wrong

- **"Choose a model first" or "No provider".** Open Settings and add a key, or pick a model in Plan & budget.
- **A picture has wrong hands or a face.** Press *Check hands & faces* in Pictures, then *Make more* on the flagged card, or fix just the hand in the Timeline view (the keyframe tools).
- **Nothing is made.** Look at the queue chip in the Studio's top bar; a job that failed shows why. Nothing is charged for a job that failed before it was accepted.
- **A music-video project will not open.** FilmCrafter makes films. Open it in PULSEFRAME; finished ones also open in the Studio here.
- **Windows warns about the installer.** It is not signed yet (no certificate). Choose *More info > Run anyway* if you trust the file.
