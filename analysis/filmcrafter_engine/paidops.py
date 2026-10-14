"""One small set of rules for anything that can spend a provider's money or a plan's allowance. Voices use it today; sound effects, ambience and music are meant to use it as they arrive.

The rules, in the order an operation meets them:
  1. AUTHORISE. The engine, not the screen, refuses unless the call says it was confirmed (and, when the cost cannot be known, that the person accepted that). Cloning a voice needs a
     separate `consent` as well: consent to use a voice and permission to spend are different things and are never merged.
  2. LIMIT. An optional spending limit per provider unit (for example 500 ElevenLabs credits for this film). Unresolved operations count against it, because they may have been charged.
  3. RECORD. A line in the ledger before anything is sent: prepared, confirmed, submitted. A crash at any point leaves a line that says how far it got.
  4. SEND ONCE. Never an identical request while an earlier one has an unknown outcome. Automatic retries only when there is evidence the provider did not accept the earlier one:
     the provider said "slow down" (429), or the connection never reached it (`classify_transport`). A timeout after sending, or a 5xx, is *uncertain*: it is recorded as such,
     shown to the person, and never repeated automatically.
  5. SETTLE. completed (with whatever the provider reported), refused (the provider said no; nothing was charged), failed_before_submission (nothing was sent), or uncertain.
     An estimate is never written as an actual: `actual.reported` is true only when the provider's own reply carried the amount.
  6. RECOVER. Entries stuck as prepared/confirmed are settled as failed_before_submission, entries stuck as submitted become uncertain, and the person can mark an uncertain one
     "not charged" or "charged" after checking the provider's own usage page.

The ledger is a JSON file written with `safeio` (atomic, locked, never lost to a concurrent writer). Units are the provider's own (`elevenlabs_credits`, `voice_slot`, `unknown`): they are never
added together across providers. Entries carry an `area` ("voice" now) and a `kind`, so audio of every sort (dialogue, effects, ambience, music) can share the same rules and file format.

  entry = {id, key, at, updated, provider, area, action, film, person, shot, estimate{unit, amount, basis}, actual{unit, amount, reported, source}, confirmed, consent,
           status, history[{status, at}], provider_request_id, asset, note, resolved{outcome, at}}
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from . import safeio

PREPARED, CONFIRMED, SUBMITTED, COMPLETED = "prepared", "confirmed", "submitted", "completed"
REFUSED, FAILED_BEFORE, UNCERTAIN = "refused", "failed_before_submission", "uncertain"
STATUSES = (PREPARED, CONFIRMED, SUBMITTED, COMPLETED, REFUSED, FAILED_BEFORE, UNCERTAIN)
NOT_SENT, AMBIGUOUS = "not_sent", "ambiguous"

STALE_SUBMITTED_S = 120        # a "submitted" line this old, with no result, belongs to a process that died while sending
STALE_PREPARED_S = 300         # a "prepared" or "confirmed" line this old never reached the point of sending
KEEP_ENTRIES = 2000            # the ledger keeps the newest this many (it is small text; a year of heavy use is far below it)


def op_key(*parts: Any) -> str:
    """A stable key for 'the same operation': the same action on the same words, voice and model."""
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def require_authorised(confirmed: Any, what: str) -> None:
    """The engine's own refusal. Anything but the boolean True is a no."""
    if confirmed is not True:
        raise SystemExit(f"To {what}, FilmCrafter uses your provider account, so it only goes ahead after you confirm. Confirm the price first. Nothing was sent.")


def require_accepted_unknown_cost(accepted: Any, what: str) -> None:
    if accepted is not True:
        raise SystemExit(f"To {what} costs an amount the provider does not publish in advance. Confirm that you accept this. Nothing was sent.")


