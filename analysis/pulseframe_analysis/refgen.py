"""Make the reference pictures a package only described.

A Producer package (or any project) can list characters, outfits, props and places that have a written spec but no picture, or a
character who appears only in a group lineup. Models then have nothing to look at for them. This turns the spec's own image
prompt (the "VISUAL GENERATION PROMPT" / "PROMPT" section the plugin writes) into a picture with an image model, after the user has
seen the price and confirmed it.

  candidates  what is missing, with the prompt each picture would use and what it would be shown for consistency
  estimate    what making them would cost on a chosen model
  queue       create image jobs (needs confirmed=True); the render runner sends them like any other image job
  use         attach a finished picture to its reference item (nothing changes until the user chooses it)
  discard     drop a finished picture without using it
  cards       every picture of the production as one card (yours, approved, waiting for approval, missing), for the Pictures step
  own         use a picture of your own for a card instead of making one

A card can be made again with a plain-language change ("older, warmer"): the current picture is shown to the model so the design holds.
Props and dance sheets are shown their owner's approved character sheet, so they match the person. Dance sheets (id choreo_*) come from
an in-app plan and, once chosen, join the project's choreography files.

Money and safety: nothing is queued without confirmed=True, a batch is capped, Local First and the project budget are respected,
prompts are length-limited text (never run, never put in a path), a downloaded picture must open as a real image before it is
offered, and generated files stay in the project's generations folder until the user chooses one.

  python -m pulseframe_analysis.refgen <candidates|estimate|queue|use|discard|status> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid

MAX_BATCH = 40
MAX_PROMPT = 1500
MAX_NOTE = 300
CHOREO = "choreo_"
SAFE_ID = re.compile(r"[a-z0-9_]{1,60}")
VISUAL = ("character", "wardrobe", "prop", "set")
ASPECT = {"character": ("3:2", "4:3", "1:1"), "wardrobe": ("3:2", "4:3", "1:1"), "prop": ("1:1", "4:3", "3:2"), "set": ("16:9", "3:2", "4:3"), "choreo": ("3:2", "16:9", "4:3")}
NO_TEXT = " No text, labels, captions, logos or watermarks anywhere in the picture."
PLAIN = {"character": " Plain light neutral background.", "wardrobe": " Plain light neutral background.", "prop": " Plain white background.",
         "set": " No people.", "choreo": " Plain light neutral background."}
SECTION = re.compile(r"(?im)^[ \t]*(?:visual generation prompt|image prompt|generation prompt|prompt)[ \t]*:?[ \t]*\n+(.+?)(?:\n[ \t]*\n|\Z)", re.S)


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _inside(d: str, path: str) -> bool:
    base, p = os.path.normcase(os.path.realpath(d)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([base, p]) == base
    except ValueError:
        return False


def _images(d: str, item: dict) -> list[str]:
    from .library import media_kind
    return [f for f in item.get("files") or [] if media_kind(f) == "image" and os.path.exists(os.path.join(d, f))]


def spec_prompt(d: str, item: dict) -> str | None:
    """The image prompt the plugin wrote into one of the item's own text files (its spec), or None. Only .md/.txt files inside the
    project are read, and only the first paragraph under a PROMPT heading."""
    for f in item.get("files") or []:
        if not f.lower().endswith((".md", ".txt")):
            continue
        path = os.path.join(d, f)
        if not (os.path.isfile(path) and _inside(d, path) and os.path.getsize(path) <= 200_000):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        m = SECTION.search(text)
        if m:
            return " ".join(m.group(1).split())
    return None


def _built_prompt(project: dict, item: dict) -> str:
    """When there is no written prompt: a sheet description from the item's own name and rules, in the project's look."""
    from .render import resolve_look
    look = ""
    try:
        look = (project.get("look") or {}).get("notes") or ""
    except AttributeError:
        pass
    name, kind = item["name"], item["kind"]
    facts = "; ".join(item.get("locked_rules") or []) or (item.get("notes") or "")
    what = {"character": f"Character sheet of {name} on a white background: full-body front, three-quarter, side and back views, a close face view and "
                         "six expressions. Same identity and scale in every view.",
            "wardrobe": f"Outfit sheet for {name}: front and back views, laid out on a plain background.",
            "prop": f"Prop reference sheet: {name}. Front, side and three-quarter views with a simple scale cue.",
            "set": f"Establishing view of the place: {name}, the whole room or location, lit as in the story."}[kind]
    return " ".join(x for x in (look.strip(), what, f"Design, keep exactly: {facts}." if facts else "") if x)


def _clip(text: str) -> str:
    return " ".join(str(text).split())[:MAX_PROMPT]


def _note(notes: dict | None, key: str) -> str:
    n = " ".join(str((notes or {}).get(key) or "").split())[:MAX_NOTE]
    return f" Change from the current version: {n}." if n else ""


def _own_picture(d: str, it: dict | None, use_count: dict) -> bool:
    """True when the item has a picture that is its own (a lineup shared with other characters does not count)."""
    imgs = _images(d, it) if it else []
    return bool(imgs) and not (it.get("kind") == "character" and all(use_count.get(f, 0) > 1 for f in imgs))


def _retire_others(store, asset_id: str, keep: str | None) -> None:
    """When a picture is chosen, the one it replaces stops being 'in use' and every other unchosen result for the card is put away."""
    for o in store.jobs:
        if o.get("kind") == "asset" and o.get("asset_id") == asset_id and o["id"] != keep and o["state"] not in ("queued", "submitting", "submitted"):
            store.update(o, used=False, replaced=True)


def _generated_ids(d: str) -> set[str]:
    from .library import load
    _, lib = load(d)
    return {i["id"] for i in lib.get("items") or [] if i.get("generated_from_spec")}


def _choreo_sheets(d: str) -> list[dict]:
    """The dance sheets an in-app plan calls for: one eight-panel sheet per dancer, built from the plan's own moves."""
    from .producer_import import DANCE
    a = (_read(os.path.join(d, "producer", "plan.json"), {}) or {}).get("assets") or {}
    people = {c.get("id"): c for c in a.get("characters") or []}
    out = []
    for e in a.get("choreography") or []:
        c, moves = people.get(e.get("character_id")), [m for m in e.get("moves") or [] if isinstance(m, dict)]
        if not (c and moves and DANCE.search(str(e.get("classification") or "")) and SAFE_ID.fullmatch(str(e.get("id") or ""))):
            continue
        panels = " ".join(f"Panel {i}: {str(m.get('name') or '')[:50]}, {str(m.get('action') or '')[:150]}." for i, m in enumerate(moves[:8], 1))
        out.append({"id": CHOREO + e["id"], "name": f"{c.get('name', 'Dancer')}: dance sheet", "owner_ext": c.get("id"), "owner_name": c.get("name", ""),
                    "base": f"{a.get('visual_style', '')} Dance choreography sheet for {c.get('name', 'the dancer')}: {min(len(moves), 8)} pose panels in a grid on a plain light "
                            f"background, read left to right and top to bottom. {panels} Thin arrows show the direction of motion. The same dancer, outfit and build in every panel.".strip()})
    return out


