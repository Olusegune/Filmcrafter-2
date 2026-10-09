"""Is there a newer FilmCrafter? One read-only question to the project's public release list on GitHub.

Privacy and safety: the address is fixed in this file (nothing the user or a project can change), only https to api.github.com is followed (a
redirect anywhere else is refused), the reply is size-limited and treated as data, and nothing about the user, the computer or any project is sent.
The only thing GitHub can see is that this computer asked. The app asks only when the user presses the button, or once a day if they switched
automatic checks on.

  python -m filmcrafter_engine.updates check --current 1.10.0
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.request

REPO = "Olusegune/FilmCrafter-Music-Video-Maker"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
PAGE = f"https://github.com/{REPO}/releases"
MAX_BYTES = 512 * 1024
TIMEOUT = 8
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def parse_version(text) -> tuple[int, int, int] | None:
    m = VERSION.match(str(text or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


class _OnlyGitHub(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://api.github.com/"):
            raise urllib.error.URLError("redirect to another site refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(current: str) -> list:
    req = urllib.request.Request(API, headers={"User-Agent": f"FilmCrafter/{current}", "Accept": "application/vnd.github+json"})
    opener = urllib.request.build_opener(_OnlyGitHub)
    with opener.open(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read(MAX_BYTES + 1)[:MAX_BYTES].decode("utf-8", "replace"))
    return data if isinstance(data, list) else []


def _clean(text, n: int) -> str:
    return " ".join(str(text or "").split())[:n]


def check(current: str, get=fetch) -> dict:
    """-> {status: update | up_to_date | offline | unavailable, current, latest, url, notes, published, prerelease}"""
    cur = parse_version(current)
    out = {"status": "unavailable", "current": str(current), "latest": None, "url": PAGE, "notes": "", "published": None, "prerelease": False}
    if not cur:
        return out
    try:
        releases = get(current)
    except urllib.error.HTTPError:
        return out                         # 404/401/403: the list is not public (or GitHub is rate-limiting this address)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return {**out, "status": "offline"}
    except ValueError:
        return out
    best = None
    for r in releases:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        v = parse_version(r.get("tag_name"))
        if v and (best is None or v > best[0]):
            best = (v, r)
    if not best:
        return {**out, "status": "up_to_date"}
    v, r = best
    url = str(r.get("html_url") or "")
    out.update(latest=".".join(map(str, v)), url=url if url.startswith(f"https://github.com/{REPO}/") else PAGE, notes=_clean(r.get("body"), 600),
               published=_clean(r.get("published_at"), 30) or None, prerelease=bool(r.get("prerelease")))
    out["status"] = "update" if v > cur else "up_to_date"
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-updates")
    ap.add_argument("action", choices=["check"])
    ap.add_argument("--current", required=True)
    a = ap.parse_args(argv)
    emit(event="result", data=check(a.current))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
