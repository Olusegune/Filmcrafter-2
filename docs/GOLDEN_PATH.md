# The golden path of a film

The order that makes a film cheapest, calmest and most likely to come out right. The app nudges you along it; nothing forces it.

1. **Story.** Bring the screenplay (or an idea). It is kept exactly as given. Lock it when it is final.
2. **Cast & World.** The people (a few pictures each: face, full body, back), the places and the props, and one **visual style**. These are what keep every shot looking like the same film. Bigger, clearer pictures give better results.
3. **Shots.** The story is cut into shots. Check who is in each shot, and fix what looks wrong (cheap: it is only text).
4. **Test one shot.** Before you make everything, make **one** picture, and then one video, for a shot with a speaking person. Make Film points you to one. If the look is wrong, change the style or the cast pictures, not 60 pictures.
5. **Pictures.** Make a few for each shot, choose one, lock it. *Select & review* lets you pick shots, enlarge the pictures and approve them before any video is paid for.
6. **Voices.** Attach your recordings (`CHLOE_S01-04.wav`) **before** the video, so each mouth follows its voice (the model can follow a recording only if it is there when the video is made). Or give each person an ElevenLabs voice.
7. **Video.** Make the video for the shots whose pictures are right. Every price is shown first.
8. **Review.** The Supervisor flags what looks wrong (hands, faces, continuity, stale takes); fix only those.
9. **Export.** Your recordings are laid over their shots (they, not the video model's sound, are heard). Export the film, or hand it to your editor (EDL, OpenTimelineIO, Final Cut XML, one audio file per person per shot).

Rules the whole path keeps: free things come first; every paid step shows its price and waits for a yes; chosen and locked work is never replaced; nothing you made is ever deleted.

Where the app says it: the step bar along the top (Story, Cast & World, Shots, Studio, Export) with its one-line hint; the gold notes at the top of Pictures and Video ("test one shot", "N voices have no recording"); the Voiceover screen; the audit tool (`scripts/audit_film.py`) checks the result.