def _sheet_picture(d: str, store, asset_id: str) -> str | None:
    """The chosen picture of a dance sheet (it is not a library item): the output of its in-use job."""
    j = next((x for x in store.jobs if x.get("kind") == "asset" and x.get("asset_id") == asset_id and x.get("used") and x.get("output")), None)
    return j["output"] if j and os.path.exists(os.path.join(d, j["output"])) else None


def candidates(d: str, redo: list[str] | tuple = (), notes: dict | None = None) -> list[dict]:
    """What is missing a picture: items with no picture at all, and characters who appear only in a picture shared with others.
    `redo` names pictures that were made here and are to be made again (with an optional note per picture); your own pictures are never offered."""
    from .library import load
    from .render import Store
    project, lib = load(d)
    items = lib.get("items") or []
    by_ext = {i.get("external_id"): i for i in items if i.get("external_id")}
    use_count: dict[str, int] = {}
    for it in items:
        if it.get("kind") == "character":
            for f in _images(d, it):
                use_count[f] = use_count.get(f, 0) + 1
    out = []
    for it in items:
        kind = it.get("kind")
        if kind not in VISUAL or it.get("from_show"):
            continue
        imgs = _images(d, it)
        shared = kind == "character" and bool(imgs) and all(use_count.get(f, 0) > 1 for f in imgs)
        again = it["id"] in redo and bool(imgs) and not shared and bool(it.get("generated_from_spec"))
        if imgs and not shared and not again:
            continue
        owner = by_ext.get(it.get("owner")) if it.get("owner") else None
        if kind == "wardrobe" and owner and _images(d, owner) and set(it.get("files") or []) <= set(owner.get("files") or []):
            continue                              # the outfit is already drawn on its owner's sheet (the same spec describes both)
        written = spec_prompt(d, it)
        base = written or _built_prompt(project, it)
        prompt = _clip(base + _note(notes, it["id"]) + PLAIN[kind] + NO_TEXT)
        refs = []
        if again:
            refs = [{"path": f, "label": f"the current version of {it['name']}: keep this exact design, face and style, and change only what the note says"} for f in imgs[:1]]
        elif kind == "character":
            refs = [{"path": f, "label": f"the cast lineup: use it only to match {it['name']}'s face, hair, build and outfit and the art style; "
                                         f"draw only {it['name']}"} for f in imgs[:1]]
        elif kind == "wardrobe" and owner:
            refs = [{"path": f, "label": f"{owner['name']}, who wears this outfit"} for f in _images(d, owner)[:1]]
        if kind == "prop" and owner and _own_picture(d, owner, use_count) and len(refs) < 2:
            refs += [{"path": f, "label": f"{owner['name']}, who owns this prop: use it only to match the art style and the size of the prop next to a person"} for f in _images(d, owner)[:1]]
        out.append({"id": it["id"], "name": it["name"], "kind": kind, "reason": "made again" if again else "only a group picture" if shared else "no picture",
                    "prompt": prompt, "prompt_from": "the spec's own prompt" if written else "built from the item's notes", "refs": refs,
                    "owner": (owner or {}).get("name", ""), "owner_ready": _own_picture(d, owner, use_count)})
    store = Store(d)
    for sh in _choreo_sheets(d):
        owner = by_ext.get(sh["owner_ext"])
        has = _sheet_picture(d, store, sh["id"])
        if has and sh["id"] not in redo:
            continue
        own_imgs = _images(d, owner) if owner else []
        refs = [{"path": f, "label": f"{sh['owner_name']}: match this dancer's face, hair, build and outfit and the art style; draw only {sh['owner_name']}"} for f in own_imgs[:1]]
        if has and sh["id"] in redo:
            refs = [{"path": has, "label": "the current version of this sheet: keep the dancer and the style, and change only what the note says"}] + refs[:1]
        out.append({"id": sh["id"], "name": sh["name"], "kind": "choreo", "reason": "made again" if has else "no picture",
                    "prompt": _clip(sh["base"] + _note(notes, sh["id"]) + PLAIN["choreo"] + NO_TEXT), "prompt_from": "built from the plan's moves", "refs": refs,
                    "owner": sh["owner_name"], "owner_ready": _own_picture(d, owner, use_count)})
    order = {"character": 0, "set": 1, "prop": 2, "wardrobe": 3, "choreo": 4}
    return sorted(out, key=lambda c: (order[c["kind"]], c["name"]))


