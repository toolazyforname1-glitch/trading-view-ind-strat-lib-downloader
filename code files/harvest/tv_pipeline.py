import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
import json, os, re, sys, threading, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_lib import (ensure_dirs, fetch, extract_scripts, page_url, suggest_url,
                    norm, norm_suggest, write_jsonl, read_jsonl, PAGES, KEYS, OUT)

TYPES = ["indicators", "strategies", "libraries"]
LIST_SORTS = ["recent", "recent_extended", "latest_popular"]
API_SORTS = ["recent_extended", "recent", "latest_popular", "trending",
             "week_popular", "picked_time"]
API_MAX_PAGE = 50
API_HDR = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
           "Accept": "application/json,text/plain,*/*",
           "Referer": "https://www.tradingview.com/scripts/"}
STOP = set("""the and for with from that this your you our are was were will can not
free best new pro buy sell long short signal alert auto upper lower high low open
close level zone block order tool smart money market price chart indicator strategy
system script version updated exclusive premium tradingview forex crypto stock
scalping intraday swing daily weekly multi super simple advanced classic""".split())
EXTRA_SEEDS = """rsi macd ema sma bollinger atr adx stoch stochastic ichimoku supertrend
vwap fibonacci pivot support resistance trend momentum volume breakout divergence
cumulative delta order flow anchored profile multi time frame mtf custom candles
heikin ashi renko grid martingale lot position risk reward trailing scalping swing
intraday overbought oversold oscillator arrow panel table shape label line box
background plot color theme session london new york asia killzone premarket""".split()
FACADE = "https://pine-facade.tradingview.com/pine-facade/get/%s/last"
FACADE_HDR = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
              "Accept": "application/json,text/plain,*/*",
              "Referer": "https://www.tradingview.com/"}
BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class NullReporter:
    def event(self, ev):
        pass


def safe_name(name, tv_id, pub_id):
    n = BAD.sub("", (name or "").strip())
    n = re.sub(r"\s+", " ", n).strip(" .") or "unnamed"
    tid = tv_id or (pub_id.split(";")[-1][:8] if pub_id else "noID")
    return ("%s [%s].pine" % (n[:120], tid)).strip()


