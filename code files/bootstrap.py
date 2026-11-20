import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for _name in os.listdir(ROOT):
    _dir = os.path.join(ROOT, _name)
    if os.path.isdir(_dir) and _dir not in sys.path:
        sys.path.insert(0, _dir)
