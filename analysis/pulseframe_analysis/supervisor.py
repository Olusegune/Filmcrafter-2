"""Production Supervisor: every quality finding in one queue, each with a decision.

Sources: the review of each shot's take in use, the keyframe check of each approved keyframe, continuity (free rules and
the AI cross-shot review), failed or uncertain renders, and shots still without a take. Each finding can be
Accepted (fine as it is), Ignored (not a problem), Fixed (re-render with the finding's correction) or Regenerated
(re-render as planned). Fix and Regenerate go through the normal queue, so the mode and the project budget apply,
and the app shows the price first. Decisions are kept in supervisor.json; a finding whose shot has moved on (a new take
or keyframe) is re-evaluated automatically.

  python -m pulseframe_analysis.supervisor <action> <project> --data '{...}'   actions: list | decide
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import sys
import time

SEV_ORDER = {"major": 0, "minor": 1, "info": 2}


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _id(*parts) -> str:
    return _sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _plan(d):
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []})


def collect(d: str) -> list[dict]:
    from .library import chosen_take, shot_state
    plan_name, plan = _plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    state = shot_state(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    shots = [s for sc in plan.get("scenes", []) for s in sorted(sc["shots"], key=lambda x: x["start"])]
    items = []

    def add(shot, source, severity, title, detail, fix, kind, basis, actions):
        items.append({"id": _id(source, shot, title, detail[:80], basis), "shot": shot, "source": source, "severity": severity,
                      "title": title, "detail": detail, "fix": fix, "kind": kind, "basis": basis, "actions": actions})

    no_take, unchecked = [], []
    for sh in shots:
        sid = sh["id"]
        if state.get(sid, {}).get("locked"):
            continue
        mine = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name]
        take = chosen_take(d, sid, plan_name, jobs, state)
        # 1. the take in use: its review
        if take and take.get("provider") != "own":
            rv = take.get("review") or {}
            if not rv.get("accepted"):
                for i in rv.get("issues") or []:
                    sev = "major" if i.get("severity") == "major" else "minor"
                    add(sid, "take review", sev, f"{(i.get('kind') or 'issue').replace('_', ' ').capitalize()} in the take",
                        i.get("detail", ""), i.get("fix", ""), "video", take["id"], ["accept", "ignore", "fix", "regenerate"])
                if rv.get("status") == "unchecked" or not rv.get("reviewed"):
                    unchecked.append(sid)
        # 2. the approved keyframe's check
        ref = kfs.get(sid)
        if isinstance(ref, str) and ref.startswith("project:"):
            kj = next((j for j in mine if j.get("kind") == "image" and j.get("output") == ref[8:]), None)
            sc = (kj or {}).get("still_check") or {}
            if sc.get("ok") is False:
                for p in sc.get("problems") or []:
                    sev = "major" if p.get("kind") in ("collage", "text", "identity", "missing") else "minor"
                    add(sid, "keyframe check", sev, f"Keyframe: {p.get('kind', 'problem')}", p.get("detail", ""), sc.get("fix", ""),
                        "image", kj["id"], ["accept", "ignore", "fix", "regenerate"])
        # 2b. the take was made from an older keyframe than the one approved now
        from .golden import is_stale
        if take and is_stale(d, take, ref if isinstance(ref, str) else None):
            add(sid, "keyframe changed", "minor", "Video made from an older keyframe",
                "The approved keyframe changed after this video was rendered, so the video doesn't match it.",
                "", "video", take["id"] + "|" + str(ref), ["accept", "ignore", "regenerate"])
        # 2c. lip-sync check of the take in use
        ls = (take or {}).get("lipsync_check") or {}
        if ls.get("verdict") == "off" and not (take.get("review") or {}).get("lipsync_accepted"):
            from .render import AUTO_LIPSYNC, _lipsync_provider
            lp = _lipsync_provider()
            add(sid, "lip-sync check", "major", "Mouth out of sync with the vocal", ls.get("detail", ""),
                ls.get("fix", "") or "Run a lip-sync pass on this take.", "lipsync", take["id"],
                ["accept", "ignore", "regenerate"] if lp else ["accept", "ignore"])
            items[-1]["render"] = {"provider": lp, "model": AUTO_LIPSYNC.get(lp)} if lp else None
        # 3. renders that failed or can't be confirmed
        latest = max(mine, key=lambda j: j["created"], default=None)
        if latest and latest["state"] in ("failed", "uncertain") and not (take and take["created"] > latest["created"]):
            from .diagnostics import RECOVERY
            kind = latest.get("error_kind") or "service"
            title = "Render failed" if latest["state"] == "failed" else "Render status unknown (it may have been charged)"
            add(sid, "renders", "major" if latest["state"] == "failed" else "minor", title, (latest.get("error") or "")[:400],
                RECOVERY.get(kind, ""), latest.get("kind", "video"), latest["id"],
                (["recheck"] if latest.get("provider_job_id") else []) + (["ignore", "regenerate"] if latest["state"] == "failed" else ["ignore"]))
        if not take and (sh.get("visual_prompt") or sh.get("beats") or sh.get("description")):
            no_take.append(sid)
    # 3b. stretches of the song no shot covers: the export fills them with black
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    if shots and sm.get("duration"):
        def clock(t):
            return f"{int(t // 60)}:{t % 60:04.1f}"
        timeline = sorted(((float(x["start"]), float(x["end"]), x["id"]) for x in shots), key=lambda t: t[0])
        cursor, prev_id = 0.0, timeline[0][2]
        gaps = []
        for st, en, sid in timeline:
            if st - cursor >= 1.0:
                gaps.append((cursor, st, prev_id if cursor > 0 else sid))
            cursor, prev_id = max(cursor, en), sid
        if float(sm["duration"]) - cursor >= 1.0:
            gaps.append((cursor, float(sm["duration"]), prev_id))
        from . import overlays as OV
        try:
            covers = sorted((o["start"], o["end"]) for o in OV.resolve(d) if o.get("placed") and o.get("enabled", True))
        except Exception:
            covers = []

        def covered(a, b):      # how much of a..b the on-screen text and pictures (titles, signs, logos) are up for
            total, cur = 0.0, a
            for s0, e0 in covers:
                lo, hi = max(s0, cur), min(e0, b)
                if hi > lo:
                    total += hi - lo
                    cur = hi
            return total
        for g0, g1, near in gaps:
            if covered(g0, g1) >= 0.8 * (g1 - g0):
                continue                      # a title card or logo fills it on purpose
            add(near, "timeline", "minor", f"Black stretch in the film: {clock(g0)} to {clock(g1)}",
                f"No shot covers {clock(g0)} to {clock(g1)} ({g1 - g0:.1f} s), so the export shows black there.",
                "Add a title card there (it fades in over the black), add a shot, or let the neighbouring shot start earlier or end later (it then needs a new render to fill the time).",
                "video", f"{g0:.2f}-{g1:.2f}", ["card", "title", "accept", "ignore"] if g0 < 0.05 and g1 - g0 >= 1.5 else ["accept", "ignore"])
    # 4. continuity
    try:
        from . import continuity
        if os.path.exists(os.path.join(d, "continuity.json")):
            for i in continuity.check(d)["issues"]:
                sev = "minor" if i.get("severity") == "warning" else "info"
                if i.get("source") == "ai" and i["kind"] in ("screen direction", "identity", "wardrobe"):
                    sev = "major"
                basis = (kfs.get(i["shot"]) or "") + "|" + i.get("source", "")
                add(i["shot"], f"continuity ({'AI' if i.get('source') == 'ai' else 'rules'})", sev,
                    f"Continuity: {i['kind']}", i["detail"], i.get("fix", ""), "image", basis,
                    ["accept", "ignore", "fix", "regenerate"] if i["kind"] not in ("blocking", "first frame") else ["accept", "ignore"])
    except Exception:
        pass
    # 4b. a PULSEFRAME Producer package import
    rep = (_read(os.path.join(d, "project.json"), {}) or {}).get("producer_import") or {}
    if rep:
        first = shots[0]["id"] if shots else "S01-01"
        for m in rep.get("missing_files") or []:
            add(first, "production package", "major",
                f"Missing file: {m.get('asset')}", f"The package names {m.get('file')} but it wasn't in the package.",
                "Add the image in the Reference library (Library → the item → Add files).", "image", "missing|" + str(m.get("file")), ["ignore"])
        for u in rep.get("unknown_refs") or []:
            add(first, "production package", "minor", f"Unknown reference {u.get('ref')}",
                f"{u.get('where')} refers to {u.get('ref')}, which isn't in the package.",
                "Add it to the Reference library, or ignore it.", "image", "ref|" + str(u.get("ref")) + str(u.get("where")), ["ignore"])
        if rep.get("untimed_shots"):
            add(first, "production package", "info", f"{len(rep['untimed_shots'])} shots placed by estimate",
                ", ".join(rep["untimed_shots"][:20]) + " had no time, lyric cue or song section; they share the time between their neighbours.",
                "Check their timing on the timeline.", "video", "untimed|" + ",".join(rep["untimed_shots"]), ["ignore"])
        if rep.get("readiness") and rep["readiness"] != "READY":
            add(first, "production package", "info", f"Producer marked the package {rep['readiness']}", rep.get("qa_report") or "",
                "", "video", "readiness|" + str(rep.get("at")), ["accept", "ignore"])
    # 5. coverage
    if unchecked:
        add(unchecked[0], "take review", "info", f"{len(unchecked)} take{'s' if len(unchecked) != 1 else ''} not visually checked",
            ", ".join(unchecked[:30]) + ("…" if len(unchecked) > 30 else ""),
            "Review runs automatically once the AI brain can see images (OpenAI, or a local vision model).",
            "video", ",".join(unchecked), ["ignore"])
    if no_take:
        add(no_take[0], "coverage", "info", f"{len(no_take)} shot{'s' if len(no_take) != 1 else ''} without a take",
            ", ".join(no_take[:30]) + ("…" if len(no_take) > 30 else ""), "Render them, or use moving stills (free).",
            "video", ",".join(no_take), ["ignore"])
    return items


def listing(d: str) -> dict:
    dec = _read(os.path.join(d, "supervisor.json"), {}) or {}
    jobs = {j["id"]: j for j in _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]}
    out = []
    for it in collect(d):
        dd = dec.get(it["id"])
        status = "open"
        if dd:
            status = dd["action"]
            if dd["action"] in ("fix", "regenerate"):
                states = [jobs.get(x, {}).get("state") for x in dd.get("jobs", [])]
                status = "working" if any(s in ("queued", "submitting", "submitted", "generating") for s in states) else \
                    "failed" if states and all(s == "failed" for s in states) else "done"
        out.append({**it, "status": status, "decision": dd})
    out.sort(key=lambda x: (x["status"] not in ("open", "failed"), SEV_ORDER[x["severity"]], x["shot"]))
    open_ = [x for x in out if x["status"] in ("open", "failed")]
    majors = sum(1 for x in open_ if x["severity"] == "major")
    return {"items": out, "groups": groups(out), "summary": {"open": len(open_), "major": majors, "minor": sum(1 for x in open_ if x["severity"] == "minor"),
                                      "info": sum(1 for x in open_ if x["severity"] == "info"),
                                      "decided": len(out) - len(open_), "ready": majors == 0}}


def decide(d: str, item_id: str, action: str, provider: str | None = None, model: str | None = None, note: str = "") -> dict:
    from .render import enqueue
    items = {i["id"]: i for i in collect(d)}
    it = items.get(item_id)
    if not it:
        raise SystemExit("That finding is no longer current; refresh the list.")
    path = os.path.join(d, "supervisor.json")
    if action == "reopen":   # undo a decision (renders already sent stay as they are)
        dec = _read(path, {}) or {}
        dec.pop(item_id, None)
        _write(path, dec)
        return listing(d)
    if action not in it["actions"]:
        raise SystemExit(f"'{action}' isn't available for this finding.")
    rec = {"action": action, "at": int(time.time()), "note": note[:300]}
    if action == "recheck":   # free: fetch a result the provider may already have finished
        from .render import resolve
        resolve(d, it["basis"], "recheck")
        rec["jobs"] = [it["basis"]]
    if action == "title":     # a title card over the black intro: the project's title, centred, fading in and out; edit it under Export > On-screen text
        from . import overlays as OV
        g0, g1 = (float(x) for x in str(it["basis"]).split("-"))
        proj = _read(os.path.join(d, "project.json"), {}) or {}
        text = " ".join(str(proj.get("title") or "Untitled").split())[:80]
        pad = min(0.4, (g1 - g0) / 6)
        OV.add(d, {"kind": "text", "text": text, "start": round(g0 + pad, 2), "end": round(g1 - pad, 2), "x": 0.5, "y": 0.5, "size": 0.09, "fade": 0.8})
        rec["title"] = text
    if action in ("fix", "regenerate"):
        if not provider:
            raise SystemExit("Choose which provider renders it.")
        notes = [it["fix"]] if action == "fix" and it["fix"] else []
        if it["kind"] == "lipsync":   # a lip-sync pass on the take itself
            made = enqueue(d, [it["shot"]], provider, model, {}, [], kind="lipsync", source_job=it["basis"])
        else:
            made = enqueue(d, [it["shot"]], provider, model, {}, notes, kind=it["kind"] if it["kind"] in ("image", "video") else "video")
        if not made:
            raise SystemExit("Nothing was queued (the shot may be locked, have no description, or already be rendering).")
        rec["jobs"] = [m["id"] for m in made]
        rec["provider"], rec["model"] = provider, made[0]["model"]
    elif action == "accept" and it["source"] == "lip-sync check":
        from .render import Store
        store = Store(d)
        j = next((x for x in store.jobs if x["id"] == it["basis"]), None)
        if j:
            store.update(j, review={**(j.get("review") or {}), "lipsync_accepted": True})
    elif action == "accept" and it["source"] == "take review":
        from .render import Store   # the take's review is accepted, so Review and Autopilot stop flagging it too
        store = Store(d)
        j = next((x for x in store.jobs if x["id"] == it["basis"]), None)
        if j:
            store.update(j, review={**(j.get("review") or {}), "accepted": True})
    dec = _read(path, {}) or {}
    dec[item_id] = rec
    _write(path, dec)
    return listing(d)


def groups(items: list[dict]) -> list[dict]:
    """Open findings of the same kind in the same scene, fixable as one priced batch (2 or more)."""
    by = {}
    for i in items:
        if i["status"] not in ("open", "failed") or not ({"fix", "regenerate"} & set(i["actions"])) or i["source"] == "coverage":
            continue
        scene = i["shot"].split("-")[0]
        by.setdefault((scene, i["title"], i["kind"]), []).append(i)
    out = []
    for (scene, title, kind), its in by.items():
        if len(its) >= 2:
            act = "fix" if all("fix" in x["actions"] for x in its) else "regenerate"
            out.append({"id": f"{scene}|{title}", "scene": scene.lstrip("S").lstrip("0") or scene, "title": title, "kind": kind,
                        "action": act, "items": [x["id"] for x in its], "shots": sorted({x["shot"] for x in its}),
                        "render": its[0].get("render")})
    out.sort(key=lambda g: (-len(g["items"]), g["id"]))
    return out


def decide_many(d: str, item_ids: list[str], action: str, provider: str | None = None, model: str | None = None) -> dict:
    """One decision for several findings. Paid batches are checked against the mode and budget as a whole first."""
    items = {i["id"]: i for i in collect(d)}
    chosen = [items[i] for i in item_ids if i in items]
    if not chosen:
        raise SystemExit("Those findings are no longer current; refresh the list.")
    if action in ("fix", "regenerate"):
        from .routing import guard
        kind = chosen[0]["kind"] if chosen[0]["kind"] in ("image", "video", "lipsync") else "video"
        guard(d, sorted({i["shot"] for i in chosen}), provider, model, kind)
    done, skipped = [], []
    for it in chosen:
        try:
            decide(d, it["id"], action, provider, model)
            done.append(it["shot"])
        except SystemExit as e:
            skipped.append({"shot": it["shot"], "reason": str(e)})
    res = listing(d)
    res["batch"] = {"done": done, "skipped": skipped}
    return res


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-supervisor")
    ap.add_argument("action", choices=["list", "decide", "decide_many"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "list":
            res = listing(a.project)
        elif a.action == "decide_many":
            res = decide_many(a.project, x["items"], x["action"], x.get("provider"), x.get("model"))
        else:
            res = decide(a.project, x["item"], x["action"], x.get("provider"), x.get("model"), x.get("note", ""))
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
