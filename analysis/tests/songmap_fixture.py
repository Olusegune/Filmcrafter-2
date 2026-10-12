"""A song map for a test song, written directly: a steady beat, a bar every two seconds, one section. (The engine no longer listens to songs; films build their own timeline.)"""
import json
import os

import soundfile as sf


def write(d: str, song: str = "song.wav", bpm: float = 120.0) -> dict:
    info = sf.info(os.path.join(d, song))
    dur = round(info.frames / info.samplerate, 3)
    beat = 60.0 / bpm
    beats = [round(i * beat, 3) for i in range(int(dur / beat) + 1)]
    sm = {"duration": dur, "bpm": bpm, "beats": beats, "downbeats": beats[::4], "energy_curve": [], "accents": [],
          "sections": [{"start": 0.0, "end": dur, "label": "Verse", "group": "Verse", "energy": 0.5, "mood": ""}], "lyrics": [], "lyric_match": None, "analyzer": "test"}
    json.dump(sm, open(os.path.join(d, "songmap.json"), "w"))
    return sm