def _needs_input_image(man: dict) -> bool:
    from .render import MEDIA_NAME
    return any(f.get("required") and MEDIA_NAME.search(f["name"]) for f in man["inputs"])


def effective_model(provider: str, model: str, has_refs: bool) -> str:
    """The model that will really make a picture. An editing model (Nano Banana Edit, GPT Image "image-to-image") refuses a request
    with no input picture, and a prop or a place has none to give, so those use the same model's text-to-image version when it exists.
    If it doesn't, the chosen model is kept and its own check explains what is missing before anything is billed."""
    from .render import manifest
    man = manifest(provider, model)
    if has_refs or not _needs_input_image(man):
        return man["model"]
    siblings = []
    if "image-to-image" in model:
        siblings.append(model.replace("image-to-image", "text-to-image"))
    if model.endswith(("-edit", "/edit")):
        siblings.append(model[:-5])
    for sib in siblings:
        try:
            alt = manifest(provider, sib)
        except (SystemExit, Exception):
            continue
        if not _needs_input_image(alt):
            return alt["model"]
    return man["model"]


def _man_and_aspect(provider: str, model: str, kind: str) -> tuple[dict, str | None]:
    from .render import manifest
    man = manifest(provider, model)
    enum = (man.get("caps") or {}).get("aspect_ratios") or []
    want = next((a for a in ASPECT[kind] if a in enum), None)
    return man, want


