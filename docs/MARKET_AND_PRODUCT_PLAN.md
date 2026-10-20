# FilmCrafter: how I would make it a product (market, plan, and what comes from Pulseframe)

Written 2026-10-20. It separates **what is verified** (checked in this repo, with tests or real runs) from **hypotheses** (things about the market that nobody has tested yet). The hypotheses are the part to test first, cheaply, before building more.

## 1. Where the product honestly stands

**Real strengths (verified):**
- A film is a folder, not a database or a cloud account. Everything is readable, backed up, portable (`.filmpack`) and never locked in.
- Money is handled unusually carefully: price shown first, a ledger of every paid operation, spending limits, "never send twice if the outcome is unknown", and a new **Costs** screen. Few tools in this space are honest about cost.
- Bring-your-own provider keys: the maker pays the providers directly, with no markup and no credits to resell. That keeps your own running costs near zero and your legal exposure low.
- A real production chain, not just a prompt box: story, Bible (cast, places, props, style), shots, storyboard, hero picture, video, voices, sound and music, a mixed export, and the new **Guide** that tells a newcomer the order and the price of each step.
- 560+ front-end tests, about 2,000 engine tests, security tests for every command that touches the outside world.

**Real gaps (verified or visible in the repo):**
- Nobody but you has used it. The lip-sync result is "better, not proven"; generated sound has not been judged by a person; the installed app has not been walked through by a stranger.
- Windows only; installers are unsigned (Windows will warn "unknown publisher"); there is no in-app update, no licence check, no crash reporting, no EULA that says who owns AI output and what the provider terms are.
- It depends entirely on other companies' models and prices. They change, and they can change in ways that break the product or its margins.
- Setup friction: a newcomer needs to understand API keys. That is a real barrier outside technical circles.
- Rights are "not established" for generated sound and music, and the app says so honestly; a commercial customer will ask.

## 2. Who I would sell to (my judgement, to be tested)

I would not try to sell to "everyone who wants to make AI video". That market is crowded by well-funded companies with their own models, and they win on convenience. Where FilmCrafter is different is **control, continuity, honesty about cost, and owning your files**. That points to people who make *stories with the same characters across many shots* and who are *careful about money and ownership*.

| Segment | Why they fit | Willingness to pay | My view |
|---|---|---|---|
| **Independent narrative filmmakers and short-film makers** (scripts, recurring characters, festivals) | Need consistent cast, shot control, dialogue, sound; script and storyboard in hand | Medium | **Beachhead.** The script-and-storyboard import you asked for fits them exactly |
| **Small studios and agencies** making ads, explainers, brand films, pitch visuals | Need speed, control, handover files, predictable cost | **Highest** | **Second wave.** Needs signing, licences, an editor handover (FCPXML/EDL exists), team features later |
| **Regional film industries and creator economies** (for example Nollywood-style production: high volume, low budgets, strong local voices and accents) | Huge output, cost pressure, underserved by Western-centred tools | Low to medium per head, large in number | **A hypothesis worth testing early, and you may know it better than I do.** Pricing must suit local incomes; BYO keys helps |
| **Music-video makers** | Pulseframe's market | Medium | Keep as the sister product; do not mix the two audiences in one message |
| **Hobbyists and casual creators** | Many of them | Low | Do not target. They want one button; the big tools give them that |

Competitors to study properly before you price (I cannot give you current prices from memory, check each one this week): the model companies' own tools (Runway, Luma, Google Flow/Veo, OpenAI Sora, Kling), aggregator tools that sell credits across models (Higgsfield and similar), storyboard-first tools (LTX Studio, Boords, Katalist), and general editors adding AI. Your honest edge is not "better video". It is **"your film stays yours, you see every price first, and the same character stays the same person across the film."**

## 3. How I would charge (hypotheses, not facts)

- **Do not resell credits.** Reselling makes you a payment business with disputes and margin pressure. BYO keys keeps you out of that.
- Free: the sample film, the guide, everything up to the first paid step, so people feel the product before they need a key.
- Paid: a licence for the Studio features that matter to a working filmmaker (exports without a watermark, storyboard and asset import, mixed audio export, handover to editors, unlimited films). Two shapes to test against each other: **one-time purchase with a year of updates** versus **monthly**. Filmmakers often dislike subscriptions on top of provider costs; agencies are fine with them.
- Price points: I will not invent numbers. Test three prices in the private beta (below) and ask "at what price would this be too cheap to trust, a bargain, getting expensive, too expensive" with each tester.
- A team or studio plan later (shared Bible, shared presets, an audit log of spending), once individuals pay.

## 4. How I would get the first 50 customers

