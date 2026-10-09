"""Worldwide creative-direction library.

Curated visual traditions from cinema and music video around the world, each described as a working brief: camera,
light, palette, editing rhythm, movement, design, a suggested look and acting profile, and what to avoid. Entries
describe film-making approaches, never peoples; each carries a respect note so a direction is used with care.

Browse and filter, rank against the song (tempo, energy, mood; free and deterministic), and apply one to a project:
it becomes the brief for the three AI directions and the treatment, fills the Production Bible, and sets the look and
acting profile (only where you haven't set your own). Your own directions can be saved to the library too.

  python -m filmcrafter_engine.directions_library <action> [project] --data '{...}'
  actions: list | match | apply | save | delete
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

USER_LIB = os.path.join(os.path.expanduser("~"), ".filmcrafter", "directions.json")

D = lambda **k: k   # noqa: E731  (keeps the table readable)
LIBRARY = [
    # ---------------- Africa
    D(id="lagos-nights", name="Lagos Nights", region="Africa", origin="Nigeria · Afrobeats video", tags=["romantic", "joyful", "confident", "night"],
      genres=["afrobeats", "amapiano", "r&b"], bpm=(95, 118), energy="mid",
      summary="Warm, glossy city nights: rooftops, danfo lights, fashion-forward friends, easy swagger and romance.",
      camera="Smooth gimbal glides and slow push-ins; low angles for swagger; wide rooftop establishing shots.",
      light="Warm practicals, neon signage, sodium streetlight, soft golden skin light.",
      palette=["amber", "magenta neon", "deep teal", "gold"], editing="Cuts on the kick; hold the romantic beats longer.",
      movement="Relaxed grooves, shoulder bounces, group dance breaks on the hook.",
      design="Contemporary Lagos fashion, ankara accents, busy markets, rooftops, bridges.", look="live-action", acting="expressive",
      avoid="Poverty tourism, generic 'Africa' imagery.", respect="Show a real, modern city; credit local stylists and dancers where you can."),
    D(id="nollywood-melodrama", name="Nollywood Melodrama", region="Africa", origin="Nigeria · home-video drama", tags=["dramatic", "family", "emotional"],
      genres=["ballad", "gospel", "highlife"], bpm=(60, 95), energy="low",
      summary="Heightened family drama told in close faces, reaction shots and big emotional turns.",
      camera="Frontal mediums and close-ups, reaction inserts, occasional dramatic zoom.", light="Bright domestic interiors; hard window light for confrontations.",
      palette=["warm beige", "wax-print colour", "deep red"], editing="Beat-by-beat reaction cutting; pauses before revelations.",
      movement="Little dance; gestures and confrontations carry the scenes.", design="Living rooms, church halls, family compounds, wax-print dress.",
      look="live-action", acting="dramatic", avoid="Mocking the genre's conventions.", respect="Played sincerely, not as parody."),
    D(id="sahel-golden", name="Sahel Golden Hour", region="Africa", origin="West African art cinema", tags=["contemplative", "spiritual", "melancholic"],
      genres=["folk", "desert blues", "ambient"], bpm=(60, 100), energy="low",
      summary="Wide, patient frames of earth, wind and light; people small in vast landscapes; music as meditation.",
      camera="Locked-off wides, slow lateral tracks, long takes.", light="Low golden sun, dust haze, deep blue dusk.",
      palette=["ochre", "indigo", "sand", "white"], editing="Long holds, few cuts, cut on phrase endings.",
      movement="Walking, weaving, hands at work; stillness.", design="Adobe architecture, indigo cloth, open desert.", look="live-action", acting="restrained",
      avoid="Exoticising or 'timeless' clichés.", respect="Name real places; avoid sacred sites and ceremonies without permission."),
    D(id="amapiano-house-party", name="Amapiano House Party", region="Africa", origin="South Africa · amapiano", tags=["joyful", "energetic", "party"],
      genres=["amapiano", "house", "gqom"], bpm=(108, 118), energy="high",
      summary="Township-to-club energy: log-drum drops, dance crews, sneakers, crowds that move as one.",
      camera="Handheld in the crowd, overhead dance formations, wide-angle close to dancers.", light="Coloured party lights, strobes on drops, warm dusk outside.",
      palette=["electric blue", "hot pink", "concrete grey", "white sneakers"], editing="Cut to the log drum; freeze or speed-ramp on the drop.",
      movement="Signature amapiano steps, crew formations, call-and-response dancing.", design="Street fashion, bucket hats, yard parties, taverns.",
      look="live-action", acting="energetic", avoid="Staging dances nobody does.", respect="Use real dance vocabulary; credit choreographers."),
    D(id="afrofuturist-epic", name="Afrofuturist Epic", region="Africa", origin="Afrofuturism · diaspora", tags=["epic", "triumphant", "mystical"],
      genres=["hip-hop", "afrobeats", "electronic", "soul"], bpm=(80, 130), energy="high",
      summary="Myth and technology fused: regal figures, sculptural costume, futuristic cities grown from tradition.",
      camera="Hero low angles, symmetrical compositions, sweeping crane moves.", light="Rim-lit silhouettes, bioluminescent accents, gold highlights.",
      palette=["gold", "royal purple", "obsidian", "cyan"], editing="Grand reveals on the downbeat; tableau holds.",
      movement="Ceremonial processions, powerful poses, synchronised movement.", design="Sculptural armour, adinkra-like geometry (invented, not copied), floating architecture.",
      look="afrofuturist", acting="dramatic", avoid="Copying real sacred regalia.", respect="Invent symbols rather than borrowing sacred ones."),
    D(id="cairo-cinema", name="Cairo Golden Age", region="Middle East & North Africa", origin="Egypt · classic cinema", tags=["romantic", "nostalgic", "elegant"],
      genres=["arabic pop", "tarab", "ballad"], bpm=(70, 110), energy="mid",
      summary="Black-and-white elegance of mid-century Egyptian film: grand staircases, orchestras, longing looks.",
      camera="Graceful dolly moves, soft close-ups, staged two-shots.", light="Glamour key light, soft halation, deep shadows.",
      palette=["silver", "black", "pearl"], editing="Classical continuity, dissolve-like pacing.",
      movement="Elegant gestures, waltz-like couples, orchestra performance.", design="Art-deco salons, Nile balconies, tailored suits and gowns.",
      look="live-action", acting="expressive", avoid="Belly-dance clichés out of context.", respect="Reference the era's real stars and craft respectfully."),
    # ---------------- Asia
    D(id="bollywood-spectacle", name="Bollywood Spectacle", region="Asia", origin="India · Hindi film song", tags=["joyful", "romantic", "celebratory"],
      genres=["filmi", "bhangra", "pop"], bpm=(90, 140), energy="high",
      summary="The song as a dream: costume changes, sweeping locations, big group choreography and star close-ups.",
      camera="Crane sweeps, whip pans between locations, hero close-ups on the chorus.", light="Saturated, bright, sunlit; fairy lights at night.",
      palette=["marigold", "fuchsia", "emerald", "gold"], editing="Location jumps on phrase changes; choreography on the beat.",
      movement="Large synchronised choreography, hand mudra-inspired flourishes, playful couple dance.", design="Lehengas and kurtas, palaces, mountain meadows, festival streets.",
      look="live-action", acting="expressive", avoid="Using sacred festivals as backdrop decoration.", respect="Research the region and occasion each costume belongs to."),
    D(id="k-pop-concept", name="K-pop Concept Video", region="Asia", origin="South Korea · idol video", tags=["confident", "energetic", "stylish"],
      genres=["k-pop", "pop", "edm"], bpm=(100, 140), energy="high",
      summary="Set-per-concept precision: sculpted sets, crisp formation dance, individual close-ups for each member.",
      camera="Precise dolly and crane moves, snap zooms, symmetrical formation wides.", light="Clean high-key sets, coloured gels per concept, glossy reflections.",
      palette=["pastel pink", "chrome", "black", "neon accent"], editing="Hard cuts on every accent; point-choreography on the hook.",
      movement="Tight formation choreography with a signature 'point' move.", design="Concept sets (school, lab, candy, dystopia), coordinated styling.",
      look="live-action", acting="energetic", avoid="Copying a real group's signature moves.", respect="Create original choreography."),
    D(id="wong-kar-wai-mood", name="Hong Kong Mood Piece", region="Asia", origin="Hong Kong · 1990s art cinema", tags=["melancholic", "romantic", "lonely", "night"],
      genres=["r&b", "trip-hop", "indie", "ballad"], bpm=(60, 100), energy="low",
      summary="Neon loneliness: step-printed motion, smoky corridors, lovers who never quite meet.",
      camera="Handheld step-print blur, tight doorframes, off-centre compositions.", light="Neon green and red, fluorescent corridors, rain reflections.",
      palette=["emerald", "crimson", "tungsten amber"], editing="Slow motion against normal speed; repeated moments.",
      movement="Smoking, waiting, walking past each other.", design="Narrow apartments, noodle bars, qipao and sharp suits.",
      look="live-action", acting="restrained", avoid="Orientalist clichés.", respect="Treat the city as lived-in, not exotic."),
    D(id="anime-opening", name="Anime Opening", region="Asia", origin="Japan · TV anime OP", tags=["energetic", "hopeful", "epic"],
      genres=["j-pop", "rock", "edm"], bpm=(120, 180), energy="high",
      summary="Ninety seconds of promise: character line-ups, sky shots, speed-line runs and a title-card-worthy finale.",
      camera="Dynamic smears, pans across line-ups, sakuga action beats.", light="Bright skies, lens flares, dramatic sunset backlight.",
      palette=["sky blue", "white", "vivid accent colours"], editing="Cut on every beat in the verse; hold the hero shot on the hook.",
      movement="Running, jumping, wind in hair, action poses.", design="School rooftops, city skylines, stylised fantasy.",
      look="anime", acting="expressive", avoid="Copying a real show's characters.", respect="Original characters and designs."),
    D(id="ghibli-pastoral", name="Pastoral Wonder", region="Asia", origin="Japan · hand-drawn feature animation", tags=["gentle", "hopeful", "nostalgic", "whimsical"],
      genres=["folk", "acoustic", "orchestral", "lo-fi"], bpm=(60, 110), energy="low",
      summary="Wind across fields, small kindnesses, food, flight and weather; wonder in ordinary life.",
      camera="Gentle pans, low grassy angles, sky-filled wides.", light="Soft daylight, cloud shadows, warm lamplight.",
      palette=["meadow green", "sky blue", "cream", "red roof"], editing="Unhurried; let moments breathe.",
      movement="Everyday gestures, cycling, running through grass.", design="Rural houses, trains, bakeries, forests.",
      look="hand-drawn-2d", acting="natural", avoid="Copying a studio's characters.", respect="Original world and creatures."),
    D(id="chinese-wuxia", name="Wuxia Poetry", region="Asia", origin="China · martial-arts cinema", tags=["epic", "romantic", "graceful"],
      genres=["orchestral", "c-pop", "cinematic"], bpm=(70, 120), energy="mid",
      summary="Swordplay as dance: bamboo forests, flowing silk, colour-coded chapters and weightless motion.",
      camera="Wire-work arcs, slow motion, overhead choreographed wides.", light="Diffused forest light, colour-washed chapters.",
      palette=["jade", "vermilion", "ink black", "silk white"], editing="Rhythmic action beats, slow-motion peaks.",
      movement="Flowing martial choreography, leaps, fabric trails.", design="Temples, bamboo, lakes, flowing robes.",
      look="live-action", acting="restrained", avoid="Mixing dynasties carelessly.", respect="Research the era's dress and architecture."),
    D(id="thai-dreamlike", name="Tropical Dreamlike", region="Asia", origin="Southeast Asian art cinema", tags=["mystical", "contemplative", "dreamy"],
      genres=["ambient", "indie", "dream pop"], bpm=(60, 100), energy="low",
      summary="Jungle nights, spirits and memory drifting into each other; slow, hypnotic and gentle.",
      camera="Static wides, slow dollies into darkness.", light="Moonlight, fireflies, fluorescent tubes in the jungle.",
      palette=["deep green", "violet night", "warm lamp"], editing="Long takes, time slips.",
      movement="Stillness, slow walking, sleeping figures.", design="Rural clinics, rivers, jungle paths.", look="live-action", acting="restrained",
      avoid="Presenting belief as superstition.", respect="Treat local beliefs with seriousness."),
    # ---------------- Europe
    D(id="french-new-wave", name="French New Wave", region="Europe", origin="France · 1960s cinema", tags=["playful", "romantic", "rebellious"],
      genres=["indie", "chanson", "pop", "jazz"], bpm=(80, 130), energy="mid",
      summary="Jump cuts, street shooting, lovers talking in cafés and running through Paris; cool and free.",
      camera="Handheld street tracking, looks to camera, long walking takes.", light="Available light, overcast Paris grey, café interiors.",
      palette=["black and white", "primary red", "blue", "yellow"], editing="Jump cuts, playful rule-breaking.",
      movement="Walking, running, spontaneous dancing in a café.", design="Striped tops, trench coats, cafés, bookshops.",
      look="live-action", acting="natural", avoid="Paris postcard clichés.", respect=""),
    D(id="nordic-noir", name="Nordic Noir", region="Europe", origin="Scandinavia · crime drama", tags=["dark", "melancholic", "tense", "cold"],
      genres=["electronic", "indie", "synth", "ambient"], bpm=(60, 110), energy="low",
      summary="Cold light, empty landscapes and quiet dread; faces that hide more than they show.",
      camera="Slow drone wides, static interiors, long lenses.", light="Overcast daylight, blue hour, practical lamps.",
      palette=["slate blue", "grey", "muted green", "white"], editing="Slow, tense, cut on silence.",
      movement="Minimal; people alone in big spaces.", design="Concrete, pine forests, wool knits, minimal interiors.", look="live-action", acting="restrained",
      avoid="", respect=""),
    D(id="italian-neorealism", name="Neorealist Streets", region="Europe", origin="Italy · postwar cinema", tags=["honest", "melancholic", "hopeful"],
      genres=["folk", "acoustic", "indie"], bpm=(60, 110), energy="low",
      summary="Ordinary people, real streets, non-actors' faces; hardship and warmth side by side.",
      camera="Handheld at eye level, real locations, deep focus.", light="Natural daylight, black-and-white or muted colour.",
      palette=["black and white", "stone", "faded blue"], editing="Plain, observational.",
      movement="Work, walking, family life.", design="Working-class streets, bicycles, laundry lines.", look="live-action", acting="natural",
      avoid="Aestheticising poverty.", respect="Dignity first."),
    D(id="uk-garage-grime", name="UK Estates & Grime", region="Europe", origin="UK · grime and drill video", tags=["confident", "gritty", "energetic"],
      genres=["grime", "drill", "uk garage", "hip-hop"], bpm=(130, 145), energy="high",
      summary="Crews on the block, fisheye close-ups, tracksuits and council-estate architecture.",
      camera="Fisheye close to lens, low-angle crew shots, tracking through walkways.", light="Flat daylight, sodium night, car headlights.",
      palette=["concrete grey", "black", "one bold colour"], editing="Hard cuts on bars; stutter edits.",
      movement="Bar delivery to camera, crew energy, skanking.", design="Estates, chicken shops, tracksuits.", look="live-action", acting="energetic",
      avoid="Glamorising violence.", respect="Work with the scene, not about it."),
    D(id="soviet-montage", name="Constructivist Montage", region="Europe", origin="Soviet 1920s montage", tags=["epic", "rebellious", "powerful"],
      genres=["industrial", "electronic", "rock", "orchestral"], bpm=(100, 160), energy="high",
      summary="Collision editing, diagonals, machines and crowds; graphic, rhythmic and bold.",
      camera="Extreme low angles, diagonals, graphic close-ups.", light="High contrast, hard sun, deep blacks.",
      palette=["red", "black", "cream"], editing="Rhythmic montage: images collide on the beat.",
      movement="Marching crowds, machines, workers in rhythm.", design="Factories, typography-inspired graphics.", look="live-action", acting="dramatic",
      avoid="Real propaganda symbols.", respect="Keep it graphic, not political endorsement."),
    D(id="flamenco-duende", name="Flamenco Duende", region="Europe", origin="Spain · Andalusian flamenco film", tags=["passionate", "dramatic", "intense"],
      genres=["flamenco", "latin", "ballad"], bpm=(80, 140), energy="mid",
      summary="Heat, stamping heels, clapping circles and faces full of feeling in whitewashed courtyards.",
      camera="Low angles on feet, circling dollies, tight faces.", light="Hard sun and shadow; candlelit tablao at night.",
      palette=["blood red", "black", "whitewash", "gold"], editing="Cut on the palmas; hold the singer.",
      movement="Flamenco footwork, arms, clapping circles.", design="Courtyards, tablaos, ruffled dresses, fitted jackets.", look="live-action", acting="dramatic",
      avoid="Costume caricature.", respect="Flamenco is Gitano/Andalusian heritage; credit and consult artists."),
    # ---------------- Americas
    D(id="latin-reggaeton", name="Reggaetón Heat", region="Americas", origin="Puerto Rico / Latin urban video", tags=["sensual", "party", "confident"],
      genres=["reggaeton", "dembow", "latin pop"], bpm=(88, 100), energy="high",
      summary="Beach-to-club heat: bright sun, flashy cars, perreo crowds and bold colour.",
      camera="Slow-motion hero walks, low angles, orbiting gimbal.", light="Tropical sun, neon night, coloured haze.",
      palette=["hot pink", "turquoise", "sunset orange"], editing="Dembow rhythm cuts, speed ramps.",
      movement="Perreo, group dance, confident struts.", design="Beaches, block parties, streetwear.", look="live-action", acting="energetic",
      avoid="Objectifying framing.", respect="Keep performers empowered and consenting."),
    D(id="telenovela-gloss", name="Telenovela Gloss", region="Americas", origin="Latin American telenovela", tags=["dramatic", "romantic", "emotional"],
      genres=["bolero", "ballad", "latin pop"], bpm=(60, 100), energy="mid",
      summary="Glossy passion: mansions, secret letters, slaps and tears in soft focus.",
      camera="Slow push-ins to faces, dramatic zooms, over-shoulder confrontations.", light="Soft glamour light, candlelight, storms.",
      palette=["wine red", "cream", "gold"], editing="Hold the reaction; cliffhanger freeze.",
      movement="Embraces, turns away, letters and rings.", design="Haciendas, ballrooms, elegant dress.", look="live-action", acting="dramatic",
      avoid="", respect="Heightened but sincere."),
    D(id="brazil-carnival", name="Carnaval Colour", region="Americas", origin="Brazil · carnival and baile", tags=["joyful", "celebratory", "energetic"],
      genres=["samba", "funk carioca", "baile funk", "pop"], bpm=(95, 140), energy="high",
      summary="Streets exploding with colour, drums, feathers and friends dancing until sunrise.",
      camera="Handheld in parades, overhead drum lines, close-ups of joy.", light="Midday sun, festival lights at night.",
      palette=["green", "yellow", "electric pink", "feather white"], editing="Drum-driven cutting, fast montage.",
      movement="Samba steps, passinho, parade formations.", design="Samba-school costume (as craft), favela hills, beaches.", look="live-action", acting="energetic",
      avoid="Sexualised tourism framing.", respect="Credit samba schools and communities."),
    D(id="mexican-magic-realism", name="Magic Realism", region="Americas", origin="Latin American literature and cinema", tags=["mystical", "nostalgic", "whimsical"],
      genres=["folk", "latin alternative", "ballad"], bpm=(60, 110), energy="low",
      summary="The impossible told plainly: butterflies from letters, the dead at the dinner table, rain that lasts for years.",
      camera="Calm, observational frames where wonders happen without comment.", light="Warm adobe interiors, marigold afternoons, candle nights.",
      palette=["marigold", "cobalt", "terracotta", "papel-picado colours"], editing="Unhurried; wonders appear in the cut.",
      movement="Daily life that bends into the fantastic.", design="Courtyards, family altars, village streets.", look="painterly", acting="natural",
      avoid="Using Día de Muertos as mere decoration.", respect="Research the meaning of altars and rituals you show."),
    D(id="hip-hop-90s", name="90s Hip-Hop Video", region="Americas", origin="USA · golden-era rap video", tags=["confident", "gritty", "nostalgic"],
      genres=["hip-hop", "boom bap", "r&b"], bpm=(80, 100), energy="mid",
      summary="Fisheye lenses, stoops and block parties, crews and B-boys, film grain and swagger.",
      camera="Fisheye, low angle, handheld through the crowd.", light="Daylight on the block, club spotlights, film grain.",
      palette=["denim blue", "timberland tan", "brick red"], editing="Cut on the snare; scratch stutters.",
      movement="Head nods, B-boying, crew shots.", design="Brownstones, basketball courts, baggy denim.", look="live-action", acting="energetic",
      avoid="", respect="Nod to the culture's originators."),
    D(id="americana-road", name="Americana Road Movie", region="Americas", origin="USA · road movie", tags=["nostalgic", "free", "melancholic", "hopeful"],
      genres=["country", "folk", "rock", "americana"], bpm=(70, 130), energy="mid",
      summary="Open highways, diners, motel neon and dust; freedom and loneliness in wide screen.",
      camera="Car-mount shots, wide deserts, dolly along the highway.", light="Golden hour, motel neon, dashboard glow.",
      palette=["dusty orange", "faded denim", "neon pink"], editing="Montage of miles; hold the horizon.",
      movement="Driving, walking the shoulder, dancing at a roadside bar.", design="Pickup trucks, diners, gas stations, boots.", look="live-action", acting="natural",
      avoid="", respect=""),
    D(id="caribbean-dancehall", name="Dancehall Yard", region="Americas", origin="Jamaica · dancehall video", tags=["party", "confident", "joyful"],
      genres=["dancehall", "reggae", "soca"], bpm=(90, 110), energy="high",
      summary="Sound systems, yard dances, bright colour and signature steps from the crowd.",
      camera="Handheld dance circles, low wides of speaker stacks.", light="Sunset, string lights, sound-system glow.",
      palette=["green", "gold", "black", "sunset red"], editing="Cut on the riddim accents.",
      movement="Dancehall steps and crews.", design="Yards, sound systems, streetwear.", look="live-action", acting="energetic",
      avoid="Parodying patois or dance.", respect="Work with dancers from the scene."),
    # ---------------- Oceania & global
    D(id="aboriginal-country", name="Country and Sky", region="Oceania", origin="Australian First Nations filmmaking (with permission)",
      tags=["spiritual", "contemplative", "proud"], genres=["folk", "hip-hop", "ambient"], bpm=(60, 110), energy="low",
      summary="Land as a living presence: red earth, vast sky, family and continuity told from within.",
      camera="Grounded wides, aerials of country, intimate family close-ups.", light="Hard outback sun, fire at night, star fields.",
      palette=["red ochre", "sky blue", "white", "charcoal"], editing="Patient, respectful pacing.",
      movement="Walking country, family gatherings.", design="Contemporary life on country.", look="live-action", acting="natural",
      avoid="Using sacred designs, dot-painting imitation, or depicting deceased people without consent.",
      respect="Only with First Nations collaborators and community permission."),
    D(id="pacific-island", name="Ocean Voyager", region="Oceania", origin="Pacific Island storytelling", tags=["hopeful", "epic", "joyful"],
      genres=["island reggae", "pop", "choral"], bpm=(80, 120), energy="mid",
      summary="Ocean, canoes, family and song: horizons as home, not the edge of the world.",
      camera="Water-level shots, drone over reefs, group singing circles.", light="Tropical clarity, sunset gold, starlit navigation.",
      palette=["lagoon turquoise", "coral", "sand", "deep ocean blue"], editing="Swells with the chorus.",
      movement="Paddling, group song and dance.", design="Canoes, villages, contemporary island life.", look="live-action", acting="expressive",
      avoid="Tiki kitsch; using tattoos (tatau, tā moko) as decoration.", respect="Tattoo designs are personal and sacred; collaborate."),
    D(id="black-and-white-poem", name="Black-and-White Poem", region="Global", origin="International art cinema", tags=["melancholic", "intimate", "contemplative"],
      genres=["ballad", "acoustic", "classical", "indie"], bpm=(50, 100), energy="low",
      summary="Faces, hands and light in monochrome; every frame a photograph.",
      camera="Static portraits, slow dollies, shallow focus.", light="Single hard key, deep shadows, window light.",
      palette=["black", "white", "silver"], editing="Very few cuts; cut on breath.",
      movement="Minimal; the smallest gesture matters.", design="Bare rooms, textures, weather.", look="live-action", acting="restrained",
      avoid="", respect=""),
    D(id="one-take", name="One-Take Performance", region="Global", origin="Music video tradition", tags=["intimate", "raw", "energetic"],
      genres=["any"], bpm=(60, 180), energy="mid",
      summary="The whole song as one continuous move around the performer: no cuts, pure presence.",
      camera="A single unbroken Steadicam or gimbal move that reveals the world as the song builds.", light="Practicals that change as the camera travels.",
      palette=["depends on the location"], editing="None; transitions happen inside the shot.",
      movement="Performer walks and sings to camera through a changing space.", design="A route through connected spaces.", look="live-action", acting="natural",
      avoid="", respect="", continuous=True),
    D(id="stop-motion-handmade", name="Handmade Stop Motion", region="Global", origin="Craft animation tradition", tags=["whimsical", "gentle", "playful"],
      genres=["indie", "folk", "pop"], bpm=(80, 130), energy="mid",
      summary="Felt, clay and paper worlds built by hand; visible fingerprints and charm.",
      camera="Miniature-scale moves, macro detail.", light="Soft practical light on sets, tiny lamps.",
      palette=["pastel felt", "kraft paper", "primary accents"], editing="On the beat, playful loops.",
      movement="Jerky charm, cardboard waves, handmade weather.", design="Miniature rooms, paper cities.", look="stop-motion", acting="expressive",
      avoid="", respect="Credit the makers."),
]
FIELDS = ("summary", "camera", "light", "editing", "movement", "design")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _user() -> list[dict]:
    return [{**x, "custom": True} for x in (_read(USER_LIB, {}) or {}).get("directions", [])]


def all_directions() -> list[dict]:
    out = []
    for x in LIBRARY + _user():
        out.append({**x, "bpm": list(x.get("bpm") or (60, 180))})
    return out


def _song(d: str) -> dict:
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    curve = [v for _, v in sm.get("energy_curve") or []]
    energy = sum(curve) / len(curve) if curve else 0.5
    moods = [str(s.get("mood") or "").lower() for s in sm.get("sections") or []]
    lyrics = " ".join(l.get("text", "") for l in sm.get("lyrics") or [] if isinstance(l, dict)).lower()
    return {"bpm": float(sm.get("bpm") or 0), "energy": energy, "moods": moods, "lyrics": lyrics}


MOOD_WORDS = {
    "intimate": ["intimate", "melancholic", "romantic", "contemplative", "gentle", "lonely"],
    "tender": ["romantic", "gentle", "intimate"], "uplifting": ["hopeful", "joyful", "triumphant"],
    "energetic": ["energetic", "party", "confident"], "euphoric": ["joyful", "celebratory", "party"],
    "dark": ["dark", "tense", "gritty"], "tense": ["tense", "dark", "dramatic"], "sad": ["melancholic", "lonely"],
    "epic": ["epic", "triumphant", "powerful"], "dreamy": ["dreamy", "mystical", "whimsical"],
}


def match(d: str, limit: int = 6) -> dict:
    """Rank directions for this song: tempo fit, energy fit and mood words. Free; no AI."""
    s = _song(d)
    level = "low" if s["energy"] < 0.35 else "high" if s["energy"] > 0.6 else "mid"
    want = []
    for m in s["moods"]:
        for k, words in MOOD_WORDS.items():
            if k in m:
                want += words
    ranked = []
    for x in all_directions():
        lo, hi = x["bpm"]
        bpm = s["bpm"]
        feel = "" if lo <= bpm <= hi else " (half-time feel)" if lo <= bpm / 2 <= hi else " (double-time feel)" if lo <= bpm * 2 <= hi else None
        tempo = 1.0 if feel == "" else 0.8 if feel else max(0.0, 1 - min(abs(bpm - lo), abs(bpm - hi)) / 40)
        en = 1.0 if x.get("energy") == level else 0.5 if "mid" in (x.get("energy"), level) else 0.0
        mood = min(1.0, sum(want.count(t) for t in x.get("tags", [])) / max(1, len(s["moods"])))
        score = round(tempo * 0.4 + en * 0.3 + mood * 0.3, 3)
        why = []
        if feel is not None:
            why.append(f"tempo {round(bpm)} BPM fits{feel}")
        if en >= 1:
            why.append(f"{level} energy")
        hit = [t for t in x.get("tags", []) if t in want]
        if hit:
            why.append("mood: " + ", ".join(hit[:3]))
        ranked.append({"id": x["id"], "score": score, "why": why})
    ranked.sort(key=lambda r: -r["score"])
    return {"song": {"bpm": round(s["bpm"]), "energy": level, "moods": sorted(set(m for m in s["moods"] if m))},
            "matches": ranked[:limit]}


def brief(x: dict) -> str:
    parts = [f"Creative direction: {x['name']} ({x['origin']}). {x['summary']}",
             f"Camera: {x['camera']}", f"Light: {x['light']}", f"Palette: {', '.join(x['palette'])}.",
             f"Editing: {x['editing']}", f"Movement: {x['movement']}", f"Design: {x['design']}"]
    if x.get("avoid"):
        parts.append(f"Avoid: {x['avoid']}")
    if x.get("respect"):
        parts.append(f"With care: {x['respect']}")
    return "\n".join(parts)


def apply(d: str, did: str, parts: list[str] | None = None, overwrite: bool = False) -> dict:
    """Use a direction for a project. parts: brief, bible, look, acting (default all). Your own settings are kept
    unless overwrite is true."""
    x = next((y for y in all_directions() if y["id"] == did), None)
    if not x:
        raise SystemExit("That direction isn't in the library.")
    parts = parts or ["brief", "bible", "look", "acting"]
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    changed = []
    filled = dict((p.get("direction") or {}).get("filled") or {})   # what earlier directions wrote

    def mine(key, value):   # the user's own value: set, and not what a direction put there
        return bool(value) and filled.get(key) != value
    new_filled = {}
    if "brief" in parts:
        ob = dict(p.get("onboarding") or {"stage": "done"})   # no setup wizard in progress: never start one
        notes = ob.get("concept_notes") or ""
        notes = re.sub(r"(?s)Creative direction: .*?(?=\n\n|\Z)", "", notes).strip()   # replace an earlier library direction
        ob["concept_notes"] = (brief(x) + ("\n\n" + notes if notes else ""))[:2000]
        ob["direction_id"] = x["id"]
        p["onboarding"] = ob
        changed.append("brief for the directions and treatment")
    if "bible" in parts:
        b = dict(p.get("bible") or {})
        new = {"world": f"{x['summary']} {x['design']}", "palette": ", ".join(x["palette"]), "avoid": x.get("avoid", "")}
        for k, v in new.items():
            if not v and b.get(k) and filled.get(f"bible.{k}") == b.get(k):
                b[k] = ""   # the earlier direction's entry, and this one has none
                continue
            if v and (overwrite or not mine(f"bible.{k}", b.get(k))):
                b[k] = v[:1500]
                new_filled[f"bible.{k}"] = b[k]
                changed.append(f"bible: {k}")
        b.setdefault("rules", "")
        p["bible"] = b
    if "look" in parts and x.get("look"):
        cur = p.get("look")
        style = cur.get("style") if isinstance(cur, dict) else cur
        if overwrite or not style or style == "auto" or not mine("look", style):
            p["look"] = {**(cur if isinstance(cur, dict) else {}), "style": x["look"]}
            new_filled["look"] = x["look"]
            changed.append(f"look: {x['look']}")
    if "acting" in parts and x.get("acting"):
        perf = dict(p.get("performance") or {})
        if overwrite or not mine("acting", perf.get("default")):
            perf["default"] = x["acting"]
            new_filled["acting"] = x["acting"]
            perf.setdefault("scenes", {}), perf.setdefault("characters", {}), perf.setdefault("shots", {})
            p["performance"] = perf
            changed.append(f"acting: {x['acting']}")
    p["direction"] = {"id": x["id"], "name": x["name"], "applied": int(time.time()), "filled": {**filled, **new_filled}}
    cur = _read(path, {})   # keep anything written meanwhile
    cur.update({k: p[k] for k in ("onboarding", "bible", "look", "performance", "direction") if k in p})
    _write(path, cur)
    return {"applied": x["id"], "name": x["name"], "changed": changed}


def save(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name or not (data.get("summary") or "").strip():
        raise SystemExit("A direction needs a name and a summary.")
    lib = _read(USER_LIB, {}) or {}
    items = lib.get("directions", [])
    did = "my-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    entry = {"id": did, "name": name[:60], "region": "My directions", "origin": (data.get("origin") or "My own").strip()[:80],
             "tags": [t.strip().lower() for t in (data.get("tags") or []) if t.strip()][:8], "genres": [], "bpm": data.get("bpm") or [60, 180],
             "energy": data.get("energy") if data.get("energy") in ("low", "mid", "high") else "mid",
             "palette": [c.strip() for c in (data.get("palette") or []) if c.strip()][:6] or ["—"],
             "look": data.get("look") or "", "acting": data.get("acting") or "", "avoid": data.get("avoid") or "", "respect": ""}
    for f in FIELDS:
        entry[f] = (data.get(f) or "").strip()[:600] or "—"
    items = [i for i in items if i["id"] != did] + [entry]
    _write(USER_LIB, {"directions": items})
    return {"saved": did}


def delete(did: str) -> dict:
    lib = _read(USER_LIB, {}) or {}
    lib["directions"] = [i for i in lib.get("directions", []) if i["id"] != did]
    _write(USER_LIB, lib)
    return {"deleted": did}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-directions")
    ap.add_argument("action", choices=["list", "match", "apply", "save", "delete"])
    ap.add_argument("project", nargs="?")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "list":
            p = _read(os.path.join(a.project, "project.json"), {}) if a.project else {}
            res = {"directions": all_directions(), "current": (p.get("direction") or {}).get("id")}
        elif a.action == "match":
            res = match(a.project)
        elif a.action == "apply":
            res = apply(a.project, x["id"], x.get("parts"), bool(x.get("overwrite")))
        elif a.action == "save":
            res = save(x)
        else:
            res = delete(x["id"])
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
