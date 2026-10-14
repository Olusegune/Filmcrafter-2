"""Spending on ElevenLabs is safe: the engine itself refuses without confirmation, every paid call is recorded honestly, an ambiguous outcome is never repeated by itself,
a crash leaves a truthful record, and a limit stops spending before anything is sent. ElevenLabs is faked throughout: nothing here spends or sends anything."""
import json
import multiprocessing as mp
import os
import time

import pytest
import requests
import urllib3

from filmcrafter_engine import cast_voice as C, paidops as P, voiceover as V
from tests.test_cast_voice import Reply, VID, calls, film, give_voice, lila_shot, wav_bytes  # noqa: F401  (fixtures)

TTS = f"/v1/text-to-speech/{VID}"


def posts(log, part):
    return [c for c in log if c[0] == "POST" and part in c[1]]


def ledger(film):
    return C._ledger(film)


def entries(film, action=None):
    return [e for e in ledger(film).entries() if action in (None, e["action"])]


def design_reply():
    import base64
    return Reply(200, {"previews": [{"generated_voice_id": "prev_abc123", "audio_base_64": base64.b64encode(wav_bytes()).decode(), "media_type": "audio/mpeg", "duration_secs": 1.5}], "text": "x"})


# ---------------------------------------------------------------- the engine refuses without confirmation

def test_every_paid_action_is_refused_by_the_engine_when_not_confirmed_and_nothing_is_sent(film, calls, tmp_path):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    sample = tmp_path / "me.wav"
    sample.write_bytes(wav_bytes())
    desc = "A warm older woman with a gentle northern accent, kind and a little tired."
    attempts = [
        lambda: C.speak(film, sid, "Lila"),
        lambda: C.speak(film, sid, "Lila", confirmed="yes"),                       # only the boolean True counts
        lambda: C.preview(film, "Lila"),
        lambda: C.design(film, desc),
        lambda: C.design_save(film, "Lila", "prev_abc123", "n", "d"),
        lambda: C.clone(film, "Lila", "Me", [str(sample)], consent=True),
    ]
    for go in attempts:
        with pytest.raises(SystemExit, match="Confirm the price first"):
            go()
    assert [c for c in log if c[0] == "POST"] == []                                  # not one request left this computer
    refused = entries(film)
    assert len(refused) == len(attempts) and {e["status"] for e in refused} == {P.REFUSED}
    assert all(e["confirmed"] is False for e in refused)


def test_a_design_must_also_accept_that_its_cost_is_unknown(film, calls):
    log, replies = calls
    desc = "A warm older woman with a gentle northern accent, kind and a little tired."
    with pytest.raises(SystemExit, match="does not publish"):
        C.design(film, desc, confirmed=True)                                         # confirmed, but the unknown cost was not accepted
    assert posts(log, "design") == []
    replies["/v1/text-to-voice/design"] = design_reply()
    C.design(film, desc, confirmed=True, unknown_cost_accepted=True)
    e = entries(film, "design")[-1]
    assert e["status"] == P.COMPLETED and e["estimate"]["unit"] == "unknown" and e["estimate"]["amount"] is None      # no fabricated number


def test_consent_and_spending_are_separate_permissions_and_both_are_needed(film, calls, tmp_path):
    log, replies = calls
    sample = tmp_path / "me.wav"
    sample.write_bytes(wav_bytes())
    with pytest.raises(SystemExit, match="right to clone"):
        C.clone(film, "Lila", "Me", [str(sample)], consent=False, confirmed=True)  # may spend, but no consent to use the voice
    with pytest.raises(SystemExit, match="Confirm the price first"):
        C.clone(film, "Lila", "Me", [str(sample)], consent=True, confirmed=False)  # consent given, but not allowed to spend
    assert [c for c in log if c[0] == "POST"] == []
    replies["/v1/voices/add"] = Reply(200, {"voice_id": VID})
    C.clone(film, "Lila", "Me", [str(sample)], consent=True, confirmed=True)
    e = entries(film, "clone")[-1]
    assert e["status"] == P.COMPLETED and e["consent"] is True and e["estimate"]["unit"] == "voice_slot"


