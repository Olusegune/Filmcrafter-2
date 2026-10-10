"""A real provider test: make ONE storyboard picture of one shot through the real render engine and a real provider, and report what it cost.

It spends the key owner's money (one picture: usually a few cents), so it does nothing until you pass --yes, and it refuses a price above --max-usd (default 0.25) or a price
that can't be known. The key is read from the environment and never printed or stored.

  set FAL_KEY=...                    (or KIE_KEY=... for Kie.ai)
  python scripts/live_test.py                       # shows the price only, spends nothing
  python scripts/live_test.py --yes                 # makes one picture
  python scripts/live_test.py --yes --provider kie --model google/nano-banana-edit --max-usd 0.10

Run it with a Python that has the film engine's packages (see README), from the repository root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))

KEYS = {"fal": "FAL_KEY", "kie": "KIE_KEY"}
SCRIPT = "INT. KITCHEN - MORNING\n\nSarah pours tea by the window.\n\nSARAH\nHe said he would call.\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=sorted(KEYS))
    ap.add_argument("--model")
    ap.add_argument("--max-usd", type=float, default=0.25)
    ap.add_argument("--yes", action="store_true", help="really make the picture (this is billed)")
    a = ap.parse_args()
    provider = a.provider or next((p for p, v in KEYS.items() if os.environ.get(v)), None)
    if not provider or not os.environ.get(KEYS[provider]):
        print(f"No key found. Set {' or '.join(KEYS.values())} in the environment first (the key is never printed or saved).")
        return 2
    from filmcrafter_engine import bible, make, render, shots, story
    d = story.create(tempfile.mkdtemp(prefix="fc-live-"), "Live test", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    bible.update_rules(d, {"style": {"lane": "painterly animation"}})
    sid = shots.breakdown(d)["shots"][0]["id"]
    make.sync(d)
    rd = make.render_dir(d)
    model = a.model or render.default_model(provider, "image")
    est = render.estimate(rd, [sid], provider, model, "image")
    usd = est.get("usd")
    print(f"Provider {provider}, model {model}, shot {sid}: price {'$%.3f' % usd if usd is not None else 'not published'}")
    if usd is None:
        print("The price can't be known, so nothing was made. Pass a model with a published price.")
        return 3
    if usd > a.max_usd:
        print(f"That is above --max-usd {a.max_usd}. Nothing was made.")
        return 3
    if not a.yes:
        print("Nothing was made. Add --yes to make one picture at this price.")
        return 0
    made = render.enqueue(rd, [sid], provider, model, {"_variants": 1}, [], "image")
    make.tag(d, [j["id"] for j in made], "storyboard")
    print(f"Queued {len(made)} job. Waiting for the provider…")
    render.run(rd)
    s = next(x for x in make.status(d)["shots"] if x["id"] == sid)
    opt = s["storyboard"]["options"]
    for o in opt:
        print(f"Result: state={o['state']} cost={o.get('cost')} file={os.path.join(rd, o['image']) if o['image'] else None} error={o.get('error')}")
    ok = any(o["ok"] for o in opt)
    print("PASSED: a real picture was made and found by the film workflow." if ok else "FAILED: no finished picture. See the error above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
