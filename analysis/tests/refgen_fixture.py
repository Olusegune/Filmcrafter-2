"""A project with a cast, a place and props that have specs but no pictures yet, for the picture-making tests (refgen). It is written straight into the project
(the same library entries a package import used to make), so these tests need nothing from any package format."""
import json
import os
import shutil

SONGMAP = {"duration": 60.0, "bpm": 0, "beats": [], "downbeats": [], "energy_curve": [], "accents": [], "sections": [], "lyrics": [], "analyzer": "film"}


def project(tmp_path, name="P"):
    d = tmp_path / name
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "P", "song": "song.wav", "look": {"style": "auto"}}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    (d / "songmap.json").write_text(json.dumps(SONGMAP))
    return str(d)


def apply_assets(d: str, package_dir: str) -> None:
    """Copy a folder of assets (a manifest.json listing characters, places, wardrobe and props, with their files) into the project and list them in its library."""
    m = json.load(open(os.path.join(package_dir, "manifest.json"), encoding="utf-8"))
    dest = os.path.join(d, "assets", "producer")
    os.makedirs(dest, exist_ok=True)
    items = []
    kinds = {"characters": "character", "environments": "set", "wardrobe": "wardrobe", "props": "prop"}
    for key, kind in kinds.items():
        for a in m["assets"].get(key, []):
            files = []
            for f in a.get("files") or []:
                src = os.path.join(package_dir, f)
                if os.path.isfile(src):
                    shutil.copyfile(src, os.path.join(dest, os.path.basename(f)))
                    files.append("assets/producer/" + os.path.basename(f))
            rules = a.get("locked_rules") or []
            items.append({"id": "pf_" + a["id"], "kind": kind, "name": a["name"], "files": files, "notes": f"Locked: {'; '.join(rules)}." if rules else "",
                          "external_id": a["id"], "canonical": False, "locked_rules": rules, "owner": a.get("owner_character_id") or "", "flexible_rules": []})
    p = json.load(open(os.path.join(d, "project.json"), encoding="utf-8"))
    p["library"] = {"items": items, "assign": {"project": [], "scenes": {}, "shots": {}}}
    json.dump(p, open(os.path.join(d, "project.json"), "w", encoding="utf-8"))