class Pipeline:
    def __init__(self, reporter=None, workers=6, delay=0.0, scope="all",
                 max_page=8000, keyword_limit=3000, out=OUT, download_limit=0):
        self.rep = reporter or NullReporter()
        self.workers = max(1, workers)
        self.delay = delay
        self.scope = scope
        self.max_page = max_page
        self.keyword_limit = keyword_limit
        self.download_limit = download_limit
        self.out = out
        self.stop = threading.Event()
        self.by_pub = {}
        self.origin = defaultdict(set)
        self.total_feeds = 0
        self.done_feeds = 0
        self.t0 = time.time()

    # ---------- events ----------
    def ev(self, **kw):
        kw["t"] = time.time()
        self.rep.emit_event(kw)

    def log(self, text, kind="info"):
        self.ev(ev="log", text=text, kind=kind)

    def phase(self, name, state="start"):
        self.ev(ev="phase", name=name, state=state)

    def task(self, name, done, total, **extra):
        self.ev(ev="task", name=name, done=done, total=total, **extra)

    def stat(self, key, value):
        self.ev(ev="stat", key=key, value=value)

    # ---------- helpers ----------
    def _throttle(self):
        if self.delay:
            time.sleep(self.delay)

    def types(self):
        return TYPES if self.scope == "all" else ["indicators"]

    # ---------- listing feeds ----------
    def _list_shard(self, t, sort, page):
        fp = os.path.join(PAGES, "list__%s__%s__p%05d.jsonl" % (t, sort, page))
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            return ("cached", read_jsonl(fp))
        self._throttle()
        html = fetch(page_url(t, sort, page))
        if html is None:
            return ("fail", [])
        objs = extract_scripts(html)
        if not objs:
            return ("empty", [])
        rows = [norm(o) for o in objs]
        write_jsonl(fp, rows)
        return ("ok", rows)

    def _listing_feed(self, t, sort):
        name = "list %s/%s" % (t, sort)
        seen = set()
        base = None
        page = 1
        idle = 0
        wave = 16
        t0 = time.time()
        pages = 0
        items = 0
        while page <= self.max_page and not self.stop.is_set():
            batch = list(range(page, page + wave))
            with ThreadPoolExecutor(max_workers=self.workers) as ex:
                res = list(ex.map(lambda p: self._list_shard(t, sort, p), batch))
            for attempt in range(2):
                retry = [p for (st, rows), p in zip(res, batch) if not rows and st in ("fail", "bad")]
                if not retry:
                    break
                time.sleep(5 + attempt * 5)
                with ThreadPoolExecutor(max_workers=self.workers) as ex:
                    r2 = list(ex.map(lambda p: self._list_shard(t, sort, p), retry))
                merged = dict(zip(batch, res))
                merged.update(dict(zip(retry, r2)))
                res = [merged[p] for p in batch]
            if base is None:
                if not res[0][1]:
                    self.log("listing %s/%s: page1 unavailable" % (t, sort), "warn")
                    self.task(name, 0, 0, state="skip")
                    return
                base = frozenset(r["pub_id"] for r in res[0][1])
            new = 0
            wrapped = False
            for (st, rows), p in zip(res, batch):
                pages += 1
                if not rows:
                    idle += 1
                    continue
                items += len(rows)
                ids = {r["pub_id"] for r in rows}
                new += len(ids - seen)
                seen |= ids
                if p != 1 and ids == base:
                    wrapped = True
            idle = 0 if new else idle + 1
            el = time.time() - t0
            self.task(name, pages, 0, items=items, unique=len(seen),
                      rate=(pages / el if el else 0), state="run")
            if wrapped or idle >= 4:
                self.log("listing %s/%s: end at page ~%d (%d items, %d unique) %s"
                         % (t, sort, page + wave - 1, items, len(seen),
                            "(wrapped)" if wrapped else "(no new ids)"), "ok")
                self.task(name, pages, pages, items=items, unique=len(seen),
                          rate=(pages / el if el else 0), state="done")
                self.done_feeds += 1
                self.total_feeds += 1
                return
            page += wave
        self.log("listing %s/%s: stopped at page ~%d (%d items)" % (t, sort, page, items), "warn")
        self.task(name, pages, pages, items=items, unique=len(seen), state="done")
        self.done_feeds += 1
        self.total_feeds += 1

    # ---------- api feeds ----------
    def _api_shard(self, t, sort, page):
        fp = os.path.join(PAGES, "api__%s__%s__p%05d.jsonl" % (t, sort, page))
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            return ("cached", read_jsonl(fp))
        self._throttle()
        url = ("https://www.tradingview.com/api/v1/scripts/?page=%d&script_type=%s&sort=%s"
               % (page, t, sort))
        body = fetch(url, timeout=40, tries=4, hdr=API_HDR)
        if body is None:
            return ("fail", [])
        try:
            j = json.loads(body)
        except Exception:
            return ("bad", [])
        rows = [norm(o) for o in (j.get("results") or []) if o.get("script_id_part")]
        write_jsonl(fp, rows)
        return ("ok", rows)

    def _api_feed(self, t, sort):
        name = "api %s/%s" % (t, sort)
        t0 = time.time()
        n = 0
        pages = list(range(1, API_MAX_PAGE + 1))
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            res = list(ex.map(lambda p: self._api_shard(t, sort, p), pages))
        for attempt in range(2):
            retry = [p for (st, rows), p in zip(res, pages) if not rows and st in ("fail", "bad")]
            if not retry:
                break
            time.sleep(5 + attempt * 5)
            with ThreadPoolExecutor(max_workers=self.workers) as ex:
                r2 = list(ex.map(lambda p: self._api_shard(t, sort, p), retry))
            merged = dict(zip(pages, res))
            merged.update(dict(zip(retry, r2)))
            res = [merged[p] for p in pages]
        for (st, rows), p in zip(res, pages):
            n += len(rows)
            self.task(name, p, API_MAX_PAGE, items=n, rate=(p / max(1e-6, time.time() - t0)))
        self.task(name, API_MAX_PAGE, API_MAX_PAGE, items=n, state="done")
        self.log("api %s/%s: %d items" % (t, sort, n), "ok")
        self.done_feeds += 1
        self.total_feeds += 1

    # ---------- keyword sweep ----------
    def _kw_shard(self, term):
        fp = os.path.join(KEYS, re.sub(r"[^a-z0-9]+", "_", term.lower())[:60] + ".jsonl")
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            return ("cached", read_jsonl(fp))
        self._throttle()
        body = fetch(suggest_url(term), timeout=30, tries=3,
                     hdr={"User-Agent": "Mozilla/5.0",
                          "Referer": "https://www.tradingview.com/scripts/"})
        if body is None:
            return ("fail", [])
        try:
            j = json.loads(body)
        except Exception:
            return ("bad", [])
        rows = [norm_suggest(o) for o in (j.get("results") or []) if o.get("scriptIdPart")]
        write_jsonl(fp, rows)
        return ("ok", rows)

    def _keyword_sweep(self, seeds):
        name = "keyword sweep"
        t0 = time.time()
        hits = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            res = list(ex.map(self._kw_shard, seeds))
        for i, (st, rows) in enumerate(res):
            hits += len(rows)
            if i % 25 == 0 or i == len(res) - 1:
                self.task(name, i + 1, len(seeds), hits=hits,
                          rate=((i + 1) / max(1e-6, time.time() - t0)))
        self.task(name, len(seeds), len(seeds), hits=hits, state="done")
        self.log("keyword sweep: %d terms -> %d raw hits" % (len(seeds), hits), "ok")
        self.done_feeds += 1
        self.total_feeds += 1

    # ---------- merge ----------
    def _merge(self):
        by_pub = {}
        origin = defaultdict(set)
        for fn in sorted(os.listdir(PAGES)):
            if not fn.endswith(".jsonl"):
                continue
            src = "/".join(fn[:-6].split("__")[:2])
            for r in read_jsonl(os.path.join(PAGES, fn)):
                p = r.get("pub_id")
                if not p:
                    continue
                origin[p].add(src)
                if p not in by_pub:
                    by_pub[p] = r
                else:
                    for k, v in r.items():
                        if not by_pub[p].get(k) and v:
                            by_pub[p][k] = v
        kw = 0
        for fn in sorted(os.listdir(KEYS)):
            if not fn.endswith(".jsonl"):
                continue
            for r in read_jsonl(os.path.join(KEYS, fn)):
                p = r.get("pub_id")
                if not p:
                    continue
                origin[p].add("keyword")
                if p not in by_pub:
                    kw += 1
                    by_pub[p] = r
                else:
                    for k, v in r.items():
                        if not by_pub[p].get(k) and v:
                            by_pub[p][k] = v
        self.by_pub = by_pub
        self.origin = origin
        self.stat("unique_pub_ids", len(by_pub))
        self.stat("from_keywords_only", kw)
        self.log("merged: %d unique scripts (%d only from keyword sweep)" % (len(by_pub), kw), "ok")

    # ---------- download ----------
    def _download(self):
        rows = list(self.by_pub.values())
        open_rows = [r for r in rows if str(r.get("access")) == "1"]
        unknown = [r for r in rows if r.get("access") is None]
        protected = len(rows) - len(open_rows) - len(unknown)
        todo = open_rows + unknown
        if self.download_limit:
            todo = todo[:self.download_limit]
        self.stat("open_scripts", len(open_rows))
        self.stat("protected_scripts", protected)
        self.log("protected (no source available): %d  -> manifest only" % protected, "warn")
        state_path = os.path.join(self.out, "_downloaded.jsonl")
        done = set()
        if os.path.exists(state_path):
            for l in open(state_path, encoding="utf-8"):
                try:
                    done.add(json.loads(l)["pub_id"])
                except Exception:
                    pass
        self.log("resuming: %d already on disk" % len(done), "info")
        state = open(state_path, "a", encoding="utf-8")
        lock = threading.Lock()
        counters = Counter()
        name = "source download"
        t0 = time.time()
        total = len(todo)
        self.task(name, 0, total, state="run")

        def work(rec):
            pub = rec.get("pub_id")
            if not pub or pub in done:
                return "skip"
            tgt = os.path.join(self.out, safe_name(rec.get("name"), rec.get("tv_id"), pub))
            if os.path.exists(tgt) and os.path.getsize(tgt) > 0:
                return "exists"
            self._throttle()
            body = fetch(FACADE % quote(pub, safe=""), timeout=40, tries=4, hdr=FACADE_HDR)
            if body is None:
                return "error"
            try:
                j = json.loads(body)
            except Exception:
                return "badjson"
            src = j.get("source")
            if not src:
                return "protected"
            tmp = tgt + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(src)
            os.replace(tmp, tgt)
            with lock:
                state.write(json.dumps({"pub_id": pub, "file": os.path.basename(tgt),
                                        "name": rec.get("name"), "author": rec.get("author"),
                                        "url": rec.get("url"), "bytes": len(src),
                                        "version": j.get("version")}, ensure_ascii=False) + "\n")
                state.flush()
                done.add(pub)
            return "ok"

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for i, st in enumerate(ex.map(work, todo)):
                counters[st] += 1
                if i % 50 == 0 or i == total - 1:
                    el = time.time() - t0
                    rate = (i + 1) / el if el else 0
                    eta_min = ((total - i - 1) / rate / 60) if rate else 0
                    self.task(name, i + 1, total, rate=rate,
                              eta_min=eta_min,
                              ends=time.strftime("%H:%M", time.localtime(time.time() + eta_min * 60)),
                              counters=dict(counters))
                    if counters["error"] and counters["error"] % 200 == 0:
                        self.log("source errors so far: %d" % counters["error"], "warn")
        state.close()
        self.task(name, total, total, state="done", counters=dict(counters))
        self.log("download finished: %s" % dict(counters), "ok")
        self.stat("downloaded_files", counters["ok"])

    # ---------- verify + catalog ----------
    def _verify(self):
        files = [f for f in os.listdir(self.out) if f.lower().endswith(".pine")]
        total_bytes = 0
        for f in files:
            try:
                total_bytes += os.path.getsize(os.path.join(self.out, f))
            except OSError:
                pass
        self.stat("pine_files", len(files))
        self.stat("total_mb", round(total_bytes / 1048576, 1))
        cat = os.path.join(self.out, "catalog.md")
        with open(cat, "w", encoding="utf-8") as f:
            f.write("# TradingView Pine library\n\n")
            f.write("- scripts enumerated: %d\n" % len(self.by_pub))
            f.write("- open-source (downloaded): %d\n" % len(files))
            f.write("- protected (no source): %d\n"
                    % sum(1 for r in self.by_pub.values() if str(r.get("access")) != "1"))
            f.write("- generated: %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("| # | Name | Author | Ver | Source | URL |\n|---|---|---|---|---|---|\n")
            rows = sorted(self.by_pub.values(),
                          key=lambda r: (-(r.get("likes") or 0), r.get("name") or ""))
            for i, r in enumerate(rows, 1):
                pub = r.get("pub_id")
                fname = safe_name(r.get("name"), r.get("tv_id"), pub)
                has = os.path.exists(os.path.join(self.out, fname))
                f.write("| %d | %s | %s | %s | %s | %s |\n" % (
                    i, (r.get("name") or "").replace("|", "/"),
                    (r.get("author") or "").replace("|", "/"),
                    r.get("version") or "",
                    ("[%s](%s)" % (fname, fname)) if has else "_protected_",
                    r.get("url") or ""))
        self.log("catalog written: %s" % cat, "ok")

    # ---------- orchestrator ----------
    def run(self):
        ensure_dirs()
        types = self.types()
        self.ev(ev="plan", plan={
            "ENUMERATE": (["list %s/%s" % (t, s) for t in types for s in LIST_SORTS]
                          + ["api %s/%s" % (t, s) for t in types for s in API_SORTS]),
            "KEYWORDS": ["keyword sweep"],
            "DOWNLOAD": ["source download"],
            "VERIFY": ["verify"],
        })
        self.phase("ENUMERATE", "start")
        for t in types:
            for s in LIST_SORTS:
                if self.stop.is_set():
                    break
                self._listing_feed(t, s)
            for s in API_SORTS:
                if self.stop.is_set():
                    break
                self._api_feed(t, s)
        self._merge()
        tokens = Counter()
        for r in self.by_pub.values():
            for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", r.get("name") or ""):
                w = w.lower()
                if len(w) >= 4 and w not in STOP and not w.isdigit():
                    tokens[w] += 1
        seeds = [w for w, _ in tokens.most_common(self.keyword_limit)]
        for w in EXTRA_SEEDS:
            if w not in seeds:
                seeds.append(w)
        self.phase("KEYWORDS", "start")
        self._keyword_sweep(seeds)
        self._merge()
        self.phase("DOWNLOAD", "start")
        self._download()
        self.phase("VERIFY", "start")
        self._verify()
        self.phase("DONE", "done")
        self.ev(ev="final", summary={"scripts": len(self.by_pub),
                                     "elapsed": time.time() - self.t0})