def test_a_cancelled_operation_makes_no_request_and_leaves_no_charge(film, calls):
    """The screen's Cancel simply never calls the engine; and if the engine is called unconfirmed it refuses. Either way nothing is sent."""
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    est = C.estimate(film, [{"shot": sid, "speaker": "Lila"}])                      # looking at the price is free
    assert est["rows"][0]["credits"] > 0 and [c for c in log if c[0] == "POST"] == [] and entries(film) == []


# ---------------------------------------------------------------- the ledger tells the truth

def test_a_completed_speak_is_recorded_with_its_estimate_and_no_invented_actual(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film, model="eleven_flash_v2_5")
    replies[TTS] = Reply(200, content=wav_bytes())
    out = C.speak(film, sid, "Lila", confirmed=True)
    e = entries(film, "speak")[-1]
    assert e["status"] == P.COMPLETED and e["provider"] == "elevenlabs" and e["person"] == "Lila" and e["shot"] == sid
    assert e["estimate"] == {"unit": "elevenlabs_credits", "amount": out["credits"], "basis": e["estimate"]["basis"]} and out["credits"] == round(len("It looked weird.") * 0.5)
    assert e["actual"]["reported"] is False and e["actual"]["amount"] is None        # ElevenLabs did not report an amount, so none is claimed
    assert [h["status"] for h in e["history"]][:4] == [P.PREPARED, P.CONFIRMED, P.SUBMITTED, P.COMPLETED] and e["asset"].startswith("voice/_generated/")


def test_what_elevenlabs_reports_is_kept_and_labelled_as_reported(film, calls, monkeypatch):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    r = Reply(200, content=wav_bytes())
    r.headers = {"request-id": "req_123", "character-cost": "16"}
    replies[TTS] = r
    C.speak(film, sid, "Lila", confirmed=True)
    e = entries(film, "speak")[-1]
    assert e["provider_request_id"] == "req_123" and e["actual"] == {"unit": "elevenlabs_credits", "amount": 16.0, "reported": True, "source": "ElevenLabs response header"}
    s = C.usage(film)["by_unit"]["elevenlabs_credits"]
    assert s["reported"] == 16.0 and s["unreported_operations"] == 0


