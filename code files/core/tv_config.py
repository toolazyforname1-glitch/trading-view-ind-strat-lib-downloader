import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Portable path resolution, for source runs and for the frozen .exe."""
import json
import os
import sys

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    HERE = os.path.dirname(os.path.abspath(sys.executable))
    CONFIG = os.path.join(HERE, "config.json")
else:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
    HERE = os.path.dirname(CONFIG_DIR)
    CONFIG = os.path.join(CONFIG_DIR, "config.json")

LOGS = os.path.join(HERE, "logs")


def _data_dir():
    env = os.environ.get("TV_DATA_DIR")
    if env:
        return os.path.abspath(env)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            p = (json.load(f) or {}).get("output_dir")
        if p:
            return os.path.abspath(os.path.join(os.path.dirname(CONFIG), p))
    except Exception:
        pass
    return os.path.abspath(os.path.join(HERE, "indicators"))


OUT = _data_dir()


def set_data_dir(path):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"output_dir": os.path.abspath(path)}, f, indent=2)
