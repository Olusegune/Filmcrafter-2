"""The film's spending summary: reads the render jobs and the paid-operations ledger, keeps reported amounts apart from estimates, never adds different units, and changes nothing."""
import hashlib
import json
import os

import pytest

from filmcrafter_engine import bible, paidops as P, shots as S, spending as SP, story

SCRIPT = "INT. KITCHEN - NIGHT\n\nSarah pours tea.\n\nSARAH\nHe said he'd call.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def jobs(film, rows):
    os.makedirs(os.path.join(film, "render"), exist_ok=True)
    json.dump({"jobs": rows}, open(os.path.join(film, "render", "jobs.json"), "w"))


def ledger(film):
    return P.Ledger(os.path.join(film, "voice", "ledger.json"), film="T")


def done(L, key, provider, action, unit, est, actual=None):
    e = L.begin(key=key, provider=provider, area="voice" if action == "speak" else action, action=action, estimate={"unit": unit, "amount": est, "basis": ""})
    L.mark(e["id"], P.SUBMITTED)
    L.complete(e["id"], actual_amount=actual, source="reply" if actual is not None else None)
    return e["id"]


def test_an_empty_film_has_nothing_to_show(film):
    s = SP.summary(film)
    assert s["lines"] == [] and s["totals"] == [] and s["operations"] == 0 and s["uncertain"] == []


def test_each_step_and_unit_stays_apart_and_estimates_are_not_reported(film):
    jobs(film, [
        {"kind": "image", "provider": "kie", "state": "ready", "cost": 4},
        {"kind": "video", "provider": "kie", "state": "ready", "cost": 164},
        {"kind": "lipsync", "provider": "kie", "state": "ready", "cost": 32},
        {"kind": "video", "provider": "fal", "state": "ready", "estimate_usd": 1.25},
        {"kind": "video", "provider": "kie", "state": "failed", "cost": 999},             # failed: costs nothing
        {"kind": "image", "provider": "openai", "state": "ready"},
    ])
    L = ledger(film)
    done(L, "a", "elevenlabs", "speak", "elevenlabs_credits", 10, actual=6)
    done(L, "b", "elevenlabs", "sfx", "elevenlabs_credits", 33)                           # the provider reported nothing: an estimate
    s = SP.summary(film)
    by = {(r["step"], r["provider"]): r for r in s["lines"]}
    assert by[("video", "kie")]["reported"] == 164 and by[("pictures", "kie")]["reported"] == 4 and by[("lipsync", "kie")]["reported"] == 32
    assert by[("video", "fal")]["estimated"] == 1.25 and by[("video", "fal")]["reported"] == 0
    assert by[("voices", "elevenlabs")]["reported"] == 6
    assert by[("sound_effects", "elevenlabs")]["estimated"] == 33 and by[("sound_effects", "elevenlabs")]["reported"] == 0
    assert by[("pictures", "openai")]["operations"] == 1
    tot = {t["unit"]: t for t in s["totals"]}
    assert tot["kie_credits"]["reported"] == 200 and tot["usd"]["estimated"] == 1.25 and tot["elevenlabs_credits"]["reported"] == 6   # never summed across units


def test_an_unresolved_operation_is_listed_and_counts_only_once_charged(film):
    L = ledger(film)
    e = L.begin(key="u", provider="elevenlabs", area="voice", action="speak", estimate={"unit": "elevenlabs_credits", "amount": 8, "basis": ""})
    L.mark(e["id"], P.UNCERTAIN)
    s = SP.summary(film)
    assert [u["id"] for u in s["uncertain"]] == [e["id"]] and s["operations"] == 0
    L.resolve(e["id"], "charged")
    s = SP.summary(film)
    assert s["uncertain"] == [] and s["operations"] == 1


def test_it_changes_nothing(film):
    jobs(film, [{"kind": "video", "provider": "kie", "state": "ready", "cost": 5}])
    done(ledger(film), "k", "elevenlabs", "speak", "elevenlabs_credits", 3, actual=3)
    def h():
        out = []
        for r, _, fs in os.walk(film):
            for f in sorted(fs):
                out.append((os.path.join(r, f), hashlib.sha1(open(os.path.join(r, f), "rb").read()).hexdigest()))
        return sorted(out)
    before = h()
    SP.summary(film)
    assert h() == before


def test_a_damaged_job_file_does_not_stop_the_summary(film):
    os.makedirs(os.path.join(film, "render"), exist_ok=True)
    open(os.path.join(film, "render", "jobs.json"), "w").write("{not json")
    before = sorted(os.listdir(os.path.join(film, "render")))
    r = SP.summary(film)
    assert r["lines"] == [] and r["problems"] and sorted(os.listdir(os.path.join(film, "render"))) == before     # said so, and moved nothing
