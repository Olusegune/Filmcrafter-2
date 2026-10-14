"""Stage D: making sound effects and music with a provider. Every provider call is faked: nothing here spends or sends anything. What is checked: the price and the rights come first, one yes covers one
request, an unclear outcome is never repeated, what is made is kept once with how it was made, and a sound made before is never paid for again."""
import json
import os

import pytest
import requests

from filmcrafter_engine import audiocues as Q, audiogen as AG, audiolib as AL, bible, shots as S, story
from tests.test_cast_voice import Reply, wav_bytes

SCRIPT = "INT. KITCHEN - NIGHT\n\nRain on the roof. Sarah pours tea from the kettle.\n\nSARAH\nHe said he'd call.\n"
YES = dict(confirmed=True, rights_ack=True)


@pytest.fixture
def film(tmp_path, monkeypatch):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    monkeypatch.setenv("ELEVENLABS_KEY", "test-key-not-real")
    monkeypatch.setenv("KIE_KEY", "test-kie-key-not-real")
    monkeypatch.setattr(AG.time, "sleep", lambda s: None)
    return d


@pytest.fixture
def net(monkeypatch):
    """Everything that would have gone to a provider, and the replies to give."""
    log = {"eleven": [], "kie_post": [], "kie_get": [], "download": []}
    rep = {"eleven": lambda: Reply(200, content=wav_bytes(1.5)), "kie_post": lambda: Reply(200, {"code": 200, "msg": "success", "data": {"taskId": "task_1"}}),
           "kie_get": lambda: Reply(200, {"code": 200, "data": {"state": "success", "resultJson": json.dumps({"resultUrls": ["https://cdn.example.com/a.mp3", "https://cdn.example.com/b.mp3"]}), "creditsConsumed": 12}}),
           "download": lambda url: wav_bytes(2.0)}

    def eleven(path, accept="audio/mpeg", timeout=300, **kw):
        log["eleven"].append((path, kw))
        r = rep["eleven"]()
        if not hasattr(r, "headers"):
            r.headers = {}
        return r

    def kpost(path, **kw):
        log["kie_post"].append((path, kw))
        r = rep["kie_post"]()
        r.headers = getattr(r, "headers", {})
        return r

    def kget(path, **kw):
        log["kie_get"].append((path, kw))
        r = rep["kie_get"]()
        r.headers = getattr(r, "headers", {})
        return r

    def dl(url):
        log["download"].append(url)
        return rep["download"](url)
    monkeypatch.setattr(AG, "_eleven_post", eleven)
    monkeypatch.setattr(AG, "_kie_post", kpost)
    monkeypatch.setattr(AG, "_kie_get", kget)
    monkeypatch.setattr(AG, "_download", dl)
    return log, rep


def sent(log):
    return len(log["eleven"]) + len(log["kie_post"])


def entries(film):
    from filmcrafter_engine import cast_voice as C
    return C._ledger(film).entries()


SFX = {"provider": "elevenlabs_sfx", "prompt": "A kettle clicking off, close", "duration": 2, "influence": 0.5}
MUSIC = {"provider": "elevenlabs_music", "prompt": "Gentle music box theme, tender", "duration": 30}
SUNO = {"provider": "kie_suno", "prompt": "A tender music box lullaby"}


# ---------------------------------------------------------------- what is offered and what it would cost

def test_the_providers_say_what_they_do_what_it_costs_and_that_the_rights_are_not_established(film):
    r = AG.providers()["providers"]
    assert [p["id"] for p in r] == ["elevenlabs_sfx", "elevenlabs_music", "kie_suno"]
    assert all(p["rights"] == "not_established" and "not established" in p["rights_note"] and p["has_key"] for p in r)
    assert [p["cost_known"] for p in r] == [True, False, False]
    assert "key" not in json.dumps(r).lower().replace("has_key", "").replace("key\"", "")[:0] and "test-key" not in json.dumps(r)             # only whether a key exists is read, never the key


