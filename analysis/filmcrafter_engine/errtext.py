"""What a person sees when one of the engine's doors fails in a way nobody planned for: a sentence, not the name of a Python error. The technical text still goes to the log (stderr) for whoever supports the app.

A planned refusal (SystemExit with a reason) is never passed through here: those are already plain."""
import sys


def plain(e: BaseException) -> str:
    name = type(e).__name__
    try:
        print(f"{name}: {e}", file=sys.stderr)
    except Exception:                                    # noqa: BLE001  (a closed stderr must not hide the real message)
        pass
    if isinstance(e, KeyError):
        what = str(e.args[0]) if e.args and str(e.args[0]) else ""
        return f"Something this needed was left out{f' ({what[:40]})' if what else ''}, so it was not done."
    if isinstance(e, (TypeError, ValueError, AttributeError, IndexError, ZeroDivisionError, OverflowError, RecursionError, UnicodeError)):
        return "One of the values sent was not in a form FilmCrafter can use, so it was not done."
    return f"{name}: {e}"
