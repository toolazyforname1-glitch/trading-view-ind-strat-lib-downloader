import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _name in os.listdir(_root):
    _dir = os.path.join(_root, _name)
    if os.path.isdir(_dir) and _dir not in sys.path:
        sys.path.append(_dir)
