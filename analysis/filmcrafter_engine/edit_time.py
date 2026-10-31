"""Exact time for editing: whole numbers of ticks, never floating seconds.

One tick is 1/254,016,000,000 of a second. That number is 2^12 x 3^4 x 5^6 x 7^2, so the length of one frame at 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60 and 120 frames a second is a
whole number of ticks, and so are the common audio sample rates. A position on the timeline is an integer; adding, trimming and splitting are integer sums, so a hundred edits never drift by a frame.
(The idea, and this constant, are from the public filmcraft project's time notes, MIT or Apache-2.0; this file is written for FilmCrafter.)

Seconds appear only at the edges: `seconds_to_ticks` rounds once, half up, when something typed or measured comes in, and `ticks_to_seconds` is for showing. Frames are whole numbers too:
`frame_at` rounds down (the frame that is on screen at that tick), `tick_of_frame` is exact.

No function in this file, and none of the editing modules that use it, does arithmetic on time in floating point; a test looks for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import gcd

TICKS_PER_SECOND = 254_016_000_000


@dataclass(frozen=True)
class FrameRate:
    num: int = 24
    den: int = 1

    def __post_init__(self):
        if not (isinstance(self.num, int) and isinstance(self.den, int)) or self.num <= 0 or self.den <= 0:
            raise ValueError("A frame rate is two positive whole numbers.")
        g = gcd(self.num, self.den)
        if g > 1:
            object.__setattr__(self, "num", self.num // g)
            object.__setattr__(self, "den", self.den // g)

    @property
    def frame_ticks(self) -> int:
        """The length of one frame, in ticks: a whole number for every common frame rate (checked in `exact`)."""
        return TICKS_PER_SECOND * self.den // self.num

    @property
    def exact(self) -> bool:
        return (TICKS_PER_SECOND * self.den) % self.num == 0

    def as_list(self) -> list[int]:
        return [self.num, self.den]

    @staticmethod
    def of(v) -> "FrameRate":
        if isinstance(v, FrameRate):
            return v
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v):
            try:
                return FrameRate(v[0], v[1])
            except ValueError:
                pass
        return FPS_24


FPS_24 = FrameRate(24, 1)
COMMON = {"23.976": FrameRate(24000, 1001), "24": FPS_24, "25": FrameRate(25, 1), "29.97": FrameRate(30000, 1001), "30": FrameRate(30, 1), "48": FrameRate(48, 1), "50": FrameRate(50, 1),
          "59.94": FrameRate(60000, 1001), "60": FrameRate(60, 1), "120": FrameRate(120, 1)}


def tick_of_frame(frame: int, fps: FrameRate = FPS_24) -> int:
    """The tick at which a frame starts. Exact."""
    return int(frame) * fps.frame_ticks


def frame_at(tick: int, fps: FrameRate = FPS_24) -> int:
    """The frame that is showing at a tick (rounds down)."""
    return int(tick) // fps.frame_ticks


def snap(tick: int, fps: FrameRate = FPS_24) -> int:
    """Down to the start of its frame."""
    return frame_at(tick, fps) * fps.frame_ticks


def snap_nearest(tick: int, fps: FrameRate = FPS_24) -> int:
    """To the nearest frame start; exactly half way goes to the earlier frame."""
    ft = fps.frame_ticks
    lo = (int(tick) // ft) * ft
    return lo if int(tick) - lo <= lo + ft - int(tick) else lo + ft


def seconds_to_ticks(seconds, fps: FrameRate = FPS_24) -> int:
    """Seconds typed or measured, to ticks, rounded once (half up) and then snapped to the nearest frame. This is the one place a float comes in."""
    num, den = _ratio(seconds)
    t = (num * TICKS_PER_SECOND * 2 + den) // (den * 2)             # half up, in integers
    return snap_nearest(t, fps)


def ticks_to_seconds(tick: int) -> float:
    """For showing only."""
    return int(tick) / TICKS_PER_SECOND


def _ratio(v) -> tuple[int, int]:
    """A number as a fraction of whole numbers, without doing arithmetic on it as a float."""
    if isinstance(v, bool):
        raise ValueError("Not a time.")
    if isinstance(v, int):
        return v, 1
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("Not a time.")
        n, d = v.as_integer_ratio()
        return n, d
    from fractions import Fraction
    f = Fraction(str(v))
    return f.numerator, f.denominator


def frames_of(ticks: int, fps: FrameRate = FPS_24) -> int:
    """How many whole frames a length holds (a length that is not a whole number of frames rounds down)."""
    return int(ticks) // fps.frame_ticks


def timecode(tick: int, fps: FrameRate = FPS_24) -> str:
    """hh:mm:ss:ff for showing (non-drop-frame; at 29.97 and 59.94 it counts frames at the nominal 30 or 60)."""
    nominal = (fps.num + fps.den - 1) // fps.den
    n = frame_at(tick, fps)
    ff = n % nominal
    s = n // nominal
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{ff:02d}"