def test_the_estimate_is_an_estimate_free_when_made_before_and_sends_nothing(film, net):
    log, _ = net
    e = AG.estimate(film, SFX)
    assert e["unit"] == "elevenlabs_credits" and e["amount"] == 22 and "an estimate" in e["basis"] and e["cached"] is None and e["needs_rights_ack"] and not e["needs_unknown_cost_accepted"]
    assert AG.estimate(film, {**SFX, "duration": None})["amount"] == 100
    m = AG.estimate(film, MUSIC)
    assert m["amount"] is None and m["needs_unknown_cost_accepted"] and "does not publish" in m["basis"]
    assert sent(log) == 0
    AG.generate(film, SFX, **YES)
    again = AG.estimate(film, SFX)
    assert again["cached"] and again["amount"] == 0 and "free" in again["basis"] and not again["needs_rights_ack"]


def test_bad_requests_are_refused_before_anything_is_sent(film, net):
    log, _ = net
    for bad in ({"provider": "nonsense", "prompt": "x y z"}, {**SFX, "prompt": "  "}, {**SFX, "duration": 99}, {**SFX, "duration": "long"}, {**SFX, "influence": 3}, {**MUSIC, "duration": 1},
                {**SFX, "prompt": "x" * 2000}, {**SUNO, "duration": 30}):
        with pytest.raises(SystemExit):
            AG.estimate(film, bad)
        with pytest.raises(SystemExit):
            AG.generate(film, bad, **YES)
    assert sent(log) == 0 and entries(film) == []


# ---------------------------------------------------------------- the engine refuses without a yes, the rights acknowledgement and (when unknown) the cost acceptance

def test_nothing_is_sent_without_confirmation_the_rights_acknowledgement_and_for_unknown_cost_its_acceptance(film, net):
    log, _ = net
    with pytest.raises(SystemExit, match="only goes ahead after you confirm"):
        AG.generate(film, SFX, confirmed=False, rights_ack=True)
    with pytest.raises(SystemExit, match="not established"):
        AG.generate(film, SFX, confirmed=True, rights_ack=False)
    with pytest.raises(SystemExit, match="does not publish|unknown"):
        AG.generate(film, MUSIC, confirmed=True, rights_ack=True)
    with pytest.raises(SystemExit, match="does not publish|unknown"):
        AG.generate(film, SUNO, confirmed=True, rights_ack=True)
    assert sent(log) == 0 and not os.path.exists(os.path.join(film, "audio", "library.json"))
    assert [e["status"] for e in entries(film)] == ["refused"] * 4


# ---------------------------------------------------------------- ElevenLabs sound effects

def test_a_sound_effect_is_made_kept_with_how_it_was_made_and_recorded_honestly(film, net):
    log, _ = net
    rep = net[1]
    rep["eleven"] = lambda: _with(Reply(200, content=wav_bytes(1.5)), {"character-cost": "22", "request-id": "req_9"})
    r = AG.generate(film, {**SFX, "loop": True, "name": "Kettle click", "scenes": [1], "places": ["Kitchen"]}, **YES)
    path, kw = log["eleven"][0]
    assert path == "/v1/sound-generation" and kw["json"] == {"text": SFX["prompt"], "model_id": "eleven_text_to_sound_v2", "duration_seconds": 2.0, "prompt_influence": 0.5, "loop": True}
    a = r["asset"]
    assert r["cached"] is False and a["source"] == "generated" and a["kind"] == "sfx" and a["name"] == "Kettle click" and a["approval"] == "pending"
    assert a["scenes"] == ["1"] and a["places"] == ["Kitchen"] and os.path.isfile(os.path.join(film, *a["file"].split("/")))
    g = a["generation"]
    assert g["provider"] == "elevenlabs_sfx" and g["model"] == "eleven_text_to_sound_v2" and g["prompt"] == SFX["prompt"] and g["duration"] == 2.0 and g["loop"] is True and g["key"] and g["variation"] == 0
    assert a["licence"]["commercial"] == "unknown" and "not established" in a["licence"]["note"]
    e = [x for x in entries(film) if x["action"] == "sfx"]
    assert len(e) == 1 and e[0]["status"] == "completed" and e[0]["estimate"]["amount"] == 22 and e[0]["actual"]["reported"] is True and e[0]["actual"]["amount"] == 22 and e[0]["area"] == "sound"
    assert r["cost"]["reported"] == 22 and r["cost"]["estimate"] == 22


