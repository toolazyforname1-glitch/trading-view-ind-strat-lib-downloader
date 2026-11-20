import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Adaptive rate limiting + status telemetry (used by the network collectors)."""
import threading
import time
from collections import Counter


class RateLimiter:
    def __init__(self, rate=10.0, burst=1):
        self.min_gap = 1.0 / max(0.01, rate)
        self.burst = burst
        self._last = 0.0
        self._n = 0
        self._lock = threading.Lock()
        self._factor = 1.0

    def wait(self):
        while True:
            with self._lock:
                now = time.time()
                due = self._last + self.min_gap * self._factor
                if now >= due:
                    self._last = now
                    self._n += 1
                    if self._n % self.burst == 0:
                        self._factor = max(0.25, self._factor * 0.995)
                    return
                delay = due - now
            time.sleep(delay)

    def slow(self, factor=1.5):
        with self._lock:
            self._factor = min(8.0, self._factor * factor)


class StatusTracker:
    def __init__(self):
        self.counts = Counter()
        self._lock = threading.Lock()

    def record(self, code):
        with self._lock:
            self.counts[str(code)] += 1

    def bad_fraction(self):
        with self._lock:
            good = sum(v for k, v in self.counts.items() if k.startswith("2"))
            total = sum(self.counts.values())
        return 0.0 if total == 0 else 1.0 - good / total

    def report(self):
        with self._lock:
            return dict(self.counts)
