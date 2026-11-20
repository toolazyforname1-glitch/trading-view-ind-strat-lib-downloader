import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Scrape full descriptions for every open-source script.

PHASE 1  re-walk the search space, capturing `imageUrl` (the short id) that the
         earlier normalizer discarded.  One request per (token, offset) pair.
PHASE 2  fetch each open-source script's page and extract the FULL description
         (the listing/API copies are truncated server-side to 500 chars).

Both phases append to jsonl and skip work already on disk, so the job is
resumable.  Emits PROG lines for the watcher.
"""
import json, os, re, sys, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT, KEYS, PAGES
from tv_config import LOGS

TV = "https://www.tradingview.com"
UA = ("Mozilla/5.0 (Windows NT 10.64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
        "Referer": TV + "/", "Accept": "text/html,application/xhtml+xml,*/*"}
DESC_DIR = os.path.join(OUT, "_work", "descriptions")
IDS_FILE = os.path.join(DESC_DIR, "ids.jsonl")
DESC_FILE = os.path.join(DESC_DIR, "descriptions.jsonl")
LOG_FILE = os.path.join(LOGS, "desc.log")
SWEEP_WORKERS = 32
PAGE_WORKERS = 12
STEP = 50
MAX_OFF = 950

_tls = threading.local()
_lock = threading.Lock()
_counts = Counter()


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def session():
    s = getattr(_tls, "s", None)
    if s is None:
        import requests
        s = requests.Session()
        s.headers.update(HDRS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8)
        s.mount("https://", adapter)
        _tls.s = s
    return s


def get(url, tries=4):
    for i in range(tries):
        try:
            r = session().get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            with _lock:
                _counts["http_%d" % r.status_code] += 1
            if r.status_code in (403, 429, 503):
                time.sleep(5 + i * 10 + (i * 3 % 7))
                continue
            return None
        except Exception as e:
            with _lock:
                _counts["exc"] += 1
            time.sleep(2 + i * 5)
    return None


def tokens_from_shards():
    tc = Counter()
    for d in (PAGES, KEYS):
        for fn in os.listdir(d):
            if not fn.endswith(".jsonl"):
                continue
            for r in read_jsonl(os.path.join(d, fn)):
                for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", r.get("name") or ""):
                    w = w.lower()
                    if len(w) >= 4 and not w.isdigit():
                        tc[w] += 1
    return [w for w, _ in tc.most_common()]


def load_ids():
    ids = {}
    if os.path.exists(IDS_FILE):
        for r in read_jsonl(IDS_FILE):
            if r.get("pub_id") and r.get("sid"):
                ids[r["pub_id"]] = r["sid"]
    return ids


def phase1():
    tokens = tokens_from_shards()
    known = load_ids()
    log("phase1: %d tokens, %d short ids already known" % (len(tokens), len(known)))
    out = open(IDS_FILE, "a", encoding="utf-8")
    done = [0]
    t0 = time.time()

    def one(token):
        got = []
        for off in range(0, MAX_OFF + 1, STEP):
            url = "%s/pubscripts-suggest-json/?search=%s&offset=%d" % (TV, quote(token), off)
            body = get(url)
            if not body:
                break
            try:
                res = (json.loads(body) or {}).get("results") or []
            except Exception:
                break
            if not res:
                break
            for o in res:
                pub = o.get("scriptIdPart")
                sid = o.get("imageUrl")
                if pub and sid and pub not in known:
                    known[pub] = sid
                    got.append({"pub_id": pub, "sid": sid,
                                "name": o.get("scriptName") or o.get("title") or "",
                                "version": o.get("version") or "",
                                "type": o.get("type"),
                                "likes": o.get("agreeCount")})
            if len(got) >= 200:
                with _lock:
                    for g in got:
                        out.write(json.dumps(g, ensure_ascii=False) + "\n")
                    out.flush()
                    done[0] += len(got)
                    got = []
        with _lock:
            for g in got:
                out.write(json.dumps(g, ensure_ascii=False) + "\n")
            out.flush()
            done[0] += len(got)
        return len(got)

    with ThreadPoolExecutor(max_workers=SWEEP_WORKERS) as ex:
        for i, _ in enumerate(ex.map(one, tokens)):
            if i % 100 == 0 or i == len(tokens) - 1:
                el = time.time() - t0
                log("  phase1 token %d/%d  ids %d  %.1f tok/s"
                    % (i + 1, len(tokens), len(known), (i + 1) / max(1e-6, el)))
                log("PROG sweep|%d|%d|ids" % (i + 1, len(tokens)))
    out.close()
    log("phase1 done: %d short ids" % len(known))
    return known


RE_DIV = re.compile(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', re.S)
RE_META = re.compile(r'<meta\s+(?:name|property)="(?:og:)?description"\s+content="([^"]*)"')
TAG = re.compile(r"<[^>]+>")


def unescape(s):
    import html
    return html.unescape(s)


def clean_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = TAG.sub("", s)
    s = unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


RE_JSON_DESC = re.compile(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _norm(s):
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def extract_description(html):
    """Full description: the page's SSR JSON "description" field.

    The visible <div class="description-XXXX"> is a hashed CSS module whose
    content is a relative timestamp ("2 days ago"), NOT the description.
    The meta tag carries the page's own copy but truncated at ~500 chars.
    """
    m = RE_META.search(html)
    meta = _norm(m.group(1)) if m else ""
    cands = []
    for mm in RE_JSON_DESC.finditer(html):
        try:
            val = json.loads('"%s"' % mm.group(1))
        except Exception:
            continue
        if val:
            cands.append(val)
    if meta:
        key = meta[:60]
        for v in cands:
            nv = _norm(v)
            if nv[:40].startswith(key[:40]) or key[:40].startswith(nv[:40]):
                return v
    if cands:
        return max(cands, key=len)
    return meta


def phase2(ids):
    rows = list(read_jsonl(os.path.join(OUT, "_manifest.jsonl")))
    open_rows = [r for r in rows if str(r.get("access")) == "1"]
    done_pub = set()
    if os.path.exists(DESC_FILE):
        for r in read_jsonl(DESC_FILE):
            if r.get("pub_id"):
                done_pub.add(r["pub_id"])
    todo = []
    no_id = 0
    for r in open_rows:
        pub = r.get("pub_id")
        if not pub or pub in done_pub:
            continue
        sid = r.get("tv_id") or ids.get(pub)
        if not sid:
            no_id += 1
            continue
        todo.append((pub, sid, r.get("name") or "", r.get("description") or ""))
    log("phase2: %d to fetch (%d already done, %d without a short id)"
        % (len(todo), len(done_pub), no_id))
    out = open(DESC_FILE, "a", encoding="utf-8")
    stats = Counter()
    t0 = time.time()

    def one(item):
        pub, sid, name, prev = item
        html = get("%s/script/%s/" % (TV, sid))
        if not html:
            with _lock:
                stats["fail"] += 1
            return
        desc = extract_description(html)
        agree = 1 if prev and desc and _norm(desc).startswith(_norm(prev)[:60]) else 0
        with _lock:
            stats["ok" if desc else "empty"] += 1
            stats["agrees"] += agree
            out.write(json.dumps({"pub_id": pub, "sid": sid, "name": name,
                                  "description": desc, "len": len(desc),
                                  "prev_agrees": agree}, ensure_ascii=False) + "\n")
            out.flush()

    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        for i, _ in enumerate(ex.map(one, todo)):
            if i % 200 == 0 or i == len(todo) - 1:
                el = time.time() - t0
                rate = (i + 1) / max(1e-6, el)
                log("  phase2 %d/%d  ok=%d empty=%d fail=%d  %.1f pages/s  eta %.0f min"
                    % (i + 1, len(todo), stats["ok"], stats["empty"], stats["fail"],
                       rate, (len(todo) - i - 1) / max(0.01, rate) / 60))
                log("PROG sweep|%d|%d|pages" % (i + 1, len(todo)))
    out.close()
    log("phase2 done: ok=%d empty=%d fail=%d  prefix-agreement=%d"
        % (stats["ok"], stats["empty"], stats["fail"], stats["agrees"]))


def main():
    os.makedirs(DESC_DIR, exist_ok=True)
    logf = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = logf
    sys.stderr = logf
    t0 = time.time()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "1"):
        ids = phase1()
    else:
        ids = load_ids()
        log("phase1 skipped, %d short ids loaded" % len(ids))
    if only in ("all", "2"):
        phase2(ids)
    log("http status counts: %s" % dict(_counts))
    log("total elapsed %.1f min" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