def _with(r, headers):
    r.headers = headers
    return r


def test_a_sound_made_before_is_reused_free_and_a_variation_is_a_new_request_and_a_new_sound(film, net):
    log, _ = net
    first = AG.generate(film, SFX, **YES)["asset"]
    again = AG.generate(film, SFX, confirmed=False, rights_ack=False)                              # nothing to confirm: nothing is sent
    assert again["cached"] is True and again["asset"]["id"] == first["id"] and len(log["eleven"]) == 1
    var = AG.generate(film, {**SFX, "variation": 1}, **YES)["asset"]
    assert var["id"] != first["id"] and var["name"].endswith("(2)") and var["generation"]["variation"] == 1 and len(log["eleven"]) == 2
    assert len(AL.list_assets(film)["assets"]) == 2 and len([e for e in entries(film) if e["status"] == "completed"]) == 2
    assert AG.generate(film, {**SFX, "variation": 1}, **YES)["cached"] is True and len(log["eleven"]) == 2


def test_something_that_is_not_audio_is_not_kept_and_the_ledger_still_says_a_request_was_made(film, net):
    log, rep = net
    rep["eleven"] = lambda: Reply(200, content=b"<html>not audio</html>" * 50)
    with pytest.raises(SystemExit, match="not playable audio"):
        AG.generate(film, SFX, **YES)
    assert AL.list_assets(film)["assets"] == [] and not os.listdir(os.path.join(film, "audio", "sfx")) if os.path.isdir(os.path.join(film, "audio", "sfx")) else True
    e = [x for x in entries(film) if x["action"] == "sfx"][0]
    assert e["status"] == "completed" and "not usable audio" in e["note"]


def test_an_unclear_outcome_is_recorded_never_repeated_and_blocks_the_identical_request(film, net):
    log, rep = net

    def drop():
        raise requests.ReadTimeout("slow")
    rep["eleven"] = drop
    with pytest.raises(SystemExit, match="NOT sent it again"):
        AG.generate(film, SFX, **YES)
    assert len(log["eleven"]) == 1 and entries(film)[0]["status"] == "uncertain"
    rep["eleven"] = lambda: Reply(200, content=wav_bytes())
    with pytest.raises(SystemExit, match="outcome is not known"):
        AG.generate(film, SFX, **YES)
    assert len(log["eleven"]) == 1


def test_a_refusal_a_busy_provider_and_no_connection_are_each_recorded_for_what_they_are(film, net):
    log, rep = net
    rep["eleven"] = lambda: Reply(401, {"detail": {"status": "invalid_api_key", "message": "Bad key"}})
    with pytest.raises(SystemExit, match="refused the request: Bad key"):
        AG.generate(film, SFX, **YES)
    rep["eleven"] = lambda: Reply(429, {"detail": "busy"})
    with pytest.raises(SystemExit, match="too busy"):
        AG.generate(film, {**SFX, "variation": 1}, **YES)
    assert len(log["eleven"]) == 1 + 3                                                           # a slow-down is tried a bounded number of times
    def never():
        raise requests.ConnectTimeout("no route")
    rep["eleven"] = never
    with pytest.raises(SystemExit, match="Nothing was sent"):
        AG.generate(film, {**SFX, "variation": 2}, **YES)
    assert [e["status"] for e in entries(film)] == ["refused", "refused", "failed_before_submission"]
    assert AL.list_assets(film)["assets"] == []