def test_the_summary_never_adds_an_estimate_to_a_reported_amount(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.speak(film, sid, "Lila", confirmed=True)
    s = C.usage(film)["by_unit"]["elevenlabs_credits"]
    assert s["operations"] == 1 and s["reported"] == 0 and s["unreported_operations"] == 1 and s["estimated"] > 0           # estimate and actual stay apart


def test_a_line_already_spoken_is_free_makes_no_request_and_adds_no_ledger_entry(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.speak(film, sid, "Lila", confirmed=True)
    again = C.speak(film, sid, "Lila")                                              # no confirmation needed: nothing is sent
    assert again["cached"] is True and len(posts(log, "text-to-speech")) == 1 and len(entries(film, "speak")) == 1


def test_the_ledger_never_holds_a_credential(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.speak(film, sid, "Lila", confirmed=True)
    assert "test-key-not-real" not in open(os.path.join(film, "voice", "ledger.json"), encoding="utf-8").read()


# ---------------------------------------------------------------- retries only on evidence the request was not accepted

def test_an_ambiguous_5xx_is_recorded_as_uncertain_and_never_sent_again(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    r = Reply(503, {"detail": "busy"})
    r.headers = {"request-id": "req_503"}
    replies[TTS] = r
    with pytest.raises(SystemExit, match="NOT sent it again"):
        C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 1                                    # exactly one request, no automatic repeat
    e = entries(film, "speak")[-1]
    assert e["status"] == P.UNCERTAIN and e["provider_request_id"] == "req_503"
    assert C.usage(film)["unresolved"][0]["id"] == e["id"]                          # and it stays visible until the person settles it
    assert not os.path.exists(C._cache(film, sid, "It looked weird.", C._cast(film)["people"]["lila"]))   # nothing was attached or cached


@pytest.mark.parametrize("exc", [requests.exceptions.ReadTimeout("read timed out"), requests.exceptions.ConnectionError("Connection aborted.", ConnectionResetError(10054, "reset")),
                                 requests.exceptions.ChunkedEncodingError("incomplete")])
def test_a_timeout_or_dropped_connection_after_sending_is_uncertain_not_retried(film, calls, exc):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)

    def boom():
        raise exc
    replies[TTS] = boom
    with pytest.raises(SystemExit, match="NOT sent it again"):
        C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 1 and entries(film, "speak")[-1]["status"] == P.UNCERTAIN


def _never_connected():
    inner = urllib3.exceptions.NewConnectionError(None, "Failed to establish a new connection")
    return requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(None, "/v1/x", reason=inner))


@pytest.mark.parametrize("exc", [requests.exceptions.ConnectTimeout("connect timed out"), _never_connected(), requests.exceptions.SSLError("handshake failed")])
def test_a_connection_that_was_never_made_is_safe_to_try_again(film, calls, exc):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    seq = [exc, Reply(200, content=wav_bytes())]

    def go():
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    replies[TTS] = go
    C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 2 and entries(film, "speak")[-1]["status"] == P.COMPLETED
    assert len(entries(film, "speak")) == 1                                          # one operation, one entry, despite the retry


def test_when_it_never_connects_at_all_nothing_is_charged_and_the_record_says_so(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)

    def down():
        raise requests.exceptions.ConnectTimeout("connect timed out")
    replies[TTS] = down
    with pytest.raises(SystemExit, match="Nothing was sent"):
        C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 3                                    # the first try and two more: bounded
    assert entries(film, "speak")[-1]["status"] == P.FAILED_BEFORE


def test_a_provider_refusal_is_recorded_as_refused_and_not_retried(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(422, {"detail": [{"msg": "text too long"}]})
    with pytest.raises(SystemExit, match="could not speak"):
        C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 1 and entries(film, "speak")[-1]["status"] == P.REFUSED


def test_a_persistent_slow_down_is_bounded_and_ends_refused(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(429, {"detail": "slow down"})
    with pytest.raises(SystemExit, match="too busy"):
        C.speak(film, sid, "Lila", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 3 and entries(film, "speak")[-1]["status"] == P.REFUSED


def test_creating_things_is_never_retried_automatically(film, calls):
    log, replies = calls
    replies["/v1/text-to-voice/design"] = Reply(429, {"detail": "slow down"})
    with pytest.raises(SystemExit):
        C.design(film, "A warm older woman with a gentle northern accent, kind and a little tired.", confirmed=True, unknown_cost_accepted=True)
    assert len(posts(log, "design")) == 1


# ---------------------------------------------------------------- an unknown outcome blocks an identical request until the person settles it

def test_an_identical_request_is_blocked_until_the_uncertain_one_is_settled_by_the_person(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(503, {"detail": "busy"})
    with pytest.raises(SystemExit):
        C.speak(film, sid, "Lila", confirmed=True)
    replies[TTS] = Reply(200, content=wav_bytes())
    with pytest.raises(SystemExit, match="will not send it again on its own"):
        C.speak(film, sid, "Lila", confirmed=True)                                   # even a confirmed repeat is blocked
    assert len(posts(log, "text-to-speech")) == 1
    op = entries(film, "speak")[0]
    with pytest.raises(SystemExit):
        C.ledger_resolve(film, op["id"], "maybe")                                    # only the two real answers
    C.ledger_resolve(film, op["id"], "not_charged")                                  # the person checked ElevenLabs' usage page
    C.speak(film, sid, "Lila", confirmed=True)                                       # now it may go
    assert len(posts(log, "text-to-speech")) == 2
    assert C.usage(film)["unresolved"] == []
    kept = [e for e in entries(film, "speak") if e["status"] == P.UNCERTAIN]
    assert len(kept) == 1 and kept[0]["resolved"]["outcome"] == "not_charged"        # the uncertain entry stays in the record, annotated


def test_an_uncertain_operation_marked_charged_counts_as_used(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(503, {"detail": "busy"})
    with pytest.raises(SystemExit):
        C.speak(film, sid, "Lila", confirmed=True)
    C.ledger_resolve(film, entries(film, "speak")[0]["id"], "charged")
    assert C.usage(film)["by_unit"]["elevenlabs_credits"]["operations"] == 1


def test_only_an_uncertain_operation_can_be_marked(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.speak(film, sid, "Lila", confirmed=True)
    with pytest.raises(SystemExit, match="outcome was unknown"):
        C.ledger_resolve(film, entries(film, "speak")[0]["id"], "not_charged")


# ---------------------------------------------------------------- a crash leaves a truthful record

def test_what_a_crash_left_half_way_is_settled_truthfully(film):
    L = ledger(film)
    est = {"unit": "elevenlabs_credits", "amount": 10, "basis": "x"}
    a = L.begin(key="a", provider="elevenlabs", area="voice", action="speak", estimate=est)            # confirmed, never sent
    b = L.begin(key="b", provider="elevenlabs", area="voice", action="speak", estimate=est)
    L.mark(b["id"], P.SUBMITTED)                                                    # sent, then the app died
    c = L.begin(key="c", provider="elevenlabs", area="voice", action="speak", estimate=est)            # just made: still in progress
    old = time.time() - 3600

    def age(data):
        for e in data["entries"]:
            if e["id"] in (a["id"], b["id"]):
                e["updated"] = int(old)
    from filmcrafter_engine import safeio
    safeio.update_json(ledger(film).path, age)
    assert L.reconcile() == 2
    got = {e["id"]: e for e in L.entries()}
    assert got[a["id"]]["status"] == P.FAILED_BEFORE                                # it never reached the provider: nothing charged
    assert got[b["id"]]["status"] == P.UNCERTAIN and "closed while this was being sent" in got[b["id"]]["note"]
    assert got[c["id"]]["status"] == P.CONFIRMED                                    # a request that is genuinely in progress is left alone
    assert C.usage(film)["unresolved"][0]["id"] == b["id"]


def test_the_same_operation_cannot_be_started_twice_at_once(film):
    L = ledger(film)
    est = {"unit": "elevenlabs_credits", "amount": 10, "basis": "x"}
    L.begin(key="same", provider="elevenlabs", area="voice", action="speak", estimate=est)
    with pytest.raises(SystemExit, match="being sent right now"):
        L.begin(key="same", provider="elevenlabs", area="voice", action="speak", estimate=est)
    assert len(L.entries()) == 1                                                    # and the refusal added no duplicate


def _begin_many(args):
    path, film_name, who, n = args
    L = P.Ledger(path, film=film_name)
    for i in range(n):
        L.begin(key=f"{who}-{i}", provider="elevenlabs", area="voice", action="speak", estimate={"unit": "elevenlabs_credits", "amount": 1, "basis": ""})
    return who


def test_entries_from_several_processes_at_once_are_all_kept(tmp_path):
    path = str(tmp_path / "ledger.json")
    with mp.get_context("spawn").Pool(4) as pool:
        pool.map(_begin_many, [(path, "T", f"p{n}", 15) for n in range(4)])
    es = P.Ledger(path).entries()
    assert len(es) == 60 and len({e["id"] for e in es}) == 60 and len({e["key"] for e in es}) == 60


# ---------------------------------------------------------------- a spending limit stops spending before anything is sent

def test_a_limit_refuses_what_would_pass_it_before_anything_is_sent(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.set_limit(film, "elevenlabs_credits", 20)
    C.speak(film, sid, "Lila", confirmed=True)                                       # 16 credits: within 20
    with pytest.raises(SystemExit, match="past 20 elevenlabs credits"):
        C.speak(film, sid, "Lila", text="Another line that is long enough to pass the limit.", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 1
    C.set_limit(film, "elevenlabs_credits", None)
    C.speak(film, sid, "Lila", text="Another line that is long enough to pass the limit.", confirmed=True)
    assert len(posts(log, "text-to-speech")) == 2


def test_limits_are_per_unit_and_only_for_units_elevenlabs_uses(film):
    with pytest.raises(SystemExit):
        C.set_limit(film, "dollars", 5)
    with pytest.raises(SystemExit):
        C.set_limit(film, "elevenlabs_credits", -3)
    assert C.set_limit(film, "voice_slot", 3)["limits"] == {"voice_slot": 3.0}


# ---------------------------------------------------------------- compatibility with what films already hold

def test_existing_voices_and_assignments_survive_the_new_safeguards(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[TTS] = Reply(200, content=wav_bytes())
    C.speak(film, sid, "Lila", confirmed=True)
    before = (V.status(film), C.status(film)["people"])
    assert "lila" in before[1] and any(p["recording"] for s in before[0]["shots"] for p in s["people"])
    assert C.status(film)["people"] == before[1] and V.status(film) == before[0]
    assert not os.path.exists(os.path.join(film, "voice", "ledger.json.corrupt")) and C.takes(film, sid, "Lila")["takes"]


def test_an_older_film_with_no_ledger_works_and_a_ledger_appears_only_when_something_is_paid(film, calls):
    log, replies = calls
    give_voice(film)
    assert not os.path.exists(os.path.join(film, "voice", "ledger.json"))
    assert C.usage(film)["count"] == 0


def test_a_damaged_voice_file_stops_voice_work_instead_of_being_overwritten(film, calls, tmp_path):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    mine = tmp_path / "mine.wav"
    mine.write_bytes(wav_bytes())
    V.attach(film, sid, "Lila", str(mine))
    p = V._meta_path(film)
    good = open(p, "rb").read()
    os.remove(p + ".bak") if os.path.exists(p + ".bak") else None
    open(p, "wb").write(b'{"schema": 1, "shots": {"S01-0')
    from filmcrafter_engine import safeio
    with pytest.raises(safeio.SafeIOError, match="damaged"):
        V.status(film)
    with pytest.raises(safeio.SafeIOError):
        V.attach(film, sid, "Lila", str(mine))
    assert open(p, "rb").read() == b'{"schema": 1, "shots": {"S01-0'              # not replaced by an empty record
    assert any(f.startswith("voice.json.corrupt-") for f in os.listdir(os.path.dirname(p)))
    assert good                                                                     # (the good copy existed before the damage)


def test_a_damaged_voice_file_is_restored_from_its_backup(film, calls, tmp_path):
    sid = lila_shot(film)
    mine, other = tmp_path / "mine.wav", tmp_path / "other.wav"
    mine.write_bytes(wav_bytes())
    other.write_bytes(wav_bytes(1.0))
    V.attach(film, sid, "Lila", str(mine))
    V.attach(film, sid, "Lila", str(other))                                         # the second save makes the first state the backup
    p = V._meta_path(film)
    open(p, "wb").write(b"{")
    st = V.status(film)                                                             # read: restored from the backup, nothing lost silently
    assert any(pp["recording"] for s in st["shots"] for pp in s["people"])
    assert any(f.startswith("voice.json.corrupt-") for f in os.listdir(os.path.dirname(p)))


def _attach_worker(args):
    film, sid, who, wav = args
    V.attach(film, sid, who, wav, fit=False)
    return who


def test_two_recordings_attached_at_the_same_moment_are_both_kept(film, tmp_path):
    sid = next(s["id"] for s in V.status(film)["shots"] if len(s["people"]) >= 2 or True)
    people = [p["name"] for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"]] + [o for s in V.status(film)["shots"] if s["id"] == sid for o in s["others"]]
    assert len(people) >= 2
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(wav_bytes(1.0))
    b.write_bytes(wav_bytes(1.2))
    with mp.get_context("spawn").Pool(2) as pool:
        pool.map(_attach_worker, [(film, sid, people[0], str(a)), (film, sid, people[1], str(b))])
    got = [p for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"] if p["recording"]]
    assert {p["name"] for p in got} == {people[0], people[1]}
