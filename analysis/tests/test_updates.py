import io
import json
import urllib.error

import urllib.request

import pytest

from pulseframe_analysis import updates as U

REL = lambda tag, **kw: {"tag_name": tag, "html_url": f"https://github.com/{U.REPO}/releases/tag/{tag}", "body": "Notes\n\n- one  two", "published_at": "2026-10-04T10:00:00Z", **kw}


def test_versions_are_read_and_compared_as_numbers():
    assert U.parse_version("v1.10.0") == (1, 10, 0) and U.parse_version("1.9.0") == (1, 9, 0) and U.parse_version("1.10.0-beta.1") == (1, 10, 0)
    assert U.parse_version("latest") is None and U.parse_version("") is None and U.parse_version(None) is None
    assert U.parse_version("1.10.0") > U.parse_version("1.9.0")                       # not compared as text


def test_a_newer_release_is_reported_with_its_notes_and_page():
    r = U.check("1.10.0", lambda c: [REL("v1.9.0"), REL("v1.11.0"), REL("v1.10.0")])
    assert r["status"] == "update" and r["latest"] == "1.11.0" and r["url"].endswith("/tag/v1.11.0") and r["notes"] == "Notes - one two" and r["published"]


def test_up_to_date_drafts_and_odd_tags_are_ignored():
    assert U.check("1.10.0", lambda c: [REL("v1.10.0")])["status"] == "up_to_date"
    assert U.check("1.10.0", lambda c: [REL("v2.0.0", draft=True), REL("nightly"), "junk", None])["status"] == "up_to_date"
    assert U.check("1.10.0", lambda c: [])["status"] == "up_to_date"
    assert U.check("1.10.0", lambda c: [REL("v1.11.0-rc1", prerelease=True)])["prerelease"] is True


def test_a_private_list_a_missing_network_and_bad_replies_are_reported_plainly():
    def http(code):
        def f(c):
            raise urllib.error.HTTPError(U.API, code, "x", {}, io.BytesIO(b""))
        return f
    assert U.check("1.10.0", http(404))["status"] == "unavailable"
    assert U.check("1.10.0", http(403))["status"] == "unavailable"
    def offline(c):
        raise urllib.error.URLError("no route")
    assert U.check("1.10.0", offline)["status"] == "offline"
    def timeout(c):
        raise TimeoutError()
    assert U.check("1.10.0", timeout)["status"] == "offline"
    def garbled(c):
        raise json.JSONDecodeError("x", "", 0)
    assert U.check("1.10.0", garbled)["status"] == "unavailable"
    assert U.check("not-a-version", lambda c: [REL("v9.9.9")])["status"] == "unavailable"


def test_a_release_page_outside_this_project_is_never_offered():
    r = U.check("1.0.0", lambda c: [REL("v1.1.0", html_url="https://evil.example/download.exe")])
    assert r["status"] == "update" and r["url"] == U.PAGE
    r = U.check("1.0.0", lambda c: [REL("v1.1.0", html_url="https://github.com/other/repo/releases/tag/v1.1.0")])
    assert r["url"] == U.PAGE


def test_the_address_is_fixed_and_redirects_to_other_sites_are_refused():
    assert U.API.startswith("https://api.github.com/repos/") and "?" in U.API
    h = U._OnlyGitHub()
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(urllib.request.Request(U.API), None, 302, "Found", {}, "https://evil.example/x")
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(urllib.request.Request(U.API), None, 302, "Found", {}, "http://api.github.com/x")


def test_the_command_line_speaks_json(capsys):
    assert U.main(["check", "--current", "garbage"]) == 0
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert ev["event"] == "result" and ev["data"]["status"] == "unavailable"
