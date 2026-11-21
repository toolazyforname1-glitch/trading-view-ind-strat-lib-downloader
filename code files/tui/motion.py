"""Small tween engine for Textual widgets.

Textual's stylesheet transitions are not reliable for every property in this
version, so numeric motion (entrances, KPI count-ups, modal fades) is driven here
at 30 fps and only while tweens are active.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable

Easing = Callable[[float], float]


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0


@dataclass
class Tween:
    start: float
    duration: float
    delay: float
    begin: float
    end: float
    apply: Callable[[float], None]
    easing: Easing


class Motion:
    def __init__(self, app, *, enabled: bool = True, fps: int = 30) -> None:
        self.app = app
        self.enabled = enabled
        self._interval = 1.0 / fps
        self._tweens: dict[str, Tween] = {}
        self._timer = None

    def to(
        self,
        key: str,
        begin: float,
        end: float,
        duration: float,
        apply: Callable[[float], None],
        *,
        delay: float = 0.0,
        easing: Easing = ease_out_cubic,
    ) -> None:
        if not self.enabled or duration <= 0 or abs(end - begin) < 1e-9:
            self._tweens.pop(key, None)
            apply(end)
            self._maybe_stop()
            return
        self._tweens[key] = Tween(
            time.monotonic(), duration, delay, float(begin), float(end), apply, easing
        )
        if self._timer is None:
            self._timer = self.app.set_interval(self._interval, self._tick)

    def cancel(self, key: str, final: float | None = None) -> None:
        tween = self._tweens.pop(key, None)
        if tween is not None and final is not None:
            tween.apply(final)
        self._maybe_stop()

    def finish_all(self) -> None:
        for tween in list(self._tweens.values()):
            tween.apply(tween.end)
        self._tweens.clear()
        self._maybe_stop()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.finish_all()

    def _maybe_stop(self) -> None:
        if not self._tweens and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        now = time.monotonic()
        for key, tween in list(self._tweens.items()):
            elapsed = now - tween.start - tween.delay
            if elapsed < 0:
                continue
            progress = min(1.0, elapsed / tween.duration)
            value = tween.begin + (tween.end - tween.begin) * tween.easing(progress)
            tween.apply(value)
            if progress >= 1.0:
                del self._tweens[key]
        self._maybe_stop()
