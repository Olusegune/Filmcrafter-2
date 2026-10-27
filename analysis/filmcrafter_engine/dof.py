"""Depth of field: how much of the picture is in focus, chosen like an aperture.

On a real camera the aperture decides it: a wide opening (a small f-number) puts only the subject in focus and melts the background into a soft wash; a small opening (a large f-number) keeps
everything sharp, near and far. Image and video models cannot set an aperture, but they follow plain words about it. So a shot can carry a depth-of-field choice, and the request says it in the
terms a cinematographer uses, with the aperture it corresponds to. Left on automatic, shots about people get a softly out-of-focus background (picturecare.py) and wide shots are left alone.

  very shallow   about f/1.4: only the eyes (or the one detail) are sharp; everything else is a soft wash
  shallow        about f/2.8: the subject is sharp, the background falls softly out of focus
  medium         about f/5.6: the people and what is near them are sharp; the far background is gently soft
  deep           about f/11: near and far are both sharp, so the place is as readable as the people

Pure text: free, deterministic, nothing is sent anywhere.
"""
from __future__ import annotations

PRIORITY = 7

LEVELS: dict[str, dict] = {
    "very shallow": {"label": "Very shallow (about f/1.4)", "aperture": "f/1.4", "soft": True,
                     "text": "Very shallow depth of field, as if shot wide open at about f/1.4: only the eyes (or the one key detail) are sharp, and everything in front of and behind them melts into a soft, creamy blur."},
    "shallow": {"label": "Shallow (about f/2.8)", "aperture": "f/2.8", "soft": True,
                "text": "Shallow depth of field, as if shot at about f/2.8: the subject is sharp and the background falls softly out of focus."},
    "medium": {"label": "Medium (about f/5.6)", "aperture": "f/5.6", "soft": False,
               "text": "Medium depth of field, as if shot at about f/5.6: the people and what is near them are sharp and the far background is gently soft."},
    "deep": {"label": "Deep (about f/11)", "aperture": "f/11", "soft": False,
             "text": "Deep focus, as if shot at about f/11: everything from the foreground to the far background is sharp and in focus, so the place reads as clearly as the people."},
}


def levels() -> list[dict]:
    return [{"id": k, "label": v["label"], "aperture": v["aperture"]} for k, v in LEVELS.items()]


def line(shot: dict) -> dict | None:
    """The depth-of-field sentence for a request ({"text", "priority"}), or None when the shot is left on automatic."""
    v = LEVELS.get(str(shot.get("dof") or "").lower())
    return {"text": v["text"], "priority": PRIORITY} if v else None
