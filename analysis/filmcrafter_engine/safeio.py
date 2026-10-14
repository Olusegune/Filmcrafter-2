"""Safe reading and writing of the film's small JSON records (voice.json, cast.json, film.json, ledgers...).

Why this exists. Many modules used to read a JSON file with `except (OSError, ValueError): return default`. That makes a damaged file look like an empty one, and the next save then
replaces the damaged file with defaults: the filmmaker's work is gone and nothing said so. This module keeps the cases apart and never lets damage turn into silent loss.

Reading (`read_json`):
  absent file                 -> the caller's default (the file was never made)
  valid file (even `{}`)      -> its data
  damaged file                -> the damaged bytes are copied to `<name>.corrupt-<time>` first (never overwritten, never deleted); then, if the `<name>.bak` beside it is valid,
                                 that backup is put back and used (and a note says so); otherwise a SafeIOError is raised, the damaged file is left exactly where it is, and nothing is saved
  unreadable (permissions...) -> SafeIOError; nothing is changed
  valid JSON of the wrong shape (the caller's `check` refuses it) -> SafeIOError; nothing is changed

Writing (`write_json`, `update_json`):
  the data is turned into text first (a failure there touches nothing), written to a temporary file in the same folder, flushed to disk, then swapped in with one atomic replace.
  The file being replaced becomes `<name>.bak` only if it is itself valid, so a known-good backup is never replaced by damaged data. A failed write leaves the old file in place.
  A lock file beside the target makes a read-modify-write (`update_json`) safe against another process doing the same at the same moment.

Used so far by: voice.json, cast.json, the voice ledger, film.json (story.py) and the film snapshots. Other modules still carry their own readers; adopt this one gradually.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable


class SafeIOError(SystemExit):
    """A plain-words problem with a file. A SystemExit so the engine's commands report it the way they report every other refusal. `kind`: corrupt, unreadable, unsupported, busy."""

    def __init__(self, message: str, kind: str, path: str):
        super().__init__(message)
        self.kind, self.path = kind, path


def _name(path: str) -> str:
    return os.path.basename(path)


# ---------------------------------------------------------------- the damaged-file copy

def _sha1(b: bytes) -> str:
    return hashlib.sha1(b, usedforsecurity=False).hexdigest()


def preserve_copy(path: str, raw: bytes) -> str:
    """Keep the exact bytes of a damaged file as `<path>.corrupt-<time>`. A copy with identical bytes is reused (so reading a damaged file twice does not fill the folder), and a new
    copy never overwrites an older one. Returns the copy's path."""
    folder, base = os.path.dirname(path) or ".", _name(path)
    want = _sha1(raw)
    try:
        for f in os.listdir(folder):
            if f.startswith(base + ".corrupt-"):
                try:
                    with open(os.path.join(folder, f), "rb") as fh:
                        if _sha1(fh.read()) == want:
                            return os.path.join(folder, f)
                except OSError:
                    continue
    except OSError:
        pass
    stamp = time.strftime("%Y%m%d-%H%M%S")
    n = 0
    while True:
        copy = os.path.join(folder, f"{base}.corrupt-{stamp}" + (f"-{n}" if n else ""))
        try:
            with open(copy, "xb") as fh:                      # "x": never overwrite an existing file
                fh.write(raw)
                fh.flush()
                os.fsync(fh.fileno())
            return copy
        except FileExistsError:
            n += 1


# ---------------------------------------------------------------- reading

def inspect_json(path: str, check: Callable[[Any], bool] | None = None) -> str:
    """What is at this path, without changing anything: 'absent', 'ok', 'corrupt', 'unsupported' or 'unreadable'."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unreadable"
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return "corrupt"
    if check is not None and not check(data):
        return "unsupported"
    return "ok"


def read_json(path: str, default: Any = None, *, check: Callable[[Any], bool] | None = None, recover: bool = True, notes: list | None = None) -> Any:
    """See the module note. `check(data)` says whether valid JSON has the shape the caller needs. `notes` (a list) receives a plain sentence when a backup was put back."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return default
    except OSError as e:
        raise SafeIOError(f"{_name(path)} can't be read ({e.strerror or e}). Nothing was changed.", "unreadable", path)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return _damaged(path, raw, default, check, recover, notes)
    if check is not None and not check(data):
        raise SafeIOError(f"{_name(path)} is not in a form this version of FilmCrafter understands. It was left untouched.", "unsupported", path)
    return data


