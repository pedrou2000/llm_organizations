"""Display formatting for the visualizer — the one place raw values become
human strings/classes. Exposed to templates as `fmt`.
"""
from __future__ import annotations

from typing import Any

# Score -> qualitative class thresholds (also drives tile/badge coloring).
GOOD_AT = 0.6
MID_AT = 0.3

_MISSING = "–"


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float))


def pct(x: Any) -> str:
    """A 0-1 fraction as a whole-number percent, e.g. 0.44 -> '44%'."""
    return f"{x*100:.0f}%" if _is_num(x) else _MISSING


def count(n: Any) -> str:
    """A large count, compacted: 2_805_153 -> '2.8M', 4520 -> '5K'."""
    if not _is_num(n):
        return _MISSING
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return str(int(n))


def chars(n: Any) -> str:
    """A char-count for per-step size: 742 -> '742', 12030 -> '12.0K'."""
    if not _is_num(n):
        return _MISSING
    return f"{n/1000:.1f}K" if n >= 1000 else str(int(n))


def duration(sec: Any) -> str:
    """Seconds -> 'Xm Ys' (or 'Ys')."""
    if not _is_num(sec):
        return _MISSING
    m, s = divmod(int(sec), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def score_class(x: Any) -> str:
    """'good' | 'mid' | 'low' | '' for coloring a score by GOOD_AT / MID_AT."""
    if not _is_num(x):
        return ""
    return "good" if x >= GOOD_AT else ("mid" if x >= MID_AT else "low")


# The object handed to templates (Jinja can't call bare module functions as
# `fmt.pct(...)` unless we give it a namespace).
class Fmt:
    pct = staticmethod(pct)
    count = staticmethod(count)
    chars = staticmethod(chars)
    duration = staticmethod(duration)
    score_class = staticmethod(score_class)


FMT = Fmt()
