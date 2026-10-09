"""How one shot enters from the one before it.

Every transition keeps each cut exactly on its frame: nothing is shifted or overlapped in time. The previous shot's last frame is held and taken away over the first moments of
the new shot (dissolved, wiped, slid off, zoomed through), so the film is the same length with or without a transition. The two dips (black, white) are fades of the shot itself.
"""
from __future__ import annotations

# id -> (label, group, default seconds)
CATALOG: dict[str, tuple[str, str, float]] = {
    "cut": ("Cut", "Basic", 0.0),
    "dissolve": ("Cross-dissolve", "Basic", 0.5),
    "black": ("Dip to black", "Basic", 0.3),
    "white": ("Flash of white", "Basic", 0.3),
    "wipe_right": ("Wipe to the right", "Wipe", 0.5),
    "wipe_left": ("Wipe to the left", "Wipe", 0.5),
    "wipe_down": ("Wipe down", "Wipe", 0.5),
    "wipe_up": ("Wipe up", "Wipe", 0.5),
    "slide_left": ("Slide off to the left", "Move", 0.45),
    "slide_right": ("Slide off to the right", "Move", 0.45),
    "slide_up": ("Slide off upward", "Move", 0.45),
    "slide_down": ("Slide off downward", "Move", 0.45),
    "whip_left": ("Whip to the left", "Move", 0.25),
    "whip_right": ("Whip to the right", "Move", 0.25),
    "zoom_through": ("Zoom through", "Move", 0.6),
}
TRANSITIONS = list(CATALOG)
MIN_S, MAX_S = 0.1, 2.0
DIPS = ("black", "white")


def clean_seconds(kind: str, seconds) -> float | None:
    """The length a person asked for, kept inside what looks right; None means the transition's own default."""
    if seconds in (None, ""):
        return None
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        raise SystemExit("A transition's length is a number of seconds.")
    if s != s or s in (float("inf"), float("-inf")):
        raise SystemExit("A transition's length is a number of seconds.")
    return round(min(MAX_S, max(MIN_S, s)), 2)


def seconds_for(kind: str, chosen) -> float:
    return clean_seconds(kind, chosen) or CATALOG.get(kind, CATALOG["cut"])[2]


def frames_for(kind: str, chosen, frames: int, fps: int) -> int:
    """How many frames of the new shot the transition takes: never more than half the shot, at least 2."""
    return max(2, min(round(seconds_for(kind, chosen) * fps), max(2, frames // 2)))


def fades(tin: str, tout: str, frames: int, fps: int, tin_s=None, tout_s=None) -> str:
    """The dips: a shot entering from black or white fades in, and one followed by a dip fades out."""
    f = ""
    if tin in DIPS:
        n = min(round(seconds_for(tin, tin_s) * fps), max(1, frames // 3))
        f += f",fade=t=in:s=0:n={n}:color={tin}"
    if tout in DIPS:
        n = min(round(seconds_for(tout, tout_s) * fps), max(1, frames // 3))
        f += f",fade=t=out:s={max(0, frames - n)}:n={n}:color={tout}"
    return f


def _p(secs: float, ease: str = "", var: str = "t") -> str:
    p = f"min(1,{var}/{secs:.4f})"        # overlay names the time t; blend's T did not behave, so blend counts frames (N) instead (see _pn)
    return f"pow({p},3)" if ease == "whip" else p


def _pn(n: int) -> str:
    return f"min(1,N/{n})"


def filter_graph(kind: str, n: int, w: int, h: int, fps: int) -> tuple[str, bool]:
    """(ffmpeg filter_complex, uses_last_frame_zoom). Input 0 is the new shot, input 1 is the previous shot's last frame held. The output is the new shot with the old frame taken away."""
    D = n / fps
    if kind == "dissolve":
        return f"[1:v]format=rgba,fade=t=out:s=0:n={n}:alpha=1,trim=end_frame={n}[ov];[0:v][ov]overlay=eof_action=pass,format=yuv420p", False
    if kind.startswith("wipe_"):
        P = _pn(n)
        cond = {"wipe_right": f"gt(X,W*{P})", "wipe_left": f"lt(X,W*(1-{P}))", "wipe_down": f"gt(Y,H*{P})", "wipe_up": f"lt(Y,H*(1-{P}))"}[kind]
        return f"[1:v]format=yuv420p[a];[0:v]format=yuv420p[b];[a][b]blend=all_expr='if({cond},A,B)':shortest=1,format=yuv420p", False
    if kind.startswith(("slide_", "whip_")):
        P = _p(D, "whip" if kind.startswith("whip_") else "", "t")
        way = kind.split("_", 1)[1]
        pos = {"left": f"x='-w*{P}':y=0", "right": f"x='w*{P}':y=0", "up": f"x=0:y='-h*{P}'", "down": f"x=0:y='h*{P}'"}[way]
        return f"[0:v][1:v]overlay={pos}:eof_action=pass:shortest=1,format=yuv420p", False
    if kind == "zoom_through":
        P = _pn(n)
        return (f"[1:v]zoompan=z='min(1.7,1+0.7*on/{n})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},format=yuv420p[a];[0:v]format=yuv420p[b];"
                f"[a][b]blend=all_expr='A*(1-{P})+B*{P}':shortest=1,format=yuv420p"), True
    raise SystemExit("Unknown transition.")


def enter(run, prev: str, cur: str, frames: int, enc: list[str], kind: str, chosen, w: int, h: int, fps: int) -> None:
    """Replace `cur` with the same shot entered by `kind` from the end of `prev`. `run` runs ffmpeg with the given arguments."""
    import os
    if kind not in CATALOG or kind in ("cut",) + DIPS:
        return
    n = frames_for(kind, chosen, frames, fps)
    last = cur + ".last.png"
    run(["-sseof", "-0.1", "-i", prev, "-frames:v", "1", "-update", "1", last])
    tmp = cur + ".dx.mp4"
    graph, _ = filter_graph(kind, n, w, h, fps)
    try:
        run(["-i", cur, "-loop", "1", "-framerate", str(fps), "-i", last, "-filter_complex", graph, "-frames:v", str(frames), *enc, tmp])
        os.replace(tmp, cur)
    finally:
        if os.path.exists(last):
            os.remove(last)
        if os.path.exists(tmp):
            os.remove(tmp)