1. **Private beta of 20 to 30 people** from the segments above. Free licence in exchange for a recorded session of them making one scene, and a weekly one-line answer to "would you be upset if this went away?" That one question is the market test. Aim for at least 40% "very upset".
2. **Make films with it in public.** One short film, one case study: cost per minute, time taken, what went wrong. The Costs screen is the honest hook: people in this space distrust opaque pricing.
3. **Teach, don't advertise.** Short tutorials on the problems the product actually solves (a character that looks the same in every shot; storyboard to film; voice and sound). Post where AI filmmakers already gather.
4. **Partners.** Providers like Kie.ai and ElevenLabs often have affiliate or partner programmes; ask. A filmmaking school or a film collective in your region as a first institutional customer is worth more than ads.
5. Measure: people who finish a first scene (not who install), time to first picture, spend per film, who comes back in week 2.

## 5. What it needs before strangers pay (in order)

**A. Trust (must have before any paid launch)**
1. Code signing certificate and signed installers (Windows SmartScreen warnings kill installs). Needs a purchase; you decide.
2. Signed in-app updates, which need a public place for releases and an updater key (steps in `docs/UPDATES.md`).
3. EULA and a plain-language rights page: you own what you make subject to each provider's terms; AI output may not be copyrightable everywhere; sound and music rights are the provider's terms. A lawyer should read it.
4. Opt-in crash and error reports (no film content, no keys).
5. Licence check that works offline for a grace period.

**B. First-run and UX polish (this is where polish pays most)**
- One dialog component for all sheets (Escape, focus trap, labelled), already built in the Pulseframe repo.
- A calm Home with one way in and a "Continue where you left off" card; one orange next-step button per screen; tools shown only when they can work.
- Export that shows the folder, file name, length and size before pressing the button, and a post-export check on the finished file.
- Friendly errors everywhere (no raw `TypeError`), a 12 px minimum text size, skip links and landmarks, and a sweep at 125% and 150% scaling.
- Faster start: load screens when opened.

**C. Architecture (so you can keep shipping without breaking things)**
- A schema version in every film record with a tested upgrade path (so a film made in 0.26 opens in 1.0). The film folder already tolerates added fields; make it a rule with a test.
- Split the very large files (`lib.rs`, `render.py`, the big screens) behind the tests that exist.
- One shared state layer instead of dozens of local flags in the big screens.
- CI on every push (type check, tests, `npm audit`, `pip-audit`, `cargo clippy`), Dependabot and a weekly audit, all of which exist in Pulseframe and can be copied.
- The spending token (S-01) from Pulseframe: a paid batch can only start from a click that carries a one-time token, enforced by the engine, with a batch ceiling.

## 6. What in the Pulseframe repo is useful here

I read the 28 commits since the 1.36.0 baseline that FilmCrafter forked from, the audit, the security review and the remediation plan. Ranked by value for FilmCrafter:

| Item (in `pulseframe`) | Why it matters here | Effort | Port? |
|---|---|---|---|
| `Sheet.tsx` (one accessible dialog, 57 sheets moved onto it) | Biggest accessibility and consistency win; FilmCrafter has the same hand-built dialogs | Medium | **Yes, first** |
| S-01 spend confirmation token and engine batch ceiling | Closes "a paid batch could start without a confirming click" at the engine, not just the screen | Medium | **Yes** |
| CI workflows, Dependabot, weekly audit, `cargo clippy` gate | FilmCrafter has no CI at all | Small | **Yes** |
| Export folder and file name choice, output details, friendly formats, `export_validate.py`, Export Guardian (`guardian.py`) | Checks the finished film (frame count, audio length, black or frozen stretches) | Medium | **Yes** |
| Home screen with Continue card, shorter rail, Fold, friendly errors, lazy loading | The UX polish the audit measured | Medium | **Yes** |
| Security review and arc42 architecture docs (tested for stale links) | A buyer's or investor's due diligence reads these | Small to copy, then adapt | **Yes** |
| `versions.py` (named snapshots of the choices that make a cut) | Lets a filmmaker try a cut and go back; takes and pictures are never touched | Medium | Soon |
| `checkup.py` ("check my video", every free check in one list) and `integrity.py` (does the shot still show what it was meant to show) | Turns many separate checks into one calm list; FilmCrafter's `filmcheck` and `supervisor` can feed it | Medium | Soon |
| `agentapi.py` and `docs/AGENTS.md` (MCP tools for an AI agent, with proposals and "rendering is always a request") | Genuinely differentiating: "drive your film from Claude, safely". Same safety model as the app | Larger | After the polish |
| `advisor.py` (which model for which shot, three plans with costs), `discover.py` (new models found automatically) | Cost control and model churn, which is your main business risk | Medium | Later |
| `script_flex.py`, `producer_import.py` (a production package from a plugin) | Overlaps the new materials import; the package format could become a standard way to hand FilmCrafter a whole production | Small to align | Align later |
| `castboard.py` (who wears what, scene by scene, where it drifts) | Continuity for films; FilmCrafter's continuity check is shot-level | Small | Maybe |
| Instruments, songs, dance, singers, lyrics, take windows | Music-video features | n/a | **No** (different product) |

