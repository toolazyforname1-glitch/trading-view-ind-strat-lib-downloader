import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Enrichment collectors: facade metadata, versions, images, comments, languages.

Modes: meta | versions | images | comments | lang | all
Each writes a resumable jsonl under _work/enrich/ keyed by pub_id.
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT, LOGS
from tv_lib import fetch, read_jsonl, write_jsonl
from tv_rate import RateLimiter, StatusTracker

FACADE = "https://pine-facade.tradingview.com/pine-facade"
TV = "https://www.tradingview.com"
UA = ("Mozilla/5.0 (Windows NT 10.64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
DIR = os.path.join(OUT, "_work", "enrich")
LIM = RateLimiter(rate=10)
STAT = StatusTracker()
WORKERS = 12
LOG = os.path.join(LOGS, "enrich.log")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def open_rows():
    return [r for r in read_jsonl(os.path.join(OUT, "_manifest.jsonl")) if str(r.get("access")) == "1"]


def done_ids(fp):
    return {r.get("pub_id") for r in read_jsonl(fp) if r.get("pub_id")}


def collect(mode, rows, fn):
    os.makedirs(DIR, exist_ok=True)
    fp = os.path.join(DIR, mode + ".jsonl")
    have = done_ids(fp)
    todo = [r for r in rows if r.get("pub_id") and r["pub_id"] not in have]
    log("mode=%s todo=%d (already %d)" % (mode, len(todo), len(have)))
    out = open(fp, "a", encoding="utf-8")
    t0 = time.time()

    def one(r):
        LIM.wait()
        try:
            d = fn(r)
        except Exception as e:
            STAT.record("exc")
            return None
        if not d:
            STAT.record("fail")
            return None
        STAT.record(200)
        return dict(d, pub_id=r["pub_id"])

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, d in enumerate(ex.map(one, todo)):
            if d:
                out.write(json.dumps(d, ensure_ascii=False) + "\n")
                out.flush()
            if i % 500 == 0 or i == len(todo) - 1:
                log("  %s %d/%d %.1f/s" % (mode, i + 1, len(todo),
                                           (i + 1) / max(1e-6, time.time() - t0)))
                log("PROG enrich|%d|%d|%s" % (i + 1, len(todo), mode))
    out.close()
    log("mode=%s done %s" % (mode, STAT.report()))


def by_meta(r):
    body = fetch("%s/get/%s/last" % (FACADE, quote(r["pub_id"], safe=";")),
                 timeout=30, tries=3, hdr={"User-Agent": UA, "Referer": TV + "/"})
    if not body:
        return None
    j = json.loads(body)
    return {"name": j.get("scriptName"), "created": j.get("created"), "updated": j.get("updated"),
            "access": j.get("scriptAccess"), "facade_version": j.get("lastVersionMaj"),
            "kind": (j.get("extra") or {}).get("kind")}


def by_versions(r):
    """Probe older facade versions; store which ones exist."""
    found = []
    base = r.get("pub_id")
    for v in ("0", "1", "2", "3"):
        body = fetch("%s/get/%s/%s" % (FACADE, quote(base, safe=";"), v),
                     timeout=20, tries=1, hdr={"User-Agent": UA})
        if body and '"source"' in body:
            found.append(v)
    return {"versions": found} if found else None


def by_page(r, lang=None, key="image"):
    sid = r.get("tv_id") or (r.get("pub_id") or "")[4:12]
    hdr = {"User-Agent": UA}
    if lang:
        hdr["Accept-Language"] = lang
    body = fetch("%s/script/%s/" % (TV, sid), timeout=35, tries=3, hdr=hdr)
    if not body:
        return None
    if key == "image":
        m = re.search(r'<meta property="og:image" content="([^"]+)"', body)
        return {"image": m.group(1) if m else ""} if m else None
    if key == "comments":
        m = re.search(r'"comments_count"\s*:\s*(\d+)', body)
        return {"comments": int(m.group(1)) if m else 0}
    if key == "lang":
        m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
        return {"description": json.loads('"%s"' % m.group(1))} if m else None
    return None


def main():
    os.makedirs(DIR, exist_ok=True)
    lf = open(LOG, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = lf
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    rows = open_rows()
    log("open scripts: %d" % len(rows))
    if mode in ("all", "meta"):
        collect("meta", rows, by_meta)
    if mode in ("all", "versions"):
        collect("versions", rows[:5000], by_versions)
    if mode in ("all", "images"):
        collect("images", rows, lambda r: by_page(r, key="image"))
    if mode in ("all", "comments"):
        collect("comments", rows, lambda r: by_page(r, key="comments"))
    if mode in ("all", "lang"):
        for lang in ("it-IT", "es-ES", "fr-FR", "de-DE", "ja-JP"):
            collect("lang_" + lang, rows[:10000], lambda r, l=lang: by_page(r, l, "lang"))
    log("enrichment complete: %s" % STAT.report())


if __name__ == "__main__":
    main()
