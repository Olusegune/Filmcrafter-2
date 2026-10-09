# Start and end frames

Every shot has a **start frame** and, optionally, an **end frame**. A video model that accepts both animates *between* them, so you decide exactly where a shot begins and where it lands.

## In the app

Open a shot (double-click it) → **Start & end frames**, or in **Select & review → Keyframes**, open **Start & end frames** under any shot.

**Start**
- **Its keyframe**: the still you chose in Select & review.
- **Continue from the previous shot's last frame**: free; the shot picks up exactly where the previous take ended.

**End**
- **None**: the model decides how the shot ends (the default).
- **Its own**: describe how the shot ends, then **Make 2 end stills** (priced first; the start frame is used as the main reference so people, wardrobe, set and light stay the same), or **Use an image…** of your own. Choose one; reject (×) or restore (↺) any. Nothing is deleted.
- **Flow into the next shot**: the shot ends exactly on the next shot's start frame, so the two play as one continuous move. If the next shot's start changes, this end follows it. **Flow selected shots together** in Select & review does this for a whole run of shots.

A shot can't both end on the next shot's start *and* have that next shot continue from its last frame (that would be circular); the app explains and asks you to pick one.

## Which models

PULSEFRAME reads each model's real input schema. When a shot has an end frame:

1. If the chosen model takes a last frame, it is sent there (never as a reference image).
2. If not, but the same family has a start+end version on the same provider, that shot renders on it. The confirmation names the switch and prices it.
3. If neither, the end frame is not sent, and the shot panel and confirmation say so before anything is paid.

| Takes an end frame directly | Switches to a start+end version (fal) | Can't |
|---|---|---|
| Seedance 2 (fal image-to-video), Veo 3.1 (Google), Wan 3.0, Wan 2.2 Turbo, LTX 2.3, Vidu Q3 Turbo (fal), Hailuo 02 (Kie) | Kling 3 Turbo → Kling 3 Pro; Veo 3.1 Fast → Veo 3.1 Fast first-last-frame; Seedance 2 reference → Seedance 2 image-to-video; Hailuo 2.3 / 02 Fast → Hailuo 02; PixVerse 5.5 → PixVerse 5.5 transition | ComfyUI Wan 2.2 5B; Kling 2.6, Wan 3.0, PixVerse on Kie; Seedance 2 on Kie (refuses extra images beside a first frame) |

### On Kie.ai (the first-class provider)

These Kie models take a start picture and an end picture, and PULSEFRAME sends both:

| Kie model | How the two frames go in |
|---|---|
| Seedance 2.0, Seedance 2.0 Fast, Seedance 2.0 Mini, Seedance 2.5 | `first_frame_url` and `last_frame_url`. This is the model's own two-frame mode, so its reference pictures, videos and audio are left out of the request (Kie refuses them beside a first frame), and a last frame is never sent without its first frame. The two frames carry the continuity. |
| Kling 3.0 | One picture list, `image_urls`: the first picture is the first frame, the second is the last frame (single-shot mode). Character sheets are never put in that list. |
| Kling 2.1 Pro, Kling 2.5 Turbo Pro | `tail_image_url` |
| Hailuo 02 (Standard, Pro), Seedance 1 Lite | `end_image_url` |
| Wan 2.7 image-to-video, Wan 3.0, MiniMax H3 image-to-video, Gemini Omni Flash | `last_frame_url` |

Hailuo 02 on Kie is proven with a real render (below). **The others are built from Kie's published schemas and have not yet been proven with a real render on your account: the Start → End tab says so plainly. Try one shot first and look at where it lands.**

## Proven with real renders

| Model | Date | Result |
|---|---|---|
| Hailuo 02 standard (Kie) | 2026-10-01 | Last frame matched the end frame (difference 1.9 vs 21.0 to the start frame). 50 credits. |
| Wan 2.2 Turbo (fal) | 2026-10-01 | 3.3 vs 19.8. $0.10. |
| Hailuo 02 standard (fal), reached by the automatic switch from Hailuo 2.3 | 2026-10-01 | 2.3 vs 21.3. $0.45. |
| Vidu Q3 Turbo (fal) | 2026-10-01 | 0.8 vs 20.7. $0.04. |

You can prove a model yourself from a take you already paid for: in the shot's Start → End tab, **Check where the take landed** compares the take's last frame with the end and start pictures (the same numbers as the table above: a small difference to the end picture and a large one to the start). **Mark this model as proven** keeps the result on this computer (`.pulseframe/proven_models.json`) and the warning goes away for that model; a take that did not land cannot be marked.

Models not yet proven show "Not yet proven on this model with a real render: check the result" in the shot panel. 
