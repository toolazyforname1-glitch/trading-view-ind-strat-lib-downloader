import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Refresh the .md description files once the full descriptions have been scraped."""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT
from tv_restructure import build_md, load_jsonl, log

DESC_FILE = os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl")
IDS_FILE = os.path.join(OUT, "_work", "descriptions", "ids.jsonl")


def main():
    t0 = time.time()
    man = {r.get("pub_id"): r for r in load_jsonl(os.path.join(OUT, "_manifest.jsonl"))}
    descs = {r.get("pub_id"): r for r in load_jsonl(DESC_FILE)}
    sids = {r.get("pub_id"): r.get("sid") for r in load_jsonl(IDS_FILE)}
    dl = load_jsonl(os.path.join(OUT, "_downloaded.jsonl"))
    log("manifest=%d descriptions=%d downloaded=%d" % (len(man), len(descs), len(dl)))
    wrote = 0
    withdesc = 0
    empty = 0
    for rec in dl:
        pub = rec.get("pub_id")
        fname = rec.get("file") or ""
        stem = fname[:-5] if fname.lower().endswith(".pine") else fname
        folder = os.path.join(OUT, stem)
        if not os.path.isdir(folder):
            continue
        d = descs.get(pub)
        if not d:
            continue
        desc = d.get("description") or ""
        if not desc:
            empty += 1
            continue
        withdesc += 1
        m = man.get(pub) or {}
        merged = dict(m)
        merged.update({k: v for k, v in rec.items() if v})
        sid = (d or {}).get("sid") or sids.get(pub) or rec.get("tv_id")
        md = os.path.join(folder, stem + ".md")
        with open(md, "w", encoding="utf-8") as f:
            f.write(build_md(merged, desc, sid))
        wrote += 1
        if wrote % 10000 == 0:
            log("  rewrote %d" % wrote)
    log("done: rewrote=%d with_desc=%d empty=%d in %.1f min"
        % (wrote, withdesc, empty, (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