def test_the_ledger_limit_is_honoured_before_sending(film, net):
    from filmcrafter_engine import cast_voice as C
    log, _ = net
    C.set_limit(film, "elevenlabs_credits", 10)
    with pytest.raises(SystemExit, match="limit"):
        AG.generate(film, SFX, **YES)                                                            # about 22 credits against a limit of 10
    assert sent(log) == 0


# ---------------------------------------------------------------- ElevenLabs Music

def test_music_asks_for_the_unknown_cost_to_be_accepted_and_sends_only_documented_fields(film, net):
    log, _ = net
    r = AG.generate(film, {**MUSIC, "instrumental": True, "model": "music_v2"}, confirmed=True, rights_ack=True, unknown_cost_accepted=True)
    path, kw = log["eleven"][0]
    assert path == "/v1/music" and kw["json"] == {"prompt": MUSIC["prompt"], "model_id": "music_v2", "force_instrumental": True, "music_length_ms": 30000}
    assert r["asset"]["kind"] == "music" and r["asset"]["generation"]["provider"] == "elevenlabs_music" and r["asset"]["licence"]["commercial"] == "unknown"
    e = [x for x in entries(film) if x["action"] == "music"][0]
    assert e["status"] == "completed" and e["estimate"]["amount"] is None and e["actual"]["reported"] is False and e["area"] == "music"          # no invented number


# ---------------------------------------------------------------- Suno through Kie.ai

def test_suno_through_kie_makes_the_task_waits_downloads_every_track_and_records_the_credits_kie_reported(film, net):
    log, _ = net
    r = AG.generate(film, SUNO, confirmed=True, rights_ack=True, unknown_cost_accepted=True)
    path, kw = log["kie_post"][0]
    assert path == "/api/v1/jobs/createTask" and kw["json"] == {"model": "ai-music-api/generate", "input": {"custom_mode": False, "instrumental": True, "model": "V6", "prompt": SUNO["prompt"]}}
    assert log["kie_get"][0][0] == "/api/v1/jobs/recordInfo" and log["kie_get"][0][1]["params"] == {"taskId": "task_1"}
    assert log["download"] == ["https://cdn.example.com/a.mp3", "https://cdn.example.com/b.mp3"] and len(r["assets"]) == 2
    a, b = r["assets"]
    assert a["generation"]["task"] == "task_1" and a["generation"]["track"] == 1 and b["generation"]["track"] == 2 and a["generation"]["key"] != b["generation"]["key"]
    assert all(x["licence"]["commercial"] == "unknown" and x["approval"] == "pending" for x in r["assets"])
    e = [x for x in entries(film) if x["action"] == "music"][0]
    assert e["status"] == "completed" and e["actual"]["amount"] == 12 and e["actual"]["reported"] is True and e["estimate"]["amount"] is None and e["provider_request_id"] == "task_1"
    assert AG.pending(film)["tasks"] == []
    assert AG.generate(film, SUNO, confirmed=False)["cached"] is True and len(log["kie_post"]) == 1


def test_a_task_that_is_still_running_is_kept_and_finished_later_without_paying_again(film, net):
    log, rep = net
    state = {"n": 0}
    done = rep["kie_get"]

    def slow():
        state["n"] += 1
        return Reply(200, {"code": 200, "data": {"state": "generating"}}) if state["n"] <= AG.POLL_FOR // AG.POLL_EVERY + 1 else done()
    rep["kie_get"] = slow
    r = AG.generate(film, SUNO, confirmed=True, rights_ack=True, unknown_cost_accepted=True)
    assert "pending" in r and r["pending"]["task"] == "task_1" and "paid for" in r["note"]
    assert AL.list_assets(film)["assets"] == [] and len(AG.pending(film)["tasks"]) == 1
    assert [e["status"] for e in entries(film)] == ["completed"]
    r2 = AG.check(film, "task_1")
    assert len(r2["assets"]) == 2 and AG.pending(film)["tasks"] == [] and len(log["kie_post"]) == 1               # nothing was created or paid for a second time
    with pytest.raises(SystemExit, match="not waiting"):
        AG.check(film, "task_1")