def classify_transport(exc: BaseException) -> str:
    """Did the request leave this computer? NOT_SENT only on evidence it could not have been accepted (the connection was never made, the name did not resolve, the secure handshake failed).
    Anything else (a timeout waiting for the answer, a dropped connection, an incomplete reply) is AMBIGUOUS: the provider may have done the work."""
    try:
        from requests import exceptions as E
        import urllib3.exceptions as U
    except ImportError:                                           # pragma: no cover
        return AMBIGUOUS
    if isinstance(exc, (E.ConnectTimeout, E.SSLError, E.InvalidURL, E.MissingSchema)):
        return NOT_SENT
    never = tuple(getattr(U, n) for n in ("NewConnectionError", "NameResolutionError", "ConnectTimeoutError") if hasattr(U, n))
    seen, stack = set(), [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if never and isinstance(e, never):
            return NOT_SENT
        stack += [getattr(e, "reason", None), e.__cause__, e.__context__] + [a for a in getattr(e, "args", ()) if isinstance(a, BaseException)]
    return AMBIGUOUS


def _blank() -> dict:
    return {"schema": 1, "limits": {}, "entries": []}


def _valid(d: Any) -> bool:
    return isinstance(d, dict) and isinstance(d.get("entries", []), list) and isinstance(d.get("limits", {}), dict)


class Ledger:
    """The record of what was prepared, sent and settled. One file; every change is an atomic, locked update."""

    def __init__(self, path: str, film: str = ""):
        self.path, self.film = path, film

    # ---------------------------------------------------------- plumbing
    def _change(self, fn):
        def go(data):
            data.setdefault("schema", 1)
            data.setdefault("limits", {})
            data.setdefault("entries", [])
            return fn(data)
        return safeio.update_json(self.path, go, _blank(), check=_valid)

    def read(self) -> dict:
        d = safeio.read_json(self.path, _blank(), check=_valid)
        d.setdefault("entries", [])
        d.setdefault("limits", {})
        return d

    def entries(self) -> list[dict]:
        return self.read()["entries"]

    def get(self, op_id: str) -> dict | None:
        return next((e for e in self.entries() if e["id"] == op_id), None)

    # ---------------------------------------------------------- recovery
    def reconcile(self) -> int:
        """Settle what a crash left half-way. Safe to call at any time and from any process."""
        now, changed = time.time(), [0]

        def go(data):
            for e in data["entries"]:
                age = now - e.get("updated", e.get("at", now))
                if e["status"] in (PREPARED, CONFIRMED) and age > STALE_PREPARED_S:
                    self._set(e, FAILED_BEFORE, note="It never reached the point of sending (the app was closed first). Nothing was charged.")
                    changed[0] += 1
                elif e["status"] == SUBMITTED and age > STALE_SUBMITTED_S:
                    self._set(e, UNCERTAIN, note="The app closed while this was being sent. It may or may not have reached the provider, and may or may not have been charged.")
                    changed[0] += 1
        if not self.entries():
            return 0
        self._change(go)
        return changed[0]

    @staticmethod
    def _set(e: dict, status: str, **fields) -> None:
        e["status"] = status
        e["updated"] = int(time.time())
        e.setdefault("history", []).append({"status": status, "at": e["updated"]})
        for k, v in fields.items():
            if v is not None:
                e[k] = v

    # ---------------------------------------------------------- the life of one operation
    def begin(self, *, key: str, provider: str, area: str, action: str, estimate: dict, kind: str = "", person: str | None = None, shot: str | None = None,
              asset: str | None = None, consent: bool | None = None, unit_for_limit: str | None = None) -> dict:
        """Record a confirmed operation before anything is sent. Refuses (and records nothing) if an identical earlier request has an unknown outcome, or if it would pass the limit."""
        now = int(time.time())
        made: dict = {}

        def go(data):
            for e in data["entries"]:
                if e.get("key") != key or e.get("resolved"):
                    continue
                if e["status"] == UNCERTAIN:
                    raise SystemExit("An identical request was already sent and its outcome is not known (it may have been charged). FilmCrafter will not send it again on its own. "
                                     "Check your provider's usage page, then mark it 'not charged' or 'charged' in the voice usage list.")
                if e["status"] in (CONFIRMED, SUBMITTED) and now - e.get("updated", e["at"]) <= STALE_SUBMITTED_S:
                    raise SystemExit("An identical request is being sent right now. Wait for it to finish.")
            unit, amount = estimate.get("unit"), estimate.get("amount")
            limit = data["limits"].get(unit)
            if isinstance(limit, (int, float)) and limit > 0 and isinstance(amount, (int, float)):
                used = sum(x["estimate"].get("amount") or 0 for x in data["entries"]
                           if x["estimate"].get("unit") == unit and (x["status"] in (COMPLETED, SUBMITTED) or (x["status"] == UNCERTAIN and (x.get("resolved") or {}).get("outcome") != "not_charged")))
                if used + amount > limit + 1e-9:
                    raise SystemExit(f"That would take this film's {provider} limit past {limit:g} {unit.replace('_', ' ')} ({used:g} already used or possibly used, {amount:g} more). "
                                     "Nothing was sent. Raise the limit in the voice usage list if you want to continue.")
            entry = {"id": uuid.uuid4().hex[:12], "key": key, "at": now, "updated": now, "provider": provider, "area": area, "kind": kind or area, "action": action, "film": self.film,
                     "person": person, "shot": shot, "estimate": {"unit": estimate.get("unit", "unknown"), "amount": estimate.get("amount"), "basis": estimate.get("basis", "")},
                     "actual": {"unit": estimate.get("unit", "unknown"), "amount": None, "reported": False, "source": None},
                     "confirmed": True, "consent": consent, "status": CONFIRMED, "asset": asset,
                     "history": [{"status": PREPARED, "at": now}, {"status": CONFIRMED, "at": now}], "provider_request_id": None, "note": ""}
            data["entries"].append(entry)
            if len(data["entries"]) > KEEP_ENTRIES:
                data["entries"] = data["entries"][-KEEP_ENTRIES:]
            made.update(entry)
        self._change(go)
        return made

    def mark(self, op_id: str, status: str, **fields) -> dict:
        assert status in STATUSES, status
        out: dict = {}

        def go(data):
            for e in data["entries"]:
                if e["id"] == op_id:
                    self._set(e, status, **fields)
                    out.update(e)
        self._change(go)
        return out

    def complete(self, op_id: str, *, request_id: str | None = None, actual_amount: float | None = None, source: str | None = None, asset: str | None = None, note: str | None = None) -> dict:
        def go(data):
            for e in data["entries"]:
                if e["id"] == op_id:
                    if actual_amount is not None:
                        e["actual"] = {"unit": e["actual"].get("unit", "unknown"), "amount": actual_amount, "reported": True, "source": source}
                    self._set(e, COMPLETED, provider_request_id=request_id, asset=asset, note=note)
                    out.update(e)
        out: dict = {}
        self._change(go)
        return out

    def refused_record(self, *, provider: str, area: str, action: str, reason: str, key: str = "", person: str | None = None, shot: str | None = None) -> None:
        """Log a request that the engine or the provider turned down (nothing was charged). Never raises: a log must not hide the real refusal."""
        try:
            now = int(time.time())

            def go(data):
                data["entries"].append({"id": uuid.uuid4().hex[:12], "key": key, "at": now, "updated": now, "provider": provider, "area": area, "kind": area, "action": action,
                                        "film": self.film, "person": person, "shot": shot, "estimate": {"unit": "unknown", "amount": None, "basis": ""},
                                        "actual": {"unit": "unknown", "amount": None, "reported": False, "source": None}, "confirmed": False, "consent": None,
                                        "status": REFUSED, "history": [{"status": REFUSED, "at": now}], "provider_request_id": None, "asset": None, "note": reason[:300]})
                data["entries"] = data["entries"][-KEEP_ENTRIES:]
            self._change(go)
        except (SystemExit, OSError, ValueError):
            pass

    def resolve(self, op_id: str, outcome: str) -> dict:
        """The person checked the provider's own usage and says whether an uncertain operation was charged. The entry stays in the list, marked."""
        if outcome not in ("not_charged", "charged"):
            raise SystemExit("Say whether it was charged or not.")
        out: dict = {}

        def go(data):
            for e in data["entries"]:
                if e["id"] == op_id:
                    if e["status"] != UNCERTAIN:
                        raise SystemExit("Only an operation whose outcome was unknown can be marked this way.")
                    e["resolved"] = {"outcome": outcome, "at": int(time.time())}
                    e["updated"] = int(time.time())
                    out.update(e)
            if not out:
                raise SystemExit("That operation is not in the list.")
        self._change(go)
        return out

    # ---------------------------------------------------------- limits and the summary
    def set_limit(self, unit: str, value: float | None) -> dict:
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            raise SystemExit("A limit is a number above zero (or empty for no limit).")

        def go(data):
            if value is None:
                data["limits"].pop(unit, None)
            else:
                data["limits"][unit] = float(value)
        self._change(go)
        return self.read()["limits"]

    def summary(self, provider: str | None = None) -> dict:
        """What has been done and, only where the provider said so, what it cost. Estimates are labelled as estimates and never added to reported amounts."""
        d = self.read()
        rows = [e for e in d["entries"] if provider in (None, e["provider"])]
        done = [e for e in rows if e["status"] == COMPLETED or (e["status"] == UNCERTAIN and (e.get("resolved") or {}).get("outcome") == "charged")]
        by_unit: dict = {}
        for e in done:
            u = e["estimate"].get("unit", "unknown")
            slot = by_unit.setdefault(u, {"operations": 0, "estimated": 0.0, "reported": 0.0, "unreported_operations": 0, "estimated_unreported": 0.0})
            slot["operations"] += 1
            slot["estimated"] += e["estimate"].get("amount") or 0
            if e["actual"].get("reported") and e["actual"].get("amount") is not None:
                slot["reported"] += e["actual"]["amount"]
            else:
                slot["unreported_operations"] += 1
                slot["estimated_unreported"] += e["estimate"].get("amount") or 0
        unresolved = [e for e in rows if e["status"] == UNCERTAIN and not e.get("resolved")]
        return {"limits": d["limits"], "by_unit": by_unit, "unresolved": unresolved, "recent": rows[-25:][::-1], "count": len(rows)}
