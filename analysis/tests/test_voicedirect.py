"""Stage B: directing voices. The spoken version of a line, another take, natural-delivery and voice-casting suggestions, an approved voice that nothing replaces silently, and voicing a whole
scene with one yes and a cap. Every provider call is faked: nothing here spends or sends anything."""
import json
import os

import pytest

from filmcrafter_engine import assist, bible, cast_voice as C, paidops as P, voicedirect as VD, voiceover as V
from tests.test_cast_voice import Reply, VID, calls, film, give_voice, lila_shot, wav_bytes  # noqa: F401  (fixtures)

VID2 = "ZyXwVuTs9876"
TTS = f"/v1/text-to-speech/{VID}"
TTS2 = f"/v1/text-to-speech/{VID2}"


def posts(log, part):
    return [c for c in log if c[0] == "POST" and part in c[1]]


def ready(film, calls):
    log, replies = calls
    replies[TTS] = lambda: Reply(200, content=wav_bytes(1.2))
    replies[TTS2] = lambda: Reply(200, content=wav_bytes(1.0))
    give_voice(film)
    give_voice(film, "Chloe", voice_id=VID2, voice_name="Bright")
    return log, replies


def fake_ai(monkeypatch, out, seen=None):
    def call(client, model, system, user, name, schema):
        if seen is not None:
            seen.append({"system": system, "user": json.loads(user), "schema": schema})
        return out
    monkeypatch.setattr(assist, "_call", call)
    import filmcrafter_engine.director as D
    import filmcrafter_engine.llm as L
    monkeypatch.setattr(L, "client", lambda: object())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "test-model")


# ---------------------------------------------------------------- the spoken version of a line