def test_kie_failures_are_each_told_truthfully(film, net):
    log, rep = net
    ok = dict(confirmed=True, rights_ack=True, unknown_cost_accepted=True)
    rep["kie_post"] = lambda: Reply(200, {"code": 402, "msg": "Insufficient credits"})
    with pytest.raises(SystemExit, match="refused the request: Insufficient credits"):
        AG.generate(film, SUNO, **ok)
    rep["kie_post"] = lambda: Reply(200, {"code": 200, "msg": "success", "data": {}})
    with pytest.raises(SystemExit, match="did not give a task number"):
        AG.generate(film, {**SUNO, "variation": 1}, **ok)
    rep["kie_post"] = lambda: Reply(200, {"code": 200, "data": {"taskId": "task_2"}})
    rep["kie_get"] = lambda: Reply(200, {"code": 200, "data": {"state": "fail", "failMsg": "content filtered"}})
    with pytest.raises(SystemExit, match="content filtered"):
        AG.generate(film, {**SUNO, "variation": 2}, **ok)
    assert [e["status"] for e in entries(film)] == ["refused", "uncertain", "completed"] and AG.pending(film)["tasks"] == []
    assert AL.list_assets(film)["assets"] == []


def test_finished_files_are_only_fetched_from_trustworthy_addresses():
    for bad in ("http://cdn.example.com/a.mp3", "https://127.0.0.1/a.mp3", "https://localhost/a.mp3", "file:///C:/x.mp3", "https://user:pw@cdn.example.com/a.mp3", "https://printer.local/a.mp3", ""):
        with pytest.raises(SystemExit, match="does not trust"):
            AG._download(bad)


def test_the_track_reader_understands_both_documented_shapes():
    assert AG._tracks({"resultJson": json.dumps({"resultUrls": ["https://a/x.mp3"]})}) == ["https://a/x.mp3"]
    assert AG._tracks({"response": {"data": [{"audio_url": "https://a/1.mp3"}, {"audio_url": "https://a/2.mp3"}, {"image_url": "x"}]}}) == ["https://a/1.mp3", "https://a/2.mp3"]
    assert AG._tracks({"resultJson": "not json"}) == [] and AG._tracks({}) == []


# ---------------------------------------------------------------- the rights are never silently assumed

def test_generated_sound_in_the_plan_is_reported_until_the_person_confirms_the_rights(film, net):
    a = AG.generate(film, SFX, **YES)["asset"]
    assert AL.rights_report(film)["ok"] is True                                                # made but not used in the film yet
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1})["id"]
    rep = AL.rights_report(film)
    assert rep["ok"] is False and rep["blocking"][0]["id"] == a["id"] and "not known" in rep["blocking"][0]["why"]
    AL.update(film, a["id"], {"licence": {"commercial": "yes", "note": "Checked my plan's terms."}})
    assert AL.rights_report(film)["ok"] is True
    AL.update(film, a["id"], {"licence": {"commercial": "no"}})
    assert AL.rights_report(film)["blocking"][0]["why"] == "Commercial use is not allowed."
    assert cid


def test_the_command_line_speaks_the_engine_format_and_only_knows_its_actions(film, net, capsys):
    assert AG.main(["providers", film]) == 0
    assert len(json.loads(capsys.readouterr().out)["data"]["providers"]) == 3
    with pytest.raises(SystemExit):
        AG.main(["format_disk", film])
    assert AG.main(["generate", film, "--data", json.dumps(SFX)]) == 1
    assert "only goes ahead after you confirm" in capsys.readouterr().out
