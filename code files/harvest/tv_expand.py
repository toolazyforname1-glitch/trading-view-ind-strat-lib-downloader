import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Corpus expansion via dimensions the original sweeps never used.

Modes (first argv):
  type    - `&type=1` and `&type=2` search dimensions (measured comparable yield)
  seeds   - tokens harvested from descriptions + author names
  slice   - "<term> <a-z>" query slicing to beat the 1,000-results-per-term cap
  author  - author names as search terms
  all     - type -> seeds -> author -> slice (in that order)

Every response is cached per (mode, term, offset) so re-runs are free.
"""
import hashlib, json, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT, LOGS
from tv_lib import fetch, norm_suggest, write_jsonl, read_jsonl, KEYS
from tv_rate import RateLimiter, StatusTracker

TV = "https://www.tradingview.com"
HDR = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
       "Accept-Language": "en-US,en;q=0.9", "Referer": TV + "/"}
WORKERS = 12
DELAY = 0.10
STEP = 50
MAX_OFF = 950
LIM = RateLimiter(rate=12)
STAT = StatusTracker()
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
STOP = set("the and for with from that this your you our are was were will can not free best new "
           "pro buy sell long short signal alert auto upper lower high low open close level zone "
           "block order tool smart money market price chart indicator strategy system version "
           "updated exclusive premium tradingview forex crypto stock scalping intraday swing "
           "daily weekly multi super simple advanced classic".split())
LOG = os.path.join(LOGS, "expand.log")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def shard(mode, term, off):
    h = hashlib.md5((mode + "|" + term).encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r"[^a-z0-9]+", "_", term.lower())[:28]
    return os.path.join(KEYS, "x%s__%s__%s__o%04d.jsonl" % (mode, safe, h, off))


def known_pubs():
    ids = set()
    for d in (KEYS, os.path.join(OUT, "_work", "pages")):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".jsonl"):
                for r in read_jsonl(os.path.join(d, fn)):
                    if r.get("pub_id"):
                        ids.add(r["pub_id"])
    return ids


def extra_for(mode):
    if mode == "type1":
        return "&type=1"
    if mode == "type2":
        return "&type=2"
    return ""


def fetch_term(mode, term, off):
    fp = shard(mode, term, off)
    if os.path.exists(fp) and os.path.getsize(fp) > 0:
        return read_jsonl(fp)
    LIM.wait()
    url = ("%s/pubscripts-suggest-json/?search=%s&offset=%d%s"
           % (TV, quote(term), off, extra_for(mode)))
    body = fetch(url, timeout=30, tries=4, hdr=HDR)
    if not body:
        STAT.record("fail")
        return []
    try:
        res = (json.loads(body) or {}).get("results") or []
    except Exception:
        STAT.record("badjson")
        return []
    STAT.record(200)
    rows = [norm_suggest(o) for o in res if o.get("scriptIdPart")]
    if rows:
        write_jsonl(fp, rows)
    return rows


def sweep(mode, terms):
    limit = int(os.environ.get("TV_EXPAND_LIMIT", "25000") or 25000)
    if limit and len(terms) > limit:
        terms = terms[:limit]
    log("mode=%s terms=%d" % (mode, len(terms)))
    before = len(known_pubs())
    seen = set()
    t0 = time.time()

    def one(term):
        got = []
        for off in range(0, MAX_OFF + 1, STEP):
            rows = fetch_term(mode, term, off)
            if not rows:
                break
            got.extend(rows)
        return got

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, rows in enumerate(ex.map(one, terms)):
            seen.update(r["pub_id"] for r in rows if r.get("pub_id"))
            if i % 100 == 0 or i == len(terms) - 1:
                el = time.time() - t0
                log("  %s %d/%d ids=%d new=%d %.2f/s"
                    % (mode, i + 1, len(terms), len(seen), len(seen) - before,
                       (i + 1) / max(1e-6, el)))
                log("PROG expand|%d|%d|%s" % (i + 1, len(terms), mode))
    log("mode=%s done: %d ids, %d new, %s" % (mode, len(seen), len(seen) - before, STAT.report()))


def harvest_tokens():
    tc = Counter()
    sources = [os.path.join(OUT, "_manifest.jsonl"),
               os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl")]
    for src in sources:
        if not os.path.exists(src):
            continue
        for r in read_jsonl(src):
            for w in TOKEN.findall((r.get("name") or "") + " " + (r.get("description") or "")[:1500]):
                w = w.lower()
                if len(w) >= 4 and w not in STOP and not w.isdigit():
                    tc[w] += 1
    return tc


def token_list():
    return [w for w, _ in harvest_tokens().most_common()]


def mode_type():
    terms = token_list()
    log("type mode: %d tokens" % len(terms))
    sweep("type1", terms)
    sweep("type2", terms)


def mode_seeds():
    old = set(token_list())
    fresh = [w for w, _ in harvest_tokens().most_common() if w not in old]
    log("seeds mode: %d fresh description tokens" % len(fresh))
    sweep("seed", fresh)


def mode_author():
    authors = Counter()
    for r in read_jsonl(os.path.join(OUT, "_manifest.jsonl")):
        a = (r.get("author") or "").strip()
        if a:
            authors[a] += 1
    terms = sorted(authors)
    log("author mode: %d authors" % len(terms))
    sweep("author", terms)


def mode_slice():
    base = token_list()[:2000]
    terms = []
    for w in base:
        for c in "abcdefghijklmnopqrstuvwxyz":
            terms.append(w + " " + c)
    log("slice mode: %d sliced queries" % len(terms))
    sweep("slice", terms)


def main():
    logf = open(LOG, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = logf
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "type"):
        mode_type()
    if only in ("all", "seeds"):
        mode_seeds()
    if only in ("all", "author"):
        mode_author()
    if only in ("all", "slice"):
        mode_slice()
    log("expansion complete: %s" % STAT.report())


if __name__ == "__main__":
    main()
