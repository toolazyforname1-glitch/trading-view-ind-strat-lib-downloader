import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Verify the restructured layout and the scraped descriptions."""
import json, os, random, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT

D = OUT
folders = [d for d in os.listdir(D) if os.path.isdir(os.path.join(D, d)) and d not in ("_work", "_tool")]
print("script folders : %d" % len(folders))

no_desc_md = 0
has_desc = 0
lens = []
pine_ok = 0
for f in folders:
    p = os.path.join(D, f)
    names = os.listdir(p)
    if any(n.lower().endswith(".pine") for n in names):
        pine_ok += 1
    for n in names:
        if not n.lower().endswith(".md"):
            continue
        t = open(os.path.join(p, n), encoding="utf-8").read()
        if "_No description available._" in t:
            no_desc_md += 1
        else:
            has_desc += 1
            body = t.split("## Description", 1)[-1].strip()
            lens.append(len(body))
print("folders with a .pine : %d" % pine_ok)
print(".md with a description : %d" % has_desc)
print(".md without            : %d" % no_desc_md)
lens.sort()
if lens:
    print("description length: min=%d  p25=%d  median=%d  p75=%d  max=%d  mean=%.0f"
          % (lens[0], lens[len(lens) // 4], lens[len(lens) // 2], lens[3 * len(lens) // 4],
             lens[-1], sum(lens) / len(lens)))
    print("longer than 500 chars (not server-truncated): %d (%.1f%%)"
          % (sum(1 for x in lens if x > 520), 100.0 * sum(1 for x in lens if x > 520) / len(lens)))

man = {r.get("pub_id"): r for r in read_jsonl(os.path.join(D, "_manifest.jsonl"))}
dl = {r.get("pub_id"): r for r in read_jsonl(os.path.join(D, "_downloaded.jsonl"))}
descs = list(read_jsonl(os.path.join(D, "_work", "descriptions", "descriptions.jsonl")))
agree = tot = 0
for d in descs:
    pub = d.get("pub_id")
    prev = (man.get(pub) or {}).get("description") or ""
    if prev:
        tot += 1
        if d.get("description", "").startswith(prev[:120]):
            agree += 1
print()
print("cross-check vs the 500-char listing copy: %d/%d agree (%.1f%%)" % (agree, tot, 100.0 * agree / max(1, tot)))

random.seed(4)
print()
print("=== sample .md files ===")
for f in random.sample(folders, 2):
    md = [n for n in os.listdir(os.path.join(D, f)) if n.endswith(".md")]
    if not md:
        continue
    txt = open(os.path.join(D, f, md[0]), encoding="utf-8").read()
    print("--- %s ---" % f)
    print(txt[:1100])
    print()
