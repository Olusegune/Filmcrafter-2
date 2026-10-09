"""Does the Demucs split in shotsound.split() keep speech apart from effects and music? Measured, not listened to.

Speech is Windows' own speech synthesizer (two voices); effects (bangs, clinks) and music (a chord) are synthetic. They are mixed at known levels, the mix is made into a
take, split, and each stem is compared with the clean sources. This is a stand-in for a video model's sound, not a recording of a person and not a model's output: treat the
numbers as a floor check that the separation works on speech at all, not as a promise for every take.

Run it (Windows, from the analysis folder):  python -m tests.speech_check
Numbers are squared correlations: 1.0 means the stem is exactly that source, 0.0 means none of it is there.
"""
import json
import os
import shutil
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from filmcrafter_engine import export as E, shotsound as SS

RATE = 44100
LINES = {"Microsoft David Desktop": "I told you I would come back. Nobody believed me, but here I am, standing at your door.",
         "Microsoft Zira Desktop": "Then you should have knocked. We were all waiting for you, and the lights were never off."}


def available() -> bool:
    """True where the speech synthesizer and the separator both exist (Windows with its speech voices, and Demucs)."""
    try:
        import demucs  # noqa: F401
    except ImportError:
        return False
    if os.name != "nt":
        return False
    p = subprocess.run(["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices().Count"],
                       capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip().isdigit() and int(p.stdout.strip()) > 0


def tts(voice: str, text: str, out: str) -> None:
    ps = (f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('{voice}'); "
          f"$s.SetOutputToWaveFile('{out}'); $s.Speak('{text}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def load_mono(path: str, n: int | None = None):
    r = subprocess.run([E.ffmpeg(), "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(RATE), "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    return x[:n] if n else x


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) + 1e-12


def music(n: int):
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for f in (220.0, 261.63, 329.63, 110.0):
        for h, a in ((1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15)):
            out += a * np.sin(2 * np.pi * f * h * t)
    out *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t)
    return (out / np.max(np.abs(out))).astype(np.float32)


def sfx(n: int, rng):
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for at in (1.2, 3.8, 6.1):                                           # three bangs: low-passed noise with a fast decay
        i = int(at * RATE)
        m = min(n - i, int(0.7 * RATE))
        env = np.exp(-np.arange(m) / (0.12 * RATE))
        out[i:i + m] += env * np.convolve(rng.standard_normal(m), np.ones(40) / 40, mode="same") * 4
    for at in (2.4, 5.2):                                                # two bright clinks
        i = int(at * RATE)
        m = min(n - i, int(0.5 * RATE))
        env = np.exp(-np.arange(m) / (0.08 * RATE))
        out[i:i + m] += env * (np.sin(2 * np.pi * 3100 * t[:m]) + 0.5 * np.sin(2 * np.pi * 4700 * t[:m]))
    return (out / np.max(np.abs(out))).astype(np.float32)


def explained(a, b) -> float:
    """The share of b that a explains (squared correlation): 1.0 = a is b, 0.0 = nothing of b is in a."""
    n = min(len(a), len(b))
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
    return float((np.dot(a, b) ** 2) / ((np.dot(a, a) + 1e-12) * (np.dot(b, b) + 1e-12)))


def run(root: str, name: str, speech, bed, bed_db: float) -> dict:
    """One take made of `speech` and `bed` (the bed `bed_db` relative to the speech), split; what landed where."""
    n = max(len(speech), len(bed))
    s = np.zeros(n, np.float32)
    s[: len(speech)] = speech
    b = np.zeros(n, np.float32)
    b[: len(bed)] = bed
    if rms(b) > 1e-6 and rms(s) > 1e-6:
        b = b * (rms(s) / rms(b)) * 10 ** (bed_db / 20)
    mix = 0.5 * (s + b) / max(1e-6, np.max(np.abs(s + b)))
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "generations"))
    wav = os.path.join(d, "mix.wav")
    sf.write(wav, mix, RATE)
    clip = os.path.join(d, "generations", "t.mp4")
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={n / RATE:.2f}", "-i", wav, "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip], check=True)
    json.dump({"scenes": [{"number": 1, "heading": "INT.", "shots": [{"id": "S01-01", "start": 0.0, "end": n / RATE, "beats": ["a"], "performers": []}]}]}, open(os.path.join(d, "production.json"), "w"))
    json.dump({"title": "T", "song": "song.wav"}, open(os.path.join(d, "project.json"), "w"))
    json.dump({"duration": n / RATE, "lyrics": [], "sections": []}, open(os.path.join(d, "songmap.json"), "w"))
    sf.write(os.path.join(d, "song.wav"), np.zeros(n, np.float32), RATE)
    json.dump({"jobs": [{"id": "j1", "shot_id": "S01-01", "plan": "production", "state": "ready", "output": "generations/t.mp4", "created": 1, "kind": "video", "provider": "fal",
                         "model": "x"}]}, open(os.path.join(d, "jobs.json"), "w"))
    g = SS.split(d, "S01-01")
    assert g["split"], g
    work = os.path.join(d, "cache", "sound", SS.take_key(d, SS.take_for(d, "S01-01")))
    voice, other = load_mono(os.path.join(work, "voice.wav"), n), load_mono(os.path.join(work, "other.wav"), n)
    r: dict = {}
    if rms(s) > 1e-6:
        r["speech_kept_in_voice"] = explained(voice, s)                 # 1.0: the voice stem is the speech
        r["speech_leaked_to_other"] = explained(other, s)               # 0.0: none of the speech is in the effects stem
    if rms(b) > 1e-6:
        r["bed_kept_in_other"] = explained(other, b)
        r["bed_leaked_to_voice"] = explained(voice, b)
    r["voice_rms_db"] = round(20 * float(np.log10(rms(voice))), 1)
    r["other_rms_db"] = round(20 * float(np.log10(rms(other))), 1)
    return r


def speech_clips(root: str) -> dict:
    out = {}
    for voice, text in LINES.items():
        p = os.path.join(root, voice.split()[1].lower() + ".wav")
        tts(voice, text, p)
        out[voice.split()[1].lower()] = load_mono(p)
    return out


def main() -> dict:
    root = tempfile.mkdtemp(prefix="pf-speech-")
    rng = np.random.default_rng(7)
    sp = speech_clips(root)
    n = int(8.5 * RATE)
    bed = sfx(n, rng) * 0.7 + music(n) * 0.7
    results = {}
    for who in ("david", "zira"):
        results[f"{who}: speech with effects and music 6 dB under it"] = run(root, f"{who}_a", sp[who], bed, -6)
        results[f"{who}: speech with effects and music as loud as it"] = run(root, f"{who}_b", sp[who], bed, 0)
    results["speech only"] = run(root, "c", sp["david"], np.zeros(0, np.float32), 0)
    results["effects and music only (nobody speaks)"] = run(root, "d", np.zeros(0, np.float32), bed, 0)
    for k, v in results.items():
        print(k)
        for kk, vv in v.items():
            print(f"    {kk:26s} {vv:.3f}" if isinstance(vv, float) and not kk.endswith("_db") else f"    {kk:26s} {vv}")
    shutil.rmtree(root, ignore_errors=True)
    return results


if __name__ == "__main__":
    main()
