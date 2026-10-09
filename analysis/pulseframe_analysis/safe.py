"""Names that come from outside (a shot id typed in the app, written by the language model or read from an imported package) are never trusted as file names or paths.

`file_part` turns any text into something that is safe inside one file name; `check_id` refuses an id that is not a plain shot or item id.
"""
from __future__ import annotations

import re

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def file_part(text: object, limit: int = 60) -> str:
    """Safe to put inside a file name: letters, digits, dot, dash and underscore only, never starting with a dot, never empty."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "")).lstrip(".")[:limit]
    return s or "x"


def check_id(text: object, what: str = "shot") -> str:
    """The id itself when it is a plain id (S01-02, ov_1a2b3c4d), otherwise a plain refusal."""
    s = str(text or "")
    if not ID.match(s) or ".." in s:
        raise SystemExit(f"That {what} id is not valid.")
    return s


def sha1(data: bytes = b""):
    """SHA-1 for naming cache files and ids (never for anything secret): marked as not for security so scanners know it is only a fingerprint."""
    import hashlib
    return hashlib.sha1(data, usedforsecurity=False)
