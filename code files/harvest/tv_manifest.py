import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
import csv, json, os, sys
from tv_config import HERE, OUT
sys.path.insert(0, HERE)
from tv_lib import PAGES, KEYS, OUT, read_jsonl

by_pub = {}
for fn in sorted(os.listdir(PAGES)):
    if not fn.endswith(".jsonl"):
        continue
    for r in read_jsonl(os.path.join(PAGES, fn)):
        p = r.get("pub_id")
        if p and p not in by_pub:
            by_pub[p] = r
for fn in sorted(os.listdir(KEYS)):
    if not fn.endswith(".jsonl"):
        continue
    for r in read_jsonl(os.path.join(KEYS, fn)):
        p = r.get("pub_id")
        if p and p not in by_pub:
            by_pub[p] = r

rows = list(by_pub.values())
cols = ["pub_id", "tv_id", "name", "author", "access", "script_type", "version",
        "likes", "views", "url", "created_at", "updated_at", "num_id", "description"]
with open(os.path.join(OUT, "_manifest.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        r = dict(r)
        if len(r.get("description") or "") > 400:
            r["description"] = r["description"][:400] + "..."
        w.writerow(r)
with open(os.path.join(OUT, "_manifest.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

from collections import Counter
stats = {
    "total_unique": len(rows),
    "by_type": dict(Counter(r.get("script_type") or "?" for r in rows)),
    "by_access": dict(Counter(str(r.get("access")) for r in rows)),
    "with_source": sum(1 for r in rows if str(r.get("access")) == "1"),
    "no_source": sum(1 for r in rows if str(r.get("access")) != "1"),
}
with open(os.path.join(OUT, "_manifest_stats.json"), "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)
print(json.dumps(stats, indent=2, ensure_ascii=False))
