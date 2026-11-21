"""Job state + progress-line parsing for the Pine Harvester TUI.

The harvester's collectors print two kinds of lines:

    [HH:MM:SS] human readable progress (i/N, ok=, eta ...)
    [HH:MM:SS] PROG <kind>|<a>|<b>|<c>[|<d>]

``parse_progress`` normalises both into ``{stage, done, total, rate, eta_min}``.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Job:
    """A running harvester subprocess."""

    label: str
    argv: list[str]
    seq: int = 0
    proc: subprocess.Popen | None = None
    started: float = 0.0
    stage: str = ""
    done: float = 0.0
    display_done: float = 0.0
    total: float | None = None
    rate: float = 0.0
    eta_min: float | None = None
    counters: str = ""
    returncode: int | None = None


def find_job_python() -> str:
    """Return a Python interpreter that can import ``requests``.

    The TUI itself may be running on a Textual-only virtualenv, so preferring
    ``sys.executable`` blindly would break the description scraper.
    """
    env = os.environ.get("TV_PYTHON")
    if env and os.path.exists(env):
        return env
    seen: list[str] = []
    for cand in (shutil.which("python"), shutil.which("python3"), sys.executable):
        if cand and cand not in seen:
            seen.append(cand)
    for cand in seen:
        try:
            probe = subprocess.run(
                [cand, "-c", "import requests"],
                capture_output=True,
                timeout=15,
            )
            if probe.returncode == 0:
                return cand
        except Exception:
            continue
    return sys.executable


PROG_RE = re.compile(r"PROG\s+(\w+)\|([^|]*)\|([^|]*)\|([^|]*)(?:\|([^|]*))?")
FRAC_RE = re.compile(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)")
RATE_RE = re.compile(r"([\d.]+)\s*/\s*s\b")
ETA_RE = re.compile(r"eta\s+([\d.]+)\s*min", re.I)
COUNT_RE = re.compile(r"ok=(\d+)\s+empty=(\d+)\s+fail=(\d+)", re.I)


def _num(value: object) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def parse_progress(line: str) -> dict:
    """Extract progress fields from a collector output line (may be empty)."""
    out: dict = {}

    match = PROG_RE.search(line)
    if match:
        kind = match.group(1).lower()
        a, b, c, d = match.group(2), match.group(3), match.group(4), match.group(5)
        if kind == "task":
            out["stage"] = a.strip()
            out["done"] = _num(b)
            total = _num(c)
            out["total"] = total if total > 0 else None
            if d and d.strip():
                out["eta_min"] = _num(d)
        else:
            out["done"] = _num(a)
            total = _num(b)
            out["total"] = total if total > 0 else None
            out["stage"] = (c or kind).strip()
        return out

    match = FRAC_RE.search(line)
    if match:
        done, total = _num(match.group(1)), _num(match.group(2))
        if total > 0 and 0 <= done <= total * 1.05:
            out["done"] = done
            out["total"] = total
            out["stage"] = "working"

    match = RATE_RE.search(line)
    if match:
        out["rate"] = _num(match.group(1))

    match = ETA_RE.search(line)
    if match:
        out["eta_min"] = _num(match.group(1))

    match = COUNT_RE.search(line)
    if match:
        out["counters"] = "ok %s · empty %s · fail %s" % (
            match.group(1), match.group(2), match.group(3)
        )
    return out


def classify(line: str) -> str:
    """Return a semantic style token for a log line."""
    low = line.lower()
    if re.search(r"\b(error|failed|exception|traceback|fatal)\b", low):
        return "danger"
    if re.search(r"\b(warn|warning|protected|throttl)\w*", low):
        return "warning"
    if re.search(r"\b(done|finished|complete|success|ok)\b", low):
        return "success"
    return "text"