def test_a_spoken_version_is_kept_apart_from_the_screenplay_and_is_what_is_spoken_by_default(film, calls):
    log, _ = ready(film, calls)
    sid = lila_shot(film)
    written = next(p["lines"] for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"] if p["name"] == "Lila")
    out = VD.set_performance(film, sid, "Lila", "[sighs] It… it looked weird.", note="hesitates", pronunciation="Lila = LEE-la")
    row = out["lines"][0]
    assert row["text"].startswith("[sighs]") and row["written"] == " ".join(written) and row["written_changed"] is False and row["source"] == "person"
    assert next(p["lines"] for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"] if p["name"] == "Lila") == written     # the screenplay line is untouched
    C.speak(film, sid, "Lila", None, True)
    sent = posts(log, TTS)[0][2]["json"]["text"]
    assert sent == "[sighs] It… it looked weird."
    VD.clear_performance(film, sid, "Lila")
    assert VD.get_performance(film)["lines"] == []
    C.speak(film, sid, "Lila", None, True)
    assert posts(log, TTS)[1][2]["json"]["text"] == " ".join(written)


def test_a_changed_screenplay_line_is_noticed_and_nothing_is_rewritten(film, calls, monkeypatch):
    ready(film, calls)
    sid = lila_shot(film)
    VD.set_performance(film, sid, "Lila", "Hm. It looked weird.")
    from filmcrafter_engine import shots as S
    real = V.status

    def changed(d):
        st = real(d)
        for s in st["shots"]:
            for p in s["people"]:
                if p["name"] == "Lila":
                    p["lines"] = ["It looked very strange."]
        return st
    monkeypatch.setattr(V, "status", changed)
    row = VD.get_performance(film)["lines"][0]
    assert row["written_changed"] is True and row["text"] == "Hm. It looked weird."


def test_a_spoken_version_needs_words_a_real_line_and_a_valid_shot(film, calls):
    ready(film, calls)
    sid = lila_shot(film)
    for bad in (("../x", "Lila", "hi"), (sid, "Lila", "   "), (sid, "Nobody", "hi"), (sid, "Lila", "x" * 5000)):
        with pytest.raises(SystemExit):
            VD.set_performance(film, *bad)
    assert not os.path.exists(os.path.join(film, "voice", "performance.json"))


def test_a_damaged_performance_file_is_not_replaced_by_an_empty_one(film, calls):
    ready(film, calls)
    sid = lila_shot(film)
    VD.set_performance(film, sid, "Lila", "Hm.")
    p = os.path.join(film, "voice", "performance.json")
    if os.path.exists(p + ".bak"):
        os.remove(p + ".bak")
    open(p, "wb").write(b'{"lines": {"S01')
    with pytest.raises(SystemExit, match="damaged"):
        VD.set_performance(film, sid, "Lila", "Again.")
    assert open(p, "rb").read() == b'{"lines": {"S01'


# ---------------------------------------------------------------- another take

def test_another_take_is_a_new_performance_of_the_same_words_priced_first_and_the_old_take_is_kept(film, calls):
    log, _ = ready(film, calls)
    sid = lila_shot(film)
    first = C.speak(film, sid, "Lila", None, True)
    assert first["credits"] > 0 and "seed" not in posts(log, TTS)[0][2]["json"]
    est = C.estimate(film, [{"shot": sid, "speaker": "Lila"}, {"shot": sid, "speaker": "Lila", "new_take": True}])
    assert est["rows"][0]["cached"] is True and est["rows"][0]["credits"] == 0
    assert est["rows"][1]["cached"] is False and est["rows"][1]["credits"] > 0 and est["credits"] == est["rows"][1]["credits"]      # the price is shown before it is made
    with pytest.raises(SystemExit, match="only goes ahead after you confirm"):
        C.speak(film, sid, "Lila", None, False, new_take=True)
    assert len(posts(log, TTS)) == 1
    second = C.speak(film, sid, "Lila", None, True, new_take=True)
    third = C.speak(film, sid, "Lila", None, True, new_take=True)
    bodies = [c[2]["json"] for c in posts(log, TTS)]
    assert len(bodies) == 3 and bodies[1]["text"] == bodies[0]["text"] and 0 < bodies[1]["seed"] <= 4294967295 and bodies[1]["seed"] != bodies[2]["seed"]
    assert second["take"] != first["take"] != third["take"] and second["credits"] > 0
    t = C.takes(film, sid, "Lila")["takes"]
    assert len(t) == 3 and sum(1 for x in t if x["another_take"]) == 2 and sum(1 for x in t if x["current"]) == 1
    assert os.path.isfile(os.path.join(film, *first["take"].split("/")))                                                              # the first take is still there
    again = C.speak(film, sid, "Lila", None, True)                                                                                    # the original words are still free
    assert again["cached"] is True and len(posts(log, TTS)) == 3


def test_every_take_and_its_seed_is_in_the_ledger_and_a_repeat_of_an_unclear_one_is_still_blocked(film, calls):
    log, replies = ready(film, calls)
    sid = lila_shot(film)
    C.speak(film, sid, "Lila", None, True, new_take=True)
    rows = [e for e in C._ledger(film).entries() if e["action"] == "speak"]
    assert len(rows) == 1 and rows[0]["status"] == "completed" and rows[0]["estimate"]["unit"] == "elevenlabs_credits"


# ---------------------------------------------------------------- natural-delivery suggestions

def test_the_price_comes_first_and_nothing_is_sent_to_estimate(film, calls, monkeypatch):
    ready(film, calls)
    sent = []
    monkeypatch.setattr(assist, "_call", lambda *a, **k: sent.append(1))
    est = VD.natural_estimate(film, lila_shot(film), "Lila")
    assert sent == [] and "usd" in est and "line" in est["sends"]


def test_suggestions_are_cleaned_stay_optional_and_change_nothing(film, calls, monkeypatch):
    ready(film, calls)
    sid = lila_shot(film)
    seen = []
    C.set_voice(film, "Lila", {"voice_id": VID, "voice_name": "Warm", "model": "eleven_multilingual_v2"})      # a model that does not read tags
    fake_ai(monkeypatch, {"suggestions": [
        {"text": "It… it looked weird.", "why": "A small hesitation."},
        {"text": "It looked weird.", "why": "Same as before."},                                          # not a change: dropped
        {"text": "[laughs nervously] It looked weird, honestly.", "why": "A nervous laugh."},
        {"text": "It looked weird. Really really weird, and I will tell you exactly why now.", "why": "Too long."},
        {"text": "Um, it looked, uh, weird.", "why": "Fillers."}]}, seen)
    before = open(os.path.join(film, "voice", "cast.json"), "rb").read()
    r = VD.natural_suggest(film, sid, "Lila")
    texts = [s["text"] for s in r["suggestions"]]
    assert "It… it looked weird." in texts and "It looked weird." not in texts and len(texts) <= 3
    assert all("[" not in t for t in texts)                                                                  # the model does not read tags: they are removed, not spoken aloud
    honest = next(s for s in r["suggestions"] if "honestly" in s["text"])
    assert honest["adds_words"] == ["honestly"] and "It adds: honestly" in honest["keeps_meaning_check"]
    assert seen[0]["user"]["written_line"] == "It looked weird." and seen[0]["user"]["model_reads_tags"] is False
    assert "do not rewrite the plot" in seen[0]["system"]
    assert VD.get_performance(film)["lines"] == [] and open(os.path.join(film, "voice", "cast.json"), "rb").read() == before    # nothing was saved or changed


def test_a_tagged_model_keeps_its_direction_tags(film, calls, monkeypatch):
    ready(film, calls)
    sid = lila_shot(film)
    C.set_voice(film, "Lila", {"voice_id": VID, "voice_name": "Warm", "model": "eleven_v4"})
    fake_ai(monkeypatch, {"suggestions": [{"text": "[sighs] It looked weird.", "why": "A sigh first."}]})
    r = VD.natural_suggest(film, sid, "Lila")
    assert r["suggestions"][0]["text"] == "[sighs] It looked weird."


def test_accepting_a_suggestion_is_the_persons_act_and_marks_where_it_came_from(film, calls):
    ready(film, calls)
    sid = lila_shot(film)
    out = VD.set_performance(film, sid, "Lila", "It… it looked weird.", source="assistant")
    assert out["lines"][0]["source"] == "assistant"


# ---------------------------------------------------------------- finding a voice for a character

LIB = [{"voice_id": "v" * 12, "name": "Grace", "category": "premade", "description": "A warm, calm older woman", "labels": {"gender": "female", "age": "old", "accent": "british", "descriptive": "warm"}, "preview_url": ""},
       {"voice_id": "w" * 12, "name": "Max", "category": "premade", "description": "Young energetic man", "labels": {"gender": "male", "age": "young", "accent": "american"}, "preview_url": ""},
       {"voice_id": "x" * 12, "name": "June", "category": "premade", "description": "Bright young woman", "labels": {"gender": "female", "age": "young", "accent": "american", "descriptive": "bright"}, "preview_url": ""}]


def lila_id(film):
    return next(c["id"] for c in bible.view(film)["characters"] if c["name"].lower().startswith("lila"))


def test_matching_scores_the_labels_and_ranks_the_best_first_without_any_ai():
    w = {"gender": "female", "age": "old", "accent": "british", "descriptors": ["warm", "calm"]}
    rows = VD.match_voices(w, LIB)
    assert rows[0]["voice"]["name"] == "Grace" and "female" in rows[0]["why"] and "warm" in rows[0]["why"]
    assert all(r["voice"]["name"] != "Max" for r in rows)                                                   # the wrong gender never ranks
    assert VD.match_voices({"gender": "", "age": "", "accent": "", "descriptors": []}, LIB) == []           # nothing asked, nothing offered
    assert VD.wanted_from_text("An elderly grandmother, kind")["gender"] == "female" and VD.wanted_from_text("An elderly grandmother")["age"] == "old"
    assert VD.wanted_from_text("father and mother")["gender"] == ""


def test_voice_suggestions_propose_a_profile_and_matches_and_save_nothing(film, calls, monkeypatch):
    log, replies = calls
    replies["/v2/voices"] = Reply(200, {"voices": LIB, "has_more": False})
    lid = lila_id(film)
    bible.upsert(film, "character", {"id": lid, "age": "70", "role": "grandmother", "voice": "gentle"})
    seen = []
    fake_ai(monkeypatch, {"description": "Warm and unhurried", "age_range": "seventies", "accent": "British", "timbre": "soft", "pace": "slow", "emotional_range": "restrained", "delivery": "quiet",
                          "notes": "", "search": {"gender": "female", "age": "old", "accent": "british", "descriptors": ["warm", "calm", "ignored1", "ignored2", "ignored3"]}}, seen)
    before = bible.view(film)["rev"]
    r = VD.voices_suggest(film, lid)
    assert r["proposal"]["description"] == "Warm and unhurried" and r["matches"][0]["voice"]["name"] == "Grace" and r["wanted"]["descriptors"] == ["warm", "calm", "ignored1", "ignored2"]
    assert seen[0]["user"]["character"]["role"] == "grandmother" and "real actor" in seen[0]["system"]
    assert bible.view(film)["rev"] == before                                                                # the Bible was not changed
    assert not [c for c in log if c[0] == "POST"]                                                           # reading the library is free: nothing was paid for


def test_the_free_match_uses_the_saved_profile_and_needs_no_ai(film, calls, monkeypatch):
    log, replies = calls
    replies["/v2/voices"] = Reply(200, {"voices": LIB, "has_more": False})
    lid = lila_id(film)
    bible.set_voice_profile(film, lid, {"description": "A warm older woman", "accent": "British"})
    monkeypatch.setattr(assist, "_call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no AI call is made")))
    r = VD.voices_match(film, lid)
    assert r["matches"][0]["voice"]["name"] == "Grace" and r["approved"] is False


