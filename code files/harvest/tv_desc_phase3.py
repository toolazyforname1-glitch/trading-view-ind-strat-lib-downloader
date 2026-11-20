import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Phase 3: resolve short ids for the open scripts that have none.

These came from the search endpoint with no short id recorded.  Query the same
endpoint by the script's exact title and match on title+author.
"""
import json, os, re, sys, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT
from tv_desc_scrape import get, load_ids, IDS_FILE, log

WORKERS = 4
_lock = threading.Lock()
_stats = Counter()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def base_name(name, author):
    n = (name or "").strip()
    a = (author or "").strip()
    if a and n.endswith("[%s]" % a):
        n = n[: -(len(a) + 2)].strip()
    return n


def main():
    os.makedirs(os.path.dirname(IDS_FILE), exist_ok=True)
    ids = load_ids()
    man = list(read_jsonl(os.path.join(OUT, "_manifest.jsonl")))
    todo = []
    for r in man:
        if str(r.get("access")) != "1":
            continue
        pub = r.get("pub_id")
        if not pub or r.get("tv_id") or pub in ids:
            continue
        todo.append(r)
    log("phase3: %d open scripts without a short id" % len(todo))
    out = open(IDS_FILE, "a", encoding="utf-8")
    t0 = time.time()

    def one(r):
        pub = r.get("pub_id")
        bn = base_name(r.get("name"), r.get("author"))
        url = ("https://www.tradingview.com/pubscripts-suggest-json/?search=%s" % quote(bn))
        body = get(url)
        if not body:
            with _lock:
                _stats["http_fail"] += 1
            return
        try:
            res = (json.loads(body) or {}).get("results") or []
        except Exception:
            with _lock:
                _stats["bad_json"] += 1
            return
        want_n = norm(bn)
        want_a = norm(r.get("author"))
        pick = None
        for o in res:
            on = norm(o.get("scriptName") or o.get("title") or "")
            oa = o.get("author") or {}
            oan = norm(oa.get("username") if isinstance(oa, dict) else oa)
            if on == want_n and (not want_a or oan == want_a):
                pick = o
                break
        if pick is None:
            for o in res:
                if norm(o.get("scriptName") or o.get("title") or "") == want_n:
                    pick = o
                    break
        if pick and pick.get("scriptIdPart") and pick.get("imageUrl"):
            with _lock:
                ids[pick["scriptIdPart"]] = pick["imageUrl"]
                out.write(json.dumps({"pub_id": pick["scriptIdPart"],
                                      "sid": pick["imageUrl"],
                                      "name": pick.get("scriptName") or "",
                                      "version": pick.get("version") or "",
                                      "type": pick.get("type"),
                                      "likes": pick.get("agreeCount")},
                                     ensure_ascii=False) + "\n")
                out.flush()
                _stats["resolved"] += 1
        else:
            with _lock:
                _stats["unresolved"] += 1

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, _ in enumerate(ex.map(one, todo)):
            if i % 250 == 0 or i == len(todo) - 1:
                el = time.time() - t0
                log("  phase3 %d/%d  %s  %.1f/s"
                    % (i + 1, len(todo), dict(_stats), (i + 1) / max(1e-6, el)))
    out.close()
    log("phase3 done: %s  (ids now %d)" % (dict(_stats), len(ids)))


if __name__ == "__main__":
    main()