def _damaged(path: str, raw: bytes, default: Any, check, recover: bool, notes: list | None) -> Any:
    kept = preserve_copy(path, raw)
    bak = path + ".bak"
    if recover and os.path.isfile(bak):
        try:
            with open(bak, "rb") as f:
                braw = f.read()
            good = json.loads(braw.decode("utf-8-sig"))
            if check is None or check(good):
                _swap_in(path, braw)                           # the backup becomes the file again; the damaged bytes are already kept; the backup itself is untouched
                if notes is not None:
                    notes.append(f"{_name(path)} was damaged and has been restored from its backup. The damaged copy is kept as {_name(kept)}.")
                return good
        except (OSError, ValueError, UnicodeDecodeError):
            pass
    raise SafeIOError(
        f"{_name(path)} is damaged and there is no good backup beside it, so FilmCrafter has stopped rather than start again from nothing. "
        f"A copy of the damaged file is kept as {_name(kept)}. You can restore from the film's backups (File, Restore from Backup), or send that copy for repair.",
        "corrupt", path)


# ---------------------------------------------------------------- the lock

@contextmanager
def locked(path: str, timeout: float = 15.0):
    """A lock between processes for one file: `<path>.lock`, made with O_EXCL. A lock older than 30 seconds belongs to a process that died and is removed."""
    lock = path + ".lock"
    os.makedirs(os.path.dirname(lock) or ".", exist_ok=True)
    start, fd, denied = time.time(), None, None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
        except (FileExistsError, PermissionError) as e:
            # On Windows, making a lock file in the instant its previous owner is deleting it fails with "permission denied" rather than "exists": it is the same "someone holds it" case.
            # A real permission problem (a read-only folder) looks different: there is no lock file at all, and it keeps failing.
            if isinstance(e, PermissionError) and not os.path.exists(lock):
                denied = denied or time.time()
                if time.time() - denied > 2.0:
                    raise SafeIOError(f"{_name(path)} can't be saved here ({e.strerror or e}). Nothing was changed.", "unreadable", path)
                time.sleep(0.02)
                continue
            denied = None
            try:
                if time.time() - os.path.getmtime(lock) > 30:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.time() - start > timeout:
                raise SafeIOError(f"{_name(path)} is busy (another part of FilmCrafter is saving it). Try again in a moment.", "busy", path)
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(lock)
        except OSError:
            pass


# ---------------------------------------------------------------- writing

def _replace(src: str, dst: str) -> None:
    """os.replace, retried briefly: Windows refuses while another process has the target open for a moment."""
    for i in range(40):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def _swap_in(path: str, data: bytes) -> None:
    """Put these bytes at `path` atomically, with a temporary file in the same folder. The temporary file never outlives a failure."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _write_locked(path: str, text: str, backup: bool) -> None:
    new = text.encode("utf-8")
    try:
        with open(path, "rb") as f:
            old = f.read()
    except FileNotFoundError:
        old = None
    except OSError as e:
        raise SafeIOError(f"{_name(path)} can't be saved ({e.strerror or e}). Nothing was changed.", "unreadable", path)
    if old == new:
        return                                                  # nothing to do: no churn, and the backup stays the previous version
    if old is not None and backup:
        try:
            json.loads(old.decode("utf-8-sig"))
            _swap_in(path + ".bak", old)                        # only a valid file becomes the backup
        except (ValueError, UnicodeDecodeError):
            preserve_copy(path, old)                            # the file being replaced is damaged: keep its bytes, leave the known-good backup alone
    _swap_in(path, new)


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


def write_json(path: str, data: Any, *, backup: bool = True, already_locked: bool = False) -> None:
    """Atomic, locked save. The text is made before anything is touched, so unserialisable data never harms the file that is there.
    `already_locked=True` is for a caller that holds `locked(path)` itself around a read-modify-write (the lock is not re-entrant)."""
    text = dumps(data)
    if already_locked:
        _write_locked(path, text, backup)
        return
    with locked(path):
        _write_locked(path, text, backup)


def update_json(path: str, change: Callable[[Any], Any], default: Any = None, *, check: Callable[[Any], bool] | None = None, backup: bool = True, notes: list | None = None) -> Any:
    """Read, change, save, as one step that no other process can interleave. `change(data)` may change `data` in place or return the new data. Returns what was saved."""
    with locked(path):
        data = read_json(path, default, check=check, notes=notes)
        out = change(data)
        if out is None:
            out = data
        _write_locked(path, dumps(out), backup)
        return out