def test_with_no_key_there_are_no_matches_and_the_reason_is_plain(film, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_KEY", raising=False)
    monkeypatch.setattr(C, "_headers", lambda accept="application/json": (_ for _ in ()).throw(SystemExit("Add your ElevenLabs key in Settings.")))
    r = VD.voices_match(film, lila_id(film))
    assert r["matches"] == [] and "key" in r["note"]


# ---------------------------------------------------------------- an approved voice is never replaced silently

def approve(film, who="Lila"):
    cid = next(c["id"] for c in bible.view(film)["characters"] if c["name"].lower().startswith(who.lower()))
    bible.set_voice_profile(film, cid, {"approved": True})


def test_an_approved_voice_cannot_be_replaced_or_removed_without_saying_so(film, calls):
    log, _ = ready(film, calls)
    approve(film)
    with pytest.raises(SystemExit, match="is approved"):
        give_voice(film, voice_id="n" * 12, voice_name="Other")
    with pytest.raises(SystemExit, match="is approved"):
        C.clear_voice(film, "Lila")
    assert C._cast(film)["people"]["lila"]["voice_id"] == VID
    give_voice(film, model="eleven_v4")                                                                    # the same voice with another model is not a replacement
    assert C._cast(film)["people"]["lila"]["model"] == "eleven_v4"
    C.set_voice(film, "Lila", {"voice_id": "n" * 12, "voice_name": "Other"}, replace_approved=True)       # the person said so
    assert C._cast(film)["people"]["lila"]["voice_id"] == "n" * 12
    bible.set_voice_profile(film, next(c["id"] for c in bible.view(film)["characters"] if c["name"].lower().startswith("lila")), {"approved": False})
    C.clear_voice(film, "Lila")
    assert "lila" not in C._cast(film)["people"]


def test_keeping_or_cloning_over_an_approved_voice_is_refused_before_anything_is_paid(film, calls, tmp_path):
    log, _ = ready(film, calls)
    approve(film)
    with pytest.raises(SystemExit, match="is approved"):
        C.design_save(film, "Lila", "prev_abc123", "New", "desc", confirmed=True)
    sample = tmp_path / "me.wav"
    sample.write_bytes(wav_bytes())
    with pytest.raises(SystemExit, match="is approved"):
        C.clone(film, "Lila", "Me", [str(sample)], consent=True, confirmed=True)
    assert posts(log, "/v1/") == [] and not [e for e in C._ledger(film).entries() if e["action"] in ("clone", "design_save")]


# ---------------------------------------------------------------- voicing a whole scene

def test_the_plan_names_the_speakers_the_missing_lines_and_the_price_and_sends_nothing(film, calls):
    log, _ = ready(film, calls)
    p = VD.scene_plan(film, 1)
    assert {s["name"] for s in p["speakers"]} == {"Lila", "Chloe"} and all(s["has_voice"] for s in p["speakers"])
    assert p["missing"] == 3 and p["no_voice"] == [] and p["estimate"]["credits"] > 0 and [x["state"] for x in p["lines"]] == ["missing"] * 3
    assert posts(log, "/v1/") == []
    with pytest.raises(SystemExit, match="no spoken lines"):
        VD.scene_plan(film, 9)


def test_a_scene_needs_one_yes_and_a_cap_and_a_price_above_the_cap_sends_nothing(film, calls):
    log, _ = ready(film, calls)
    with pytest.raises(SystemExit, match="only goes ahead after you confirm"):
        VD.scene_voice(film, 1, False, 500)
    with pytest.raises(SystemExit, match="spending cap"):
        VD.scene_voice(film, 1, True, None)
    with pytest.raises(SystemExit, match="spending cap"):
        VD.scene_voice(film, 1, True, 0)
    total = VD.scene_plan(film, 1)["estimate"]["credits"]
    with pytest.raises(SystemExit, match="above your cap"):
        VD.scene_voice(film, 1, True, total - 1)
    assert posts(log, "/v1/") == []


def test_voicing_a_scene_speaks_only_the_missing_lines_within_the_cap_and_reports_each(film, calls):
    log, _ = ready(film, calls)
    plan = VD.scene_plan(film, 1)
    first = next(x for x in plan["lines"] if x["speaker"] == "Chloe")
    own = film + "/own.wav"
    open(own, "wb").write(wav_bytes(1.0))
    V.attach(film, first["shot"], "Chloe", own)                                                          # one line already has the person's own recording
    r = VD.scene_voice(film, 1, True, 500)
    assert r["done"] == 2 and r["failed"] == 0 and r["stopped"] is None and len(r["results"]) == 2 and all(x["ok"] for x in r["results"])
    assert r["spent_credits"] <= r["cap"] and len(posts(log, "/v1/text-to-speech")) == 2
    assert not posts(log, TTS2)                                                                          # Chloe's own recording was not replaced
    after = VD.scene_plan(film, 1)
    assert after["missing"] == 0 and {x["state"] for x in after["lines"]} == {"recorded", "spoken"}
    assert VD.scene_voice(film, 1, True, 500)["note"].startswith("Every line")                           # nothing left: nothing sent
    assert len(posts(log, "/v1/text-to-speech")) == 2


def test_one_failed_line_does_not_destroy_the_others(film, calls):
    log, replies = ready(film, calls)
    replies[TTS2] = lambda: Reply(401, {"detail": {"status": "invalid_api_key", "message": "bad key"}})
    r = VD.scene_voice(film, 1, True, 500)
    assert r["done"] == 2 and r["failed"] == 1 and r["stopped"] is None
    bad = next(x for x in r["results"] if not x["ok"])
    assert bad["speaker"] == "Chloe" and bad["attempted"] and bad["why"]
    assert VD.scene_plan(film, 1)["missing"] == 1                                                         # only the failed one is still missing


def test_an_unclear_charge_stops_the_rest_and_says_why(film, calls):
    log, replies = ready(film, calls)
    import requests
    first = VD.scene_plan(film, 1)["lines"][0]["speaker"]
    path = TTS if first == "Lila" else TTS2

    def drop():
        raise requests.ConnectionError("reset by peer")
    replies[path] = drop
    r = VD.scene_voice(film, 1, True, 500)
    assert r["stopped"] and "charge is unclear" in r["stopped"]
    assert r["results"][0]["ok"] is False and r["results"][0]["attempted"] is True
    assert all(x["attempted"] is False for x in r["results"][1:]) and len(posts(log, "/v1/text-to-speech")) == 1


def test_the_cap_is_kept_line_by_line(film, calls):
    log, _ = ready(film, calls)
    plan = VD.scene_plan(film, 1)
    credits = sorted(x["credits"] for x in plan["lines"])
    cap = credits[0] + credits[1] + 0.5                                                                   # room for the two cheapest, not the third
    with pytest.raises(SystemExit, match="above your cap"):
        VD.scene_voice(film, 1, True, cap)                                                                # the whole price is checked first
    assert posts(log, "/v1/") == []
    r = VD.scene_voice(film, 1, True, cap, items=[{"shot": x["shot"], "speaker": x["speaker"]} for x in plan["lines"] if x["credits"] in credits[:2]][:2])
    assert r["spent_credits"] <= cap


def test_a_line_without_a_voice_is_reported_not_spoken(film, calls):
    log, replies = calls
    replies[TTS] = lambda: Reply(200, content=wav_bytes())
    give_voice(film)                                                                                      # only Lila has a voice
    p = VD.scene_plan(film, 1)
    assert p["no_voice"] == ["Chloe"] and p["missing"] == 2
    r = VD.scene_voice(film, 1, True, 500)
    assert r["done"] == 2 and not posts(log, TTS2)


# ---------------------------------------------------------------- the table read

def test_the_table_read_lists_the_dialogue_in_order_with_the_clips_it_has(film, calls):
    ready(film, calls)
    VD.scene_voice(film, 1, True, 500)
    t = VD.table_read(film, 1)
    assert [x["speaker"] for x in t["lines"]] == ["Lila", "Chloe", "Lila"] and t["silent"] == 0 and t["seconds"] > 3
    assert all(x["file"] and x["file"].startswith("voice/") and x["source"] == "elevenlabs" for x in t["lines"])
    VD.set_performance(film, t["lines"][0]["shot"], "Lila", "Hm… it looked weird.")
    assert VD.table_read(film, 1)["lines"][0]["text"] == "Hm… it looked weird."                          # what is heard matches the spoken version
    V.remove(film, t["lines"][0]["shot"], "Lila")
    assert VD.table_read(film, 1)["silent"] == 1


def test_the_command_line_speaks_the_engine_format_and_only_knows_its_actions(film, calls, capsys):
    ready(film, calls)
    assert VD.main(["scene_plan", film, "--data", json.dumps({"scene": 1})]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["missing"] == 3
    with pytest.raises(SystemExit):
        VD.main(["format_disk", film])
    assert VD.main(["scene_voice", film, "--data", json.dumps({"scene": 1, "cap_credits": 500})]) == 1
    assert "only goes ahead after you confirm" in capsys.readouterr().out
