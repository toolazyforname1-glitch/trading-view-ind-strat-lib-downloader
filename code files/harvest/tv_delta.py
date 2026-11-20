import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Delta run: re-merge every cached shard, download anything new, rebuild indexes."""
import os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT
from tv_lib import read_jsonl, PAGES, KEYS
from tv_pipeline import Pipeline

PY = sys.executable


class Rep:
    def emit_event(self, kw):
        if kw.get("ev") == "task":
            print("[%s] PROG task|%s|%s|%s|%s" % (time.strftime("%H:%M:%S"),
                  kw.get("name"), kw.get("done"), kw.get("total"), kw.get("eta_min") or ""), flush=True)


def main():
    print("[%s] delta: merging all shards" % time.strftime("%H:%M:%S"), flush=True)
    p = Pipeline(reporter=Rep(), workers=6, delay=0.15, scope="all")
    p._merge()
    old = set()
    mf = os.path.join(OUT, "_manifest.jsonl")
    for r in read_jsonl(mf):
        if r.get("pub_id"):
            old.add(r["pub_id"])
    new = set(p.by_pub) - old
    print("[%s] new scripts: %d" % (time.strftime("%H:%M:%S"), len(new)), flush=True)
    p._download()
    p._verify()
    cli = os.path.join(HERE, "tools", "tv.py")
    for step in ("manifest", "index", "analyze"):
        r = subprocess.run([PY, "-u", cli, step], capture_output=True, text=True, timeout=3600)
        print("[%s] %s rc=%s" % (time.strftime("%H:%M:%S"), step, r.returncode), flush=True)
    print("[%s] delta done" % time.strftime("%H:%M:%S"), flush=True)


if __name__ == "__main__":
    main()