def estimate(d: str, ids: list[str], provider: str, model: str, redo: list[str] | tuple = (), notes: dict | None = None) -> dict:
    from . import render as R
    cands = {c["id"]: c for c in candidates(d, redo, notes)}
    chosen = [cands[i] for i in ids if i in cands]
    if not chosen:
        raise SystemExit("Choose at least one picture to make.")
    asked = R.manifest(provider, model)
    used: dict[str, int] = {}
    for c in chosen:                                     # a picture with nothing to look at uses the text-to-image version of the model
        m = effective_model(provider, asked["model"], bool(c["refs"]))
        used[m] = used.get(m, 0) + 1
    usd, known, credits, basis = 0.0, True, 0.0, ""
    for m, n in used.items():
        man = R.manifest(provider, m)
        payload = {man["roles"].get("prompt", "prompt"): chosen[0]["prompt"]}
        try:
            e = R.estimate_payload(provider, man["model"], man, payload)
        except Exception:
            e = {"usd": None, "basis": ""}
        basis = basis or e.get("basis", "")
        if provider == "kie":                            # Kie publishes no price: what this model cost before, else what the edit version did
            seen = [float(j["cost"]) for j in R.Store(d).jobs if j["provider"] == "kie" and j["model"] == man["model"] and j.get("cost")]
            per = sorted(seen)[len(seen) // 2] if seen else (R.kie_cost_memory().get(man["model"]) or R.kie_cost_memory().get(asked["model"]))
            if per:
                from .budget import KIE_USD_PER_CREDIT
                credits += per * n
                usd += per * n * KIE_USD_PER_CREDIT
                basis = f"about {round(per)} credits per picture (what {man['model'].split('/')[-1]} cost before)"
                continue
        if e.get("usd") is None:
            known = False
        else:
            usd += e["usd"] * n
    out = {"count": len(chosen), "provider": provider, "model": asked["model"], "title": asked["title"],
           "usd": round(usd, 2) if known else None, "basis": basis,
           "uses": [{"model": m, "title": R.manifest(provider, m)["title"], "count": n} for m, n in used.items()]}
    if credits:
        out["kie_credits_est"] = round(credits)
    return out


def _guard(d: str, provider: str, usd: float | None) -> None:
    from .routing import settings
    project = _read(os.path.join(d, "project.json"), {})
    s = settings(project)
    if provider == "comfyui":
        return
    if s["mode"] == "local":
        raise SystemExit("Local First is on, so nothing is sent to paid cloud services. Switch this project to Balanced or Premium "
                         "(Plan & budget) to make pictures with a cloud model.")
    if s["budget_usd"] is not None and usd is not None:
        from .budget import spent
        used = spent(d)["total_usd"]
        if used + usd > s["budget_usd"] + 1e-6:
            raise SystemExit(f"Over budget: this project has spent ${used:.2f} of its ${s['budget_usd']:.2f} budget, and this would add about "
                             f"${usd:.2f}. Nothing was sent.")


def queue(d: str, ids: list[str], provider: str, model: str, confirmed: bool = False, redo: list[str] | tuple = (), notes: dict | None = None,
          draft: bool = False, cap_usd: float | None = None) -> dict:
    """Create one image job per picture. Needs confirmed=True (the screen shows the price first). `cap_usd` refuses a batch whose known price is
    above it; `draft` asks for the model's cheaper quality where it has one."""
    from . import render as R
    if not confirmed:
        raise SystemExit("Confirm the price first: nothing was sent.")
    if cap_usd is not None:
        try:
            cap_usd = float(cap_usd)
        except (TypeError, ValueError):
            cap_usd = float("nan")
        if not (cap_usd == cap_usd and 0 <= cap_usd < float("inf")):
            raise SystemExit("The spend limit is not a valid amount. Nothing was sent.")
    if len(ids) > MAX_BATCH:
        raise SystemExit(f"Make at most {MAX_BATCH} pictures at a time.")
    cands = {c["id"]: c for c in candidates(d, redo, notes)}
    chosen = [cands[i] for i in dict.fromkeys(ids) if i in cands]
    if not chosen:
        raise SystemExit("Choose at least one picture to make.")
    est = estimate(d, [c["id"] for c in chosen], provider, model, redo, notes)
    if cap_usd is not None and est.get("usd") is not None and est["usd"] > cap_usd + 1e-9:
        raise SystemExit(f"This would cost about ${est['usd']:.2f}, which is over your limit of ${cap_usd:.2f}. Nothing was sent.")
    _guard(d, provider, est.get("usd"))
    store = R.Store(d)
    made = []
    for c in chosen:
        if any(j.get("kind") == "asset" and j.get("asset_id") == c["id"] and j["state"] in R.ACTIVE for j in store.jobs):
            continue                                                       # never double-queue the same picture
        job_model = effective_model(provider, est["model"], bool(c["refs"]))
        _, aspect = _man_and_aspect(provider, job_model, c["kind"])
        job = {"id": uuid.uuid4().hex[:12], "shot_id": f"asset:{c['id']}", "plan": "asset", "source_shots": [], "shot_start": 0, "shot_end": 0,
               "provider": provider, "model": job_model, "kind": "asset", "asset_id": c["id"], "asset_kind": c["kind"], "asset_name": c["name"],
               "asset_prompt": c["prompt"], "asset_refs": c["refs"], "asset_aspect": aspect, "asset_draft": bool(draft), "overrides": {}, "fix_notes": [], "look": None,
               "state": "queued", "provider_job_id": None, "attempts": 0, "created": int(time.time()), "updated": int(time.time()),
               "output": None, "error": None, "cost": None}
        store.jobs.append(job)
        made.append(job)
    store.save()
    for j in made:
        emit(event="job", job=j)
    return {"queued": len(made), "estimate": est}


def build_payload(d: str, p, j: dict, man: dict) -> dict:
    """The request for one picture job: the prompt, the reference pictures it is to be consistent with, and a fitting shape."""
    from . import render as R
    roles = man["roles"]
    payload: dict = {roles.get("prompt", "prompt"): j["asset_prompt"]}
    refs = []
    for r in j.get("asset_refs") or []:
        path = os.path.join(d, r["path"])
        if os.path.exists(path) and _inside(d, path):
            refs.append({"label": r["label"], "path": path, "media": "image"})
    from .library import fit_to_model
    refs, _ = fit_to_model(refs, R.ref_limits(man, False))
    up = R._uploaded(d, p, refs) if refs else []
    if up and "ref_images" in roles:
        f = next(x for x in man["inputs"] if x["name"] == roles["ref_images"])
        urls = [u["url"] for u in up]
        payload[f["name"]] = urls if f["type"] == "array" else urls[0]
    if j.get("asset_aspect") and "aspect_ratio" in roles:
        payload[roles["aspect_ratio"]] = j["asset_aspect"]
    if j.get("asset_draft") and any(f["name"] == "quality" and "low" in (f.get("enum") or []) for f in man["inputs"]):
        payload["quality"] = "low"                       # a draft: cheaper, and good enough to judge the design
    payload = R.fill_required(man, payload, up)
    return payload


def verify_picture(path: str) -> None:
    """A downloaded file must open as a real picture before it is offered."""
    from PIL import Image
    with Image.open(path) as im:
        im.verify()


def status(d: str) -> dict:
    from . import render as R
    jobs = [j for j in R.Store(d).jobs if j.get("kind") == "asset" and j["state"] != "dismissed"]
    return {"candidates": candidates(d), "jobs": [{k: j.get(k) for k in ("id", "asset_id", "asset_name", "asset_kind", "state", "output", "error", "model",
                                                                        "provider", "cost", "cost_unit", "created", "used", "estimate_usd")}
                                                 for j in sorted(jobs, key=lambda x: x["created"], reverse=True)]}


def use(d: str, job_id: str) -> dict:
    """Make a finished picture the reference picture of its item. The item's written specs stay with it; a group picture it only
    shared with others is replaced for this item alone."""
    from . import library
    from .render import Store
    store = Store(d)
    j = next((x for x in store.jobs if x["id"] == job_id and x.get("kind") == "asset"), None)
    if not j or j["state"] != "ready" or not j.get("output"):
        raise SystemExit("That picture isn't ready.")
    path = os.path.join(d, j["output"])
    if not (os.path.exists(path) and _inside(os.path.join(d, "generations"), path)):
        raise SystemExit("That picture's file is missing.")
    if str(j["asset_id"]).startswith(CHOREO):
        return _use_sheet(d, store, j)
    p, lib = library.load(d)
    it = next((i for i in lib["items"] if i["id"] == j["asset_id"]), None)
    if not it:
        raise SystemExit("The reference item is gone.")
    keep = [f for f in it.get("files") or [] if library.media_kind(f) not in ("image",)]      # specs and other documents stay
    it["files"] = [j["output"]] + keep
    it["generated_from_spec"] = True
    library.save_library(d, p, lib)
    _retire_others(store, j["asset_id"], j["id"])                                              # one chosen picture per item
    store.update(j, used=True, replaced=False)
    return status(d)


def _use_sheet(d: str, store, j: dict) -> dict:
    """A chosen dance sheet is added to the project's choreography files (the one it replaces is taken out)."""
    from .onboarding import choreo_get, choreo_set
    ch = choreo_get(d)
    old = {o["output"] for o in store.jobs if o.get("kind") == "asset" and o.get("asset_id") == j["asset_id"] and o.get("used") and o.get("output")}
    files = [f for f in ch.get("files") or [] if f not in old]
    if j["output"] not in files:
        files.append(j["output"])
    mode = ch.get("mode") if ch.get("mode") not in (None, "none") else "upload"
    choreo_set(d, {**ch, "mode": mode, "files": files, "precise": bool(ch.get("precise"))})
    _retire_others(store, j["asset_id"], j["id"])
    store.update(j, used=True, replaced=False)
    return status(d)


def own(d: str, item_id: str, rel: str) -> dict:
    """Use a picture of your own (already in the project) for a card, instead of making one. Its written specs stay with it."""
    from . import library
    path = os.path.join(d, str(rel))
    if not (os.path.isfile(path) and _inside(d, path) and library.media_kind(str(rel)) == "image"):
        raise SystemExit("Choose a picture that is in this project.")
    try:
        verify_picture(path)
    except Exception:
        raise SystemExit("That file does not open as a picture.")
    p, lib = library.load(d)
    it = next((i for i in lib["items"] if i["id"] == item_id and i.get("kind") in VISUAL), None)
    if not it:
        raise SystemExit("That reference is gone.")
    it["files"] = [rel] + [f for f in it.get("files") or [] if library.media_kind(f) != "image"]
    it.pop("generated_from_spec", None)
    library.save_library(d, p, lib)
    from .render import Store
    _retire_others(Store(d), item_id, None)
    return cards(d)


def cards(d: str) -> dict:
    """Every picture of the production as one card: who it is, the picture it has now and where that came from, a picture waiting for
    your approval, whether one is being made, and what it is waiting on (a prop or dance sheet is made after its owner's sheet)."""
    from . import render as R
    from .library import load
    _, lib = load(d)
    items = lib.get("items") or []
    by_ext = {i.get("external_id"): i for i in items if i.get("external_id")}
    store = R.Store(d)
    jobs = sorted([j for j in store.jobs if j.get("kind") == "asset" and j["state"] != "dismissed"], key=lambda x: x["created"], reverse=True)
    use_count: dict[str, int] = {}
    for it in items:
        if it.get("kind") == "character":
            for f in _images(d, it):
                use_count[f] = use_count.get(f, 0) + 1
    made = list(_generated_ids(d)) + [sh["id"] for sh in _choreo_sheets(d)]
    prompts = {c["id"]: c for c in candidates(d, made)}
    out = []

    def card(cid, name, kind, picture, yours, owner, owner_ready):
        mine = [j for j in jobs if j.get("asset_id") == cid]
        pend = next((j for j in mine if j["state"] == "ready" and not j.get("used") and not j.get("replaced") and j.get("output") and os.path.exists(os.path.join(d, j["output"]))), None)
        act = next((j for j in mine if j["state"] in R.ACTIVE), None)
        fail = mine[0] if mine and mine[0]["state"] in ("failed", "uncertain") and not pend and not act else None
        cand = prompts.get(cid)
        out.append({"id": cid, "name": name, "kind": kind, "picture": picture, "yours": yours, "owner": owner, "owner_ready": owner_ready,
                    "state": "making" if act else "waiting" if pend else "yours" if yours else "approved" if picture else "missing",
                    "pending": {"job": pend["id"], "output": pend["output"], "model": pend["model"]} if pend else None,
                    "error": (fail or {}).get("error"), "prompt": (cand or {}).get("prompt", ""), "prompt_from": (cand or {}).get("prompt_from", "")})

    for it in items:
        kind = it.get("kind")
        if kind not in VISUAL or it.get("from_show"):
            continue
        imgs = _images(d, it)
        shared = kind == "character" and bool(imgs) and all(use_count.get(f, 0) > 1 for f in imgs)
        owner = by_ext.get(it.get("owner")) if it.get("owner") else None
        if kind == "wardrobe" and owner and set(it.get("files") or []) <= set(owner.get("files") or []):
            continue
        has = bool(imgs) and not shared
        card(it["id"], it["name"], kind, imgs[0] if has else None, has and not it.get("generated_from_spec"), (owner or {}).get("name", ""),
             _own_picture(d, owner, use_count) if owner else True)
    for sh in _choreo_sheets(d):
        owner = by_ext.get(sh["owner_ext"])
        card(sh["id"], sh["name"], "choreo", _sheet_picture(d, store, sh["id"]), False, sh["owner_name"], _own_picture(d, owner, use_count))
    order = {"character": 0, "set": 1, "prop": 2, "wardrobe": 3, "choreo": 4}
    out.sort(key=lambda c: (order[c["kind"]], c["name"]))
    return {"cards": out, "working": any(c["state"] == "making" for c in out)}


def discard(d: str, job_id: str) -> dict:
    from .render import ACTIVE, Store
    store = Store(d)
    j = next((x for x in store.jobs if x["id"] == job_id and x.get("kind") == "asset"), None)
    if not j or j["state"] in ACTIVE:
        raise SystemExit("That picture can't be discarded right now.")
    store.update(j, state="dismissed")
    return status(d)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-refgen")
    ap.add_argument("action", choices=["candidates", "estimate", "queue", "use", "discard", "status", "cards", "own"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "candidates":
            res = candidates(a.project)
        elif a.action == "estimate":
            res = estimate(a.project, x["ids"], x["provider"], x["model"], x.get("redo") or [], x.get("notes") or {})
        elif a.action == "queue":
            res = queue(a.project, x["ids"], x["provider"], x["model"], bool(x.get("confirmed")), x.get("redo") or [], x.get("notes") or {},
                        bool(x.get("draft")), x.get("cap_usd"))
        elif a.action == "use":
            res = use(a.project, x["job"])
        elif a.action == "discard":
            res = discard(a.project, x["job"])
        elif a.action == "cards":
            res = cards(a.project)
        elif a.action == "own":
            res = own(a.project, str(x["id"]), str(x["file"]))
        else:
            res = status(a.project)
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