I have **not** ported any of this in this batch except by reading it. Porting means merging two code bases that have diverged for 17 versions, so it should go in small, tested steps, one row at a time, starting at the top of the table.

## 7. Your idea: storyboards, asset sheets and more as input

**I think it is right and it is the best next feature.** A script says what happens; a filmmaker's own storyboard says *how it looks*, and an asset sheet says *who and what it looks like*. Those are the things generative video gets wrong, and the ones a serious filmmaker already has. It also fits the product's promise that the maker stays in control, and it is free to run (nothing is bought).

**Built in this batch (v1, free, local):** *Bring your own materials*, opened from the Guide.
- **Storyboard panels** as pictures, folders, zips or PDFs (one picture per page). Matched to shots by file name (`S01-03.png`, `scene 2 shot 3`), or by order when the counts agree, otherwise you say which shot. A panel becomes the chosen storyboard for its shot and, if you allow it, the framing reference for that shot's hero picture. A locked storyboard is never touched; a shot that already has a panel is replaced only if you tick it.
- **Asset sheets** (`characters/Sarah/front.png`, `locations/Kitchen.jpg`, `props/Red kettle.png`): recognised by folder and file name, matched to the cast, place or prop by name, new ones created only when named. Views (front, side, back, turnaround, expression, wardrobe) are recognised. The same picture is never added twice.
- **Shot list** (CSV from Excel or Sheets): scene, shot, size (CU, WS, OTS…), movement, length, description, dialogue, notes. Normalised to FilmCrafter's camera words; unknown words are kept as a note, not lost. Fields you wrote yourself are never replaced unless you tick the row; new shots are added only if you tick them.
- **Notes** (`.txt`, `.md`): kept with the film; a tone, world or rules note can be added to the Bible (appended, never replacing).
- Every import shows a **plan first**, takes a snapshot of the film's records before applying, is logged, and never sends or buys anything. Originals stay where they are.

**Honest limits of v1:** the PDF reader takes the biggest picture inside each page, so a PDF whose pages are drawn as lines or text (not embedded pictures) is told to export pages as pictures; a page with several panels is one panel; Excel files must be saved as CSV; file names do the matching, so a storyboard with unhelpful names needs the shot chosen by hand (the screen lets you). It was checked with generated files in tests and in the browser harness with mock data; **it has not been tried on a real storyboard or in the installed app.**

**Next steps for this feature (not done):**
1. Try it on one real storyboard and one real character sheet from you; fix what is clumsy.
2. Read `.xlsx` and `.docx` directly (needs two small, vetted libraries).
3. Split a page of several panels into panels (grid detection).
4. Use the panel to *write the shot*: ask the vision model (price shown first) to describe a panel and fill framing, action and camera, then let the maker edit.
5. Use asset sheets to *check* results: after a picture is made, compare it to the sheet and flag drift (a paid, optional vision check).
6. A "production package" file that holds all of the above plus the script, so a team can hand a whole production over in one zip (aligned with Pulseframe's producer package).

## 8. A staged plan

| Stage | Goal | Contents | Needs from you |
|---|---|---|---|
| **0 (done)** | A trustworthy base | Phases 0 to G, Guide, mix preview, Costs, materials v1 | — |
| **1** | Learn from real use | You try 0.26.x and materials on a real film. Fix what is clumsy. Recruit 5 beta people | Your time, a real storyboard |
| **2** | Trust and polish | Sheet component, Home, export checks, spend token, CI, friendly errors, schema versions | Approve each batch |
| **3** | Ready to charge | Signing, updates, licence, EULA, crash reports | Certificate purchase, a lawyer, a place to host releases |
| **4** | Private beta | 20 to 30 users, weekly question, pricing test | Recruiting, a feedback channel |
| **5** | Differentiators | Agent/MCP, versions, checkup, advisor, take comparison, captions | — |
| **6** | Public launch | Case-study film, tutorials, partner outreach | A film to show |

Do not skip stage 1. Everything else is guessing until a person other than you has finished a scene with it.
