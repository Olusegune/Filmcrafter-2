# Starting a film: the story

A FilmCrafter film begins with its story. Nothing about music is needed.

## Home

![Home: drop a screenplay, start a new film, or start from an idea. Recent films and older projects below](img/film/home.png)

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

## What is built so far

Story, scenes, characters and places read from a screenplay, versions, Story Lock. Cast &amp; World, the storyboard, making the film, review and export come in later updates; they are shown along the top so the road ahead is visible.

## Cast & World: the Production Bible

Open **Cast & World** along the top. The first time, FilmCrafter fills it from your story (the speaking characters and the places); **Add from the story** brings in anything new later and never changes what you wrote.

![Characters: pictures, traits, wardrobe, and related states](img/film/cast.png)

- **Characters, Places, Props**: each is one entry with **states** (Sarah at 8, at 28, at 70; the kitchen by day and by night). Bring your own artwork (the first picture is the master); it is copied into the film and the original is left alone. Places have a layout (doors, windows, landmarks, where actors can stand and the camera can go) so a set doesn't change between shots.
- **Rules & style**: the visual style (photoreal cinematic, stylized 3D, 2D, painterly, anime-inspired, stop motion, clay and more), the rules of the world, and how the film is made (cinematography, lighting, acting, colour, continuity).

![Rules and style](img/film/bible.png)

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

Move, duplicate, split, join and take out shots freely (a shot you take out is moved aside, not deleted). Running the breakdown again only drafts scenes that have no shots; shots you have edited are never changed. A shot whose storyboard is locked can't have its framing, people or place changed until you unlock it.

## Making the film

**Storyboard**, **Make film**, **Review** and **Export** along the top open the same workspace, one step at a time.

![The storyboard wall: choose a panel, lock it, or use your own](img/film/make.png)

1. **Storyboard.** Make a few pictures of each shot's framing (or use your own), choose one and **lock** it. The composition is fixed from here on.
2. **Keyframes.** The hero frame of each shot is made from the locked storyboard panel, the Cast pictures and the shot's contract. Choose one and **lock** it. A shot's keyframe is only available once its storyboard is chosen.
3. **Video.** Each shot is brought to life from its locked keyframe (or bring your own video). Compare takes and **approve** the one to use. A shot's video is only available once its keyframe is chosen.
4. **Sound & export.** Choose a soundtrack (music, a dialogue mix, an ADR track you made elsewhere; it is copied in untouched) or keep silence, then export the film. Shots without a take appear as storyboard cards and the film is marked as a draft.

**Money.** Every generation shows the provider's price first and waits for your yes. Nothing is made until you press **Make**. Chosen and locked work is never replaced by a new generation. Pictures and video go through the same render engine PULSEFRAME uses: your provider keys, budgets, queues and retries all apply, and a render that was running when you closed the app picks up where it left off.

Under the hood the film builds a render project (in the film's `render` folder) from the Shot Contracts and the Bible, so the pictures and clips are made with the characters, places, style, camera, light and acting you set.
