import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
import json, os, random, re, sys
from tv_config import HERE, OUT

D = OUT
files = []
for root, dirs, names in os.walk(D):
    dirs[:] = [d for d in dirs if d not in ("_work", "_tool")]
    for n in names:
        if n.lower().endswith(".pine"):
            files.append(os.path.join(root, n))
total = 0
empty = 0
tiny = 0
for p in files:
    s = os.path.getsize(p)
    total += s
    if s == 0:
        empty += 1
    elif s < 60:
        tiny += 1

random.seed(7)
sample = random.sample(files, min(300, len(files)))
SIG = re.compile(r"//@version|indicator\(|strategy\(|library\(|import\s|@import")
good = 0
vers = {}
for p in sample:
    with open(p, "r", encoding="utf-8", errors="replace") as fh:
        head = fh.read(400)
    if SIG.search(head):
        good += 1
        m = re.search(r"//@version=(\d)", head)
        if m:
            vers[m.group(1)] = vers.get(m.group(1), 0) + 1

print("pine files        : %d" % len(files))
print("total size        : %.1f MB" % (total / 1048576))
print("empty files       : %d" % empty)
print("tiny (<60B) files : %d" % tiny)
print("sample valid pine : %d/%d" % (good, len(sample)))
print("pine versions     : %s" % dict(sorted(vers.items())))
for extra in ("catalog.md", "_manifest.csv", "_manifest.jsonl", "_manifest_stats.json", "_downloaded.jsonl"):
    p = os.path.join(D, extra)
    print("%-20s: %s" % (extra, ("%.1f MB" % (os.path.getsize(p) / 1048576)) if os.path.exists(p) else "MISSING"))
mp = os.path.join(D, "_manifest_stats.json")
if os.path.exists(mp):
    print("manifest stats    : %s" % json.dumps(json.load(open(mp, encoding="utf-8")), ensure_ascii=False))
cp = os.path.join(D, "catalog.md")
if os.path.exists(cp):
    with open(cp, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i > 8:
                break
            print("catalog | %s" % line.rstrip())
