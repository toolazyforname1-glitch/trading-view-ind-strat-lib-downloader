import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
import json, os, re, threading, time, urllib.error, urllib.request
from tv_config import HERE, OUT

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HDR = {"User-Agent": UA,
       "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
       "Accept-Language": "en-US,en;q=0.9",
       "Referer": "https://www.tradingview.com/scripts/"}
TV = "https://www.tradingview.com"
OUT = OUT
WORK = os.path.join(OUT, "_work")
PAGES = os.path.join(WORK, "pages")
KEYS = os.path.join(WORK, "keywords")
DEC = json.JSONDecoder()
ARR_RE = re.compile(r'\[\{"id":\d+')
_lock = threading.Lock()


def ensure_dirs():
    for d in (OUT, WORK, PAGES, KEYS):
        os.makedirs(d, exist_ok=True)


def fetch(url, timeout=45, tries=5, hdr=None):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=hdr or HDR)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code == 429:
                ra = e.headers.get("Retry-After") if e.headers else None
                wait = float(ra) if (ra and str(ra).isdigit()) else min(90, 5 * (2 ** i))
                time.sleep(wait)
                continue
            if e.code in (500, 502, 503, 504):
                time.sleep(min(30, 2 * (i + 1)))
                continue
            return None
        except Exception as e:
            last = str(e)
            time.sleep(1.5 * (i + 1))
    with _lock:
        print("    ! fetch failed %s :: %s" % (url, last))
    return None


def _try_array(html, s):
    try:
        obj, _ = DEC.raw_decode(html[s:])
    except Exception:
        return None
    if (isinstance(obj, list) and obj and isinstance(obj[0], dict)
            and "script_id_part" in obj[0]):
        return obj
    return None


def extract_scripts(html):
    """Find the SSR JSON array of script objects inside a listing page."""
    best = []
    pos = html.find('"script_id_part"')
    if pos >= 0:
        cands = []
        i = pos
        while len(cands) < 40:
            i = html.rfind("[", 0, i)
            if i < 0:
                break
            cands.append(i)
        for s in cands:
            o = _try_array(html, s)
            if o and len(o) > len(best):
                best = o
                if len(best) >= 24:
                    break
    for m in ARR_RE.finditer(html):
        o = _try_array(html, m.start())
        if o and len(o) > len(best):
            best = o
    return best


def page_url(t, sort, page):
    return "%s/scripts/page-%d/?script_type=%s&sort=%s" % (TV, page, t, sort)


def suggest_url(term):
    from urllib.parse import quote
    return "%s/pubscripts-suggest-json/?search=%s" % (TV, quote(term))


def norm(o):
    u = o.get("user")
    author = u.get("username") if isinstance(u, dict) else (u or "")
    return {
        "pub_id": o.get("script_id_part", "") or "",
        "tv_id": o.get("image_url", "") or "",
        "name": (o.get("name") or "").strip(),
        "author": author or "",
        "access": o.get("script_access"),
        "script_type": o.get("script_type", "") or "",
        "version": str(o.get("version", "") or ""),
        "likes": o.get("likes_count", 0) or 0,
        "views": o.get("views_count", 0) or 0,
        "url": o.get("chart_url", "") or "",
        "created_at": o.get("created_at", "") or "",
        "updated_at": o.get("updated_at", "") or "",
        "num_id": o.get("id"),
        "description": o.get("description", "") or "",
    }


def norm_suggest(o):
    a = o.get("author")
    author = a.get("username") if isinstance(a, dict) else (a or "")
    return {
        "pub_id": o.get("scriptIdPart", "") or "",
        "tv_id": "",
        "name": (o.get("scriptName") or o.get("title") or "").strip(),
        "author": author or "",
        "access": o.get("access"),
        "script_type": o.get("type", "") or "",
        "version": str(o.get("version", "") or ""),
        "likes": o.get("agreeCount", 0) or 0,
        "views": 0,
        "url": "",
        "created_at": "",
        "updated_at": "",
        "num_id": None,
        "description": "",
    }


def write_jsonl(fp, rows):
    tmp = fp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, fp)


def read_jsonl(fp):
    out = []
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return out
