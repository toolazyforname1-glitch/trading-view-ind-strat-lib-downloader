import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Restructure: one folder per script, holding the .pine source and a .md description.

  <Name> [TVid]\
      <Name> [TVid].pine
      <Name> [TVid].md
"""
import json, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT

DESC_FILE = os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl")
IDS_FILE = os.path.join(OUT, "_work", "descriptions", "ids.jsonl")
TYPE_MAP = {"1": "indicator", "2": "strategy", "3": "library",
            "indicator": "indicator", "strategy": "strategy", "library": "library"}


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def load_jsonl(path):
    out = []
    if os.path.exists(path):
        for r in read_jsonl(path):
            out.append(r)
    return out


def build_md(rec, desc, sid):
    name = rec.get("name") or rec.get("title") or ""
    author = rec.get("author") or ""
    t = TYPE_MAP.get(str(rec.get("script_type") or rec.get("type") or ""), "?")
    url = rec.get("url") or ""
    if not url and sid:
        url = "https://www.tradingview.com/script/%s/" % sid
    rows = [
        ("Author", author),
        ("Type", t),
        ("Version", rec.get("version") or ""),
    ]
    if url:
        rows.append(("Source", url))
    if rec.get("likes") not in (None, "", 0):
        rows.append(("Likes", "{:,}".format(rec["likes"]) if isinstance(rec["likes"], int) else rec["likes"]))
    if rec.get("views"):
        rows.append(("Views", "{:,}".format(rec["views"]) if isinstance(rec["views"], int) else rec["views"]))
    if rec.get("created_at"):
        rows.append(("Published", rec["created_at"]))
    if rec.get("updated_at"):
        rows.append(("Updated", rec["updated_at"]))
    if rec.get("bytes"):
        rows.append(("Source size", "{:,} bytes".format(rec["bytes"])))
    lines = ["# %s" % name, ""]
    lines.append("| | |")
    lines.append("|---|---|")
    for k, v in rows:
        if v:
            lines.append("| %s | %s |" % (k, v))
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(desc.strip() if desc else "_No description available._")
    lines.append("")
    return "\n".join(lines)


def main():
    t0 = time.time()
    dl = load_jsonl(os.path.join(OUT, "_downloaded.jsonl"))
    man = {r.get("pub_id"): r for r in load_jsonl(os.path.join(OUT, "_manifest.jsonl"))}
    descs = {r.get("pub_id"): r for r in load_jsonl(DESC_FILE)}
    sids = {r.get("pub_id"): r.get("sid") for r in load_jsonl(IDS_FILE)}
    log("loaded: %d downloaded, %d manifest, %d descriptions, %d short ids"
        % (len(dl), len(man), len(descs), len(sids)))

    moved = 0
    wrote = 0
    skipped = 0
    missing = 0
    withdesc = 0
    collisions = {}
    for rec in dl:
        pub = rec.get("pub_id")
        fname = rec.get("file") or ""
        if not fname:
            skipped += 1
            continue
        stem = fname[:-5] if fname.lower().endswith(".pine") else fname
        src = os.path.join(OUT, fname)
        folder = os.path.join(OUT, stem)
        dst = os.path.join(folder, fname)
        md = os.path.join(folder, stem + ".md")
        if os.path.exists(dst):
            skipped += 1
            continue
        if not os.path.exists(src):
            missing += 1
            continue
        if stem in collisions and collisions[stem] != pub:
            stem = "%s~%s" % (stem, pub[4:12])
            folder = os.path.join(OUT, stem)
            dst = os.path.join(folder, fname)
            md = os.path.join(folder, stem + ".md")
        collisions[stem] = pub
        os.makedirs(folder, exist_ok=True)
        shutil.move(src, dst)
        moved += 1
        m = man.get(pub) or {}
        d = descs.get(pub)
        desc = ""
        if d and d.get("description"):
            desc = d["description"]
            withdesc += 1
        elif m.get("description"):
            desc = m["description"]
        merged = dict(m)
        merged.update({k: v for k, v in rec.items() if v})
        merged.setdefault("name", rec.get("name") or stem)
        sid = rec.get("sid") or (d or {}).get("sid") or sids.get(pub) or rec.get("tv_id")
        with open(md, "w", encoding="utf-8") as f:
            f.write(build_md(merged, desc, sid))
        wrote += 1
        if (moved + skipped) % 5000 == 0:
            log("  %d moved, %d skipped, %d missing" % (moved, skipped, missing))

    log("done: moved=%d md=%d skipped=%d missing=%d with_full_desc=%d in %.1f min"
        % (moved, wrote, skipped, missing, withdesc, (time.time() - t0) / 60))
    leftover = [f for f in os.listdir(OUT) if f.lower().endswith(".pine")]
    log("leftover flat .pine files: %d" % len(leftover))
    dirs = [d for d in os.listdir(OUT) if os.path.isdir(os.path.join(OUT, d))]
    log("script folders: %d" % len(dirs))


if __name__ == "__main__":
    main()
