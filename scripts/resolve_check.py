"""Open a FilmCrafter hand-off folder in DaVinci Resolve (Studio, running, with external scripting on) and say what Resolve made of it.

  python scripts/resolve_check.py "<hand-off folder>"

It makes ONE new project named "FilmCrafter hand-off check <time>" (it never touches your other projects), imports the folder's clips into its media pool, then imports each timeline file
(Final Cut Pro XML, EDL, OpenTimelineIO) as a timeline and compares the clips and length Resolve shows with shots.json. Nothing is deleted.
"""
from __future__ import annotations

import json
import os
import sys
import time

MOD = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
os.environ.setdefault("RESOLVE_SCRIPT_LIB", r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll")
sys.path.append(MOD)
import DaVinciResolveScript as dvr  # noqa: E402


def main(folder: str) -> int:
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        print("Could not reach Resolve. Open it, then Preferences > System > General > External scripting using: Local.")
        return 2
    print("Resolve", resolve.GetVersionString())
    pm = resolve.GetProjectManager()
    name = time.strftime("FilmCrafter hand-off check %Y-%m-%d %H%M%S")
    proj = pm.CreateProject(name)
    if not proj:
        print("Could not create a project (is a dialog open in Resolve?).")
        return 2
    print("project:", name)
    manifest = json.load(open(os.path.join(folder, "shots.json"), encoding="utf-8"))
    shots = manifest["shots"] if isinstance(manifest, dict) else manifest
    expected = [s for s in shots if s.get("take") or s.get("file") or s.get("media")]
    total = sum(float(s.get("seconds") or 0) for s in shots)
    print(f"manifest: {len(shots)} shots, {len(expected)} with a take, {total:.1f}s")
    pool = proj.GetMediaPool()
    media = os.path.join(folder, "media")
    items = pool.ImportMedia([os.path.join(media, f) for f in sorted(os.listdir(media))]) if os.path.isdir(media) else []
    print("media pool clips:", len(items or []))
    ok = True
    for ext, label in ((".fcpxml", "Final Cut Pro XML"), (".edl", "EDL"), (".otio", "OpenTimelineIO")):
        files = [f for f in os.listdir(folder) if f.lower().endswith(ext)]
        if not files:
            print(f"{label}: no file")
            continue
        path = os.path.join(folder, files[0])
        tl = pool.ImportTimelineFromFile(path, {"timelineName": f"{label}", "importSourceClips": False})
        if not tl:
            print(f"{label}: Resolve could NOT import {files[0]}")
            ok = False
            continue
        fps = tl.GetSetting("timelineFrameRate")
        v = tl.GetTrackCount("video")
        a = tl.GetTrackCount("audio")
        clips = [c for t in range(1, v + 1) for c in tl.GetItemListInTrack("video", t)]
        start, end = tl.GetStartFrame(), tl.GetEndFrame()
        secs = (end - start) / float(fps or 24)
        names = [c.GetName() for c in clips]
        print(f"{label}: imported '{tl.GetName()}': {len(clips)} video clips on {v} track(s), {a} audio track(s), {secs:.1f}s at {fps} fps")
        print("   clips:", ", ".join(names[:8]) + (" …" if len(names) > 8 else ""))
        if len(clips) != len(expected):
            print(f"   !! expected {len(expected)} clips")
            ok = False
        if total and abs(secs - total) > max(1.0, total * 0.05):
            print(f"   !! expected about {total:.1f}s")
            ok = False
    pm.SaveProject()
    print("RESULT:", "Resolve reads the hand-off as written." if ok else "differences found (above).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
