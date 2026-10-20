"""Bringing in a filmmaker's own materials: storyboards (files, folders, zips, PDFs), asset sheets, shot lists and notes. Real files, real film folder, no provider, nothing spent."""
import hashlib
import json
import os
import zipfile

import pytest
from PIL import Image

from filmcrafter_engine import bible, make as M, materials as MT, shots as S, story

SCRIPT = ("INT. KITCHEN - NIGHT\n\nSarah pours tea. Rain on the roof.\n\nSARAH\nHe said he would call.\n\nJOHN\nDid you say something?\n\n"
          "EXT. YARD - DAY\n\nChildren play in the schoolyard. Sarah watches from the fence.\n\nSARAH\nI am going.\n")


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def pic(path, color=(200, 30, 30), size=(320, 180)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def hashes(root):
    out = {}
    for r, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(r, f)
            out[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


def ids(film):
    return [c["id"] for c in MT._shots(film)]


def shot(film, sid):
    c = S.get_shot(film, sid)
    return c.get("shot", c)


def test_scan_changes_nothing_in_the_film_and_applies_nothing(film, tmp_path):
    src = tmp_path / "mat"
    pic(str(src / "storyboard" / "01.png"))
    cache = os.sep + "cache" + os.sep
    before = {k: v for k, v in hashes(film).items() if cache not in k}
    plan = MT.scan(film, [str(src)])
    after = {k: v for k, v in hashes(film).items() if cache not in k}
    assert before == after and plan["items"] and plan["token"]


def test_storyboard_panels_named_by_shot_go_to_those_shots(film, tmp_path):
    sid = ids(film)
    src = tmp_path / "mat" / "storyboard"
    pic(str(src / f"{sid[1]}.png"), (10, 200, 10))
    pic(str(src / f"{sid[0]}.jpg"), (10, 10, 200))
    plan = MT.scan(film, [str(src)])
    by = {i["shot"]: i for i in plan["items"] if i["type"] == "storyboard"}
    assert set(by) == {sid[0], sid[1]} and all(i["on"] and i["how"] == "the file name" for i in by.values())
    res = MT.apply(film, plan["token"], {})
    assert len(res["applied"]) == 2 and not res["failed"]
    board = json.load(open(os.path.join(film, "storyboard.json")))
    assert set(board) == {sid[0], sid[1]}
    for rel in board.values():                                             # the render project holds its own copy
        assert os.path.isfile(os.path.join(film, "render", rel))
    assert os.path.isdir(os.path.join(film, "backups"))                    # a snapshot was taken first
    assert MT.history(film)["imports"][0]["applied"]


def test_panels_in_order_are_matched_only_when_the_counts_agree(film, tmp_path):
    n = len(ids(film))
    ok = tmp_path / "ok" / "storyboard"
    for i in range(n):
        pic(str(ok / f"panel {i + 1:02d}.png"))
    plan = MT.scan(film, [str(ok)])
    boards = [i for i in plan["items"] if i["type"] == "storyboard"]
    assert [b["shot"] for b in boards] == ids(film) and all(b["on"] and b["how"] == "their order" for b in boards)
    few = tmp_path / "few" / "storyboard"
    for i in range(n - 1):
        pic(str(few / f"p{i + 1}.png"))
    plan = MT.scan(film, [str(few)])
    boards = [i for i in plan["items"] if i["type"] == "storyboard"]
    assert all(not b["on"] and "say which shot" in b["blocked"] for b in boards)
    assert MT.apply(film, plan["token"], {})["applied"] == []              # nothing ticked and blocked: nothing is added
    choices = {b["id"]: {"target": ids(film)[k], "on": True} for k, b in enumerate(boards)}
    res = MT.apply(film, plan["token"], choices)                           # the person says which shot each belongs to
    assert len(res["applied"]) == n - 1


def test_a_chosen_or_locked_panel_is_not_replaced_unless_ticked_and_a_lock_is_never_overridden(film, tmp_path):
    sid = ids(film)
    first = tmp_path / "a" / "storyboard"
    pic(str(first / f"{sid[0]}.png"))
    MT.apply(film, MT.scan(film, [str(first)])["token"], {})
    old = json.load(open(os.path.join(film, "storyboard.json")))[sid[0]]
    again = tmp_path / "b" / "storyboard"
    pic(str(again / f"{sid[0]}.png"), (1, 2, 3))
    plan = MT.scan(film, [str(again)])
    it = plan["items"][0]
    assert not it["on"] and it.get("replaces")
    MT.apply(film, plan["token"], {})
    assert json.load(open(os.path.join(film, "storyboard.json")))[sid[0]] == old       # untouched
    MT.apply(film, plan["token"], {it["id"]: {"on": True}})
    assert json.load(open(os.path.join(film, "storyboard.json")))[sid[0]] != old
    M.lock(film, sid[0], "storyboard", True)
    plan = MT.scan(film, [str(again)])
    assert plan["items"][0]["blocked"].startswith("This shot's storyboard is locked")
    assert MT.apply(film, plan["token"], {plan["items"][0]["id"]: {"on": True}})["applied"] == []


def test_asset_sheets_go_to_the_right_cast_place_or_prop_and_new_ones_only_when_named(film, tmp_path):
    src = tmp_path / "mat"
    pic(str(src / "characters" / "Sarah" / "front.png"), (1, 1, 1))
    pic(str(src / "characters" / "Sarah" / "side view.png"), (2, 2, 2))
    pic(str(src / "characters" / "Mama Ada - turnaround.png"), (3, 3, 3))
    pic(str(src / "locations" / "Kitchen.jpg"), (4, 4, 4))
    pic(str(src / "props" / "Red Kettle.png"), (5, 5, 5))
    pic(str(src / "mystery.png"), (6, 6, 6))
    plan = MT.scan(film, [str(src)])
    by = {i["rel"].split("/", 1)[1]: i for i in plan["items"]}
    sarah = [i for i in plan["items"] if i.get("entry_name") == "Sarah"]
    assert len(sarah) == 2 and {i["media_kind"] for i in sarah} == {"front", "side"}
    ada = by["characters/Mama Ada - turnaround.png"]
    assert ada["create"] and ada["name"] == "Mama Ada" and ada["media_kind"] == "master"
    assert by["props/Red Kettle.png"]["kind"] == "prop" and by["props/Red Kettle.png"]["create"]
    assert by["mystery.png"]["type"] == "unsorted" and not by["mystery.png"]["on"]
    res = MT.apply(film, plan["token"], {})
    assert not res["failed"]
    b = bible.load(film)
    s = next(c for c in b["characters"] if c["name"] == "Sarah")
    assert len(s["media"]) == 2 and {m["kind"] for m in s["media"]} == {"front", "side"}
    assert any(c["name"] == "Mama Ada" and c["media"] for c in b["characters"])
    assert any(p["name"] == "Red Kettle" and p["media"] for p in b["props"])
    assert not any("mystery" in json.dumps(x).lower() for x in b["characters"])        # the unsorted picture went nowhere
    plan2 = MT.scan(film, [str(src / "characters")])                           # the same picture twice is not added twice
    dup = [i for i in plan2["items"] if i.get("entry_name") == "Sarah"]
    assert len(dup) == 2 and all(not i["on"] and "already has this exact picture" in i["blocked"] for i in dup)


def test_a_picture_can_be_told_what_it_is(film, tmp_path):
    src = tmp_path / "mat"
    pic(str(src / "mystery.png"))
    plan = MT.scan(film, [str(src)])
    iid = plan["items"][0]["id"]
    res = MT.apply(film, plan["token"], {iid: {"as": "character", "new_name": "Zed", "on": True}})
    assert len(res["applied"]) == 1 and any(c["name"] == "Zed" and c["media"] for c in bible.load(film)["characters"])


def test_a_shot_list_fills_the_shots_and_keeps_what_the_person_wrote(film, tmp_path):
    sid = ids(film)
    S.set_fields(film, sid[1], {"action": "My own words for this shot."})
    csv_text = ("Shot,Scene,Shot Size,Camera Movement,Duration,Description,Dialogue,Notes\n"
                "1,1,CU,push in,4,Her hands on the cup,Sarah line,keep it quiet\n"
                "2,1,WS,static,5,A different description,,\n"
                "9,9,MS,,3,Nowhere,,\n")
    p = tmp_path / "list.csv"
    p.write_text(csv_text, encoding="utf-8")
    plan = MT.scan(film, [str(p)])
    rows = {i["shot"]: i for i in plan["items"] if i["type"] == "shotrow"}
    first, second = rows[sid[0]], rows[sid[1]]
    assert first["on"] and {c["label"] for c in first["changes"]} >= {"Framing", "Movement", "Length (s)", "What happens"}
    assert not second["on"] and "What happens" in second["notes"][0]                  # would replace the person's words: needs a tick
    assert any(i["type"] == "skip" and "No shot" in i["blocked"] for i in plan["items"])
    MT.apply(film, plan["token"], {})
    c1, c2 = shot(film, sid[0]), shot(film, sid[1])
    assert c1["camera"]["framing"] == "close-up" and c1["camera"]["movement"] == "push in" and c1["generation"]["duration"] == 4.0 and c1["generation"]["notes"] == "keep it quiet"
    assert c2["action"] == "My own words for this shot."                             # untouched until ticked
    assert c2["camera"]["framing"] != "wide"                                          # the whole row waits for a tick, not just the field in question
    MT.apply(film, plan["token"], {second["id"]: {"on": True}})
    c2 = shot(film, sid[1])
    assert c2["action"] == "A different description" and c2["camera"]["framing"] == "wide"


def test_unknown_camera_words_are_kept_as_a_note_not_lost_or_refused(film, tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("Shot,Scene,Shot Size,Description\n1,1,Cowboy shot,Hands\n", encoding="utf-8")
    plan = MT.scan(film, [str(p)])
    MT.apply(film, plan["token"], {})
    assert "Cowboy shot" in shot(film, ids(film)[0])["generation"]["notes"]


def test_a_new_shot_is_added_only_when_ticked(film, tmp_path):
    n = len(ids(film))
    p = tmp_path / "l.csv"
    p.write_text("Scene,Shot,Description,Shot Size\n1,9,An extra insert of the kettle,insert\n", encoding="utf-8")
    plan = MT.scan(film, [str(p)])
    it = plan["items"][0]
    assert it["type"] == "newshot" and not it["on"]
    MT.apply(film, plan["token"], {})
    assert len(ids(film)) == n
    MT.apply(film, plan["token"], {it["id"]: {"on": True}})
    assert len(ids(film)) == n + 1


def test_notes_are_kept_and_can_be_added_to_the_bible_without_replacing_it(film, tmp_path):
    bible.update_rules(film, {"rules": {"tone": "Quiet and grey."}})
    d = tmp_path / "n"
    d.mkdir()
    (d / "tone.md").write_text("Warm, patient, handheld.", encoding="utf-8")
    (d / "research.txt").write_text("Facts about kettles.", encoding="utf-8")
    plan = MT.scan(film, [str(d)])
    tone = next(i for i in plan["items"] if i["rel"].endswith("tone.md"))
    assert tone["target"] == "tone" and next(i for i in plan["items"] if i["rel"].endswith("research.txt"))["target"] == "keep"
    MT.apply(film, plan["token"], {})
    assert bible.load(film)["rules"]["tone"] == "Quiet and grey.\n\nWarm, patient, handheld."
    assert os.path.isfile(os.path.join(film, "materials", "notes", "tone.md")) and os.path.isfile(os.path.join(film, "materials", "notes", "research.txt"))


def test_a_zip_is_opened_safely_and_a_bad_one_is_refused(film, tmp_path):
    sid = ids(film)
    src = pic(str(tmp_path / "x" / f"{sid[0]}.png"))
    z = tmp_path / "boards.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src, f"storyboard/{sid[0]}.png")
        zf.writestr("../evil.png", open(src, "rb").read())
        zf.writestr("/abs/evil2.png", open(src, "rb").read())
        zf.writestr("readme.exe", b"MZ")
    plan = MT.scan(film, [str(z)])
    assert [i["type"] for i in plan["items"]] == ["storyboard"]
    assert not os.path.exists(os.path.join(os.path.dirname(film), "evil.png"))
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(SystemExit) as e:
        MT.scan(film, [str(junk)])
    assert "Nothing FilmCrafter can use" in str(e.value)


def test_a_pdf_of_pictures_gives_one_panel_per_page(film, tmp_path):
    imgs = [Image.new("RGB", (400, 225), c) for c in ((255, 0, 0), (0, 255, 0))]
    p = tmp_path / "board.pdf"
    imgs[0].save(str(p), "PDF", save_all=True, append_images=imgs[1:])
    plan = MT.scan(film, [str(p)])
    boards = [i for i in plan["items"] if i["type"] == "storyboard"]
    assert len(boards) == 2 and boards[0]["rel"].endswith("page 001")


def test_a_file_changed_after_the_scan_is_not_used(film, tmp_path):
    src = tmp_path / "mat" / "storyboard"
    f = pic(str(src / f"{ids(film)[0]}.png"))
    plan = MT.scan(film, [str(src)])
    pic(f, (9, 9, 9), (640, 360))                                                     # replaced on disk after the scan
    res = MT.apply(film, plan["token"], {})
    assert res["applied"] == [] and res["changed_since_scan"]


def test_a_bad_plan_token_is_refused_and_nothing_else_is_touched(film):
    for t in ("", "../../etc", "zzzz", "0" * 12):
        with pytest.raises(SystemExit):
            MT.apply(film, t, {})


def test_nothing_in_the_module_can_spend_or_send():
    src = open(MT.__file__, encoding="utf-8").read()
    for bad in ("import requests", "urllib", "socket", "http.client", "subprocess", "paidops", "api_key"):
        assert bad not in src, bad


def test_review_shows_the_plan_with_the_persons_choices_and_changes_nothing(film, tmp_path):
    src = tmp_path / "mat"
    pic(str(src / "mystery.png"))
    plan = MT.scan(film, [str(src)])
    iid = plan["items"][0]["id"]
    cache = os.sep + "cache" + os.sep
    before = {k: v for k, v in hashes(film).items() if cache not in k}
    r = MT.review(film, plan["token"], {iid: {"as": "prop", "new_name": "Lamp"}})
    it = r["items"][0]
    assert it["type"] == "asset" and it["kind"] == "prop" and it["name"] == "Lamp" and it["create"] and it["on"] and it["preview"].endswith("mystery.png")
    assert {k: v for k, v in hashes(film).items() if cache not in k} == before
