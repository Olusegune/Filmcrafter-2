"""PULSEFRAME analysis engine."""
import os as _os
import time as _time

_replace = _os.replace


def _replace_with_retry(src, dst, *a, **kw):
    """Every save writes a temp file and renames it over the real one. On Windows, a sync client, a virus scanner or the search indexer
    can hold the target open for a moment and the rename fails with WinError 32/5; trying again for a couple of seconds almost always works."""
    delay = 0.05
    for attempt in range(12):
        try:
            return _replace(src, dst, *a, **kw)
        except PermissionError:
            if attempt == 11:
                raise
            _time.sleep(delay)
            delay = min(delay * 1.6, 0.4)


if _os.name == "nt":
    _os.replace = _replace_with_retry


def _friendly_crash(exc_type, exc, tb):
    """Any engine command that dies on something unexpected reports ONE readable line the app can show, and keeps the full trace on stderr."""
    import json as _json
    import sys as _sys
    import traceback as _tb
    _tb.print_exception(exc_type, exc, tb)
    try:
        print(_json.dumps({"event": "error", "message": f"The engine hit an unexpected problem ({exc_type.__name__}: {str(exc)[:240]}). Nothing was lost; try again, and if it keeps happening, send me this line."}), flush=True)
    except Exception:
        pass
    _sys.exit(1)


import sys as _sys0  # noqa: E402
if _sys0.excepthook is _sys0.__excepthook__:
    _sys0.excepthook = _friendly_crash
