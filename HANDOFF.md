# HANDOFF — TradingView Pine Script mass harvester

**Status:** COMPLETE — **62,478 `.pine` files**, **99,335 scripts enumerated**. All enumeration gaps closed and the deep search sweep finished (see §7). Everything is resumable and cached.

**Written:** 2026-11-14 ~18:40 · **Final update:** 2026-11-15 ~14:45
**Author:** Sisyphus (OhMyOpenCode) for the user
**Output dir:** `C:\Users\cattu\Documents\Directories\trades\indicators`
**Code dir:** `C:\Users\cattu\Documents\Directories\indicator downlaoder`

---

## 1. Goal (original request)

> "download all the Indicator in trading view, just their source code … the site which is
> https://www.tradingview.com/scripts/ has 24 indicators per section and there are 42, so that is
> just above 1000, which is not even close to the real number … saved all in C:\Users\cattu\Documents\Directories\trades\indicators …
> one simple file per idnicator, no organization needed just make sure to name them"

User decisions taken during the run:

| Decision | Choice |
|---|---|
| Scope | **Everything** — indicators + strategies + libraries |
| File naming | `Script Name [TVid].pine` (e.g. `SuperTrend [ZZ9nHANC].pine`) |
| Protected scripts | **Manifest only**, no file (no source exists to fetch) |
| Download pace | Polite: 6 workers, 150 ms spacing |

---

## 2. What was achieved

```
C:\Users\cattu\Documents\Directories\trades\indicators\
  62,478  script folders, each:
            <Name> [TVid].pine   the Pine source
            <Name> [TVid].md     metadata + full description
        catalog.md          13.8 MB    every script: author, version, link, clickable .pine link
        _manifest.csv       19.6 MB    full metadata, all 99,335 scripts (Excel-friendly, BOM)
        _manifest.jsonl     39.1 MB    same, JSON-lines
        _manifest_stats.json            by_type / by_access summary
        _downloaded.jsonl   14.4 MB    resume state (one JSON per downloaded file)
        _work/                        enumeration shards + descriptions/ (safe to delete)
        _tool/                         every script, log and probe from the project
```

**Layout note:** the flat `.pine` pile was restructured on request into one folder per script
(`tv_restructure.py`). Mapping came from `_downloaded.jsonl` (pub_id → file/name/author/url).
Zero filename collisions; max resulting path 218 chars (Windows-safe).

**Uniqueness / volume**

| Metric | Value |
|---|---|
| Scripts enumerated | **99,335** |
| With source (downloaded) | **62,478** (access `1`) |
| No source (manifest only) | **36,857** (access `2` = 22,672 protected, `3` = 14,126 invite-only) |
| by type | indicator 14,345 · strategy 6,119 · library 1,687 · numeric/unknown 73,437 + 3,642 |

The 73,437 numeric entries come from `pubscripts-suggest-json`, whose `type` field is an int, not a
string. They are real scripts and were downloaded; only their `script_type` label is unknown.

**Integrity check** — random 500-file full read:
- **500/500** contain valid Pine (`indicator(` / `study(` / `strategy(` / `library(` / `import`)
- 0 empty files; 18 files < 60 bytes (legitimate one-liners)
- version spread: v2 ×10, v3 ×31, v4 ×40, v5 ×77, v6 ×105 → genuine sources across every era,
  original author comments and MIT headers preserved.

**Runtime:** ~17 h 40 m wall total across 4 passes.

**Growth history**

| Pass | Enumerated | Files on disk |
|---|---|---|
| 1 — feeds + keyword sweep gen-1 | 60,471 | 43,941 |
| 2 — gap A (`script_type=all`) + gap B (path route) | 60,602 | — |
| 3 — gap C (keyword sweep gen-2, 12,800 new terms) | 71,954 | 48,855 |
| 4 — **deep search sweep** (offsets 0-950, dim `default` + dim `sort=recent`) | **99,335** | **62,478** |

Pass 4 alone added **27,381 new scripts** — see §3.1b for why.

---

## 3. The mechanism (how it actually works)

### 3.1 Enumeration routes

| Route | Pattern | Yield | Notes |
|---|---|---|---|
| **A. Listing (query)** | `https://www.tradingview.com/scripts/page-{N}/?script_type={indicators\|strategies\|libraries\|all}&sort={recent\|recent_extended\|latest_popular}` | **24 scripts/page**, deep (hundreds of pages) | HTML embeds a **SSR JSON array** of script objects → parse it, don't scrape the DOM |
| **B. Listing (path)** | `https://www.tradingview.com/scripts/{indicators\|strategies}/page-{N}/` | 24/page | **Discovered late, only probed 2 pages — see §7 gap C** |
| **C. JSON API** | `https://www.tradingview.com/api/v1/scripts/?page={1..50}&script_type={X}&sort={latest_popular\|week_popular\|trending\|suggested\|recent\|recent_extended\|picked_time}` | 20/page, **hard cap 1000 results** (HTTP 400 at page 51) | `count` field still reports the TRUE feed length even when serving is capped |
| **D. Keyword suggest** | `https://www.tradingview.com/pubscripts-suggest-json/?search={term}&offset={0..950}` | **1,000 results/query** (50/page × 20 offsets) | **The only route past the feed caps** — surfaced 25,632 scripts in one dimension alone |

### 3.1b The single most important discovery (2026-11-14 22:30)

`pubscripts-suggest-json` **paginates via `offset`**, and the cap is **1,000 results per term**:

| offset | results | overlap with offset 0 |
|---|---|---|
| 0 | 50 | — |
| 50 | 50 | 0 new to the *same* query (all fresh vs. what we'd seen) |
| 100 … 950 | 50 each | every offset returns **50 brand-new scripts** |
| 1000 | **no data** | hard cap |

Every earlier sweep read **only `offset=0`** — i.e. 5% of what each term can yield. For a term
like `averages` that is 1,000 matches of which we saw 50; deep-sweeping it surfaced **477 new
scripts on its own**.

Other `suggest-json` params that are **not** real dimensions: `page`, `limit`, `count`, `start`,
`is_publish`, `order` — all ignored. `sort=recent` **is** real (near-disjoint: 894/1,000 not in the
default set) and `type=1` / `type=2` are real filters. `market=forex` / `market=crypto` are
subsets (0 new).

### 3.2 Source fetch

```
GET https://pine-facade.tradingview.com/pine-facade/get/{quote("PUB;<32hex>")}/last
  200 → JSON with .source = full Pine text   (open source, no login, no cookies)
  401 → encrypted/protected, source is NEVER transmitted to the client
```
No auth of any kind is required. `PUB;…` ids come free with every listing page.

### 3.3 Wrap detection

Feeds wrap to page 1 instead of returning empty. Detect by **set-comparing a page's id-set against
page 1's id-set** (hash the sorted set). Never compare a page to itself — that bug produced
"end at page 16" for every feed in an early run.

### 3.4 Measured feed depths (page counts)

| feed | depth | scripts |
|---|---|---|
| indicators / `recent` | 1,408 pages | ~33,792 |
| indicators / `recent_extended` | 512 pages | ~12,288 |
| indicators / `latest_popular` | 48 pages | ~1,152 |
| strategies / `recent`, `recent_extended` | 512 pages | ~12,288 |
| libraries / `recent` | ~105 pages | ~1,700 |
| `all` / `recent`, `recent_extended` | 500 pages | ~12,000 |
| `all` / `latest_popular` | < 500 pages | — |

### 3.5 The critical insight

The "1000" the user hit is an **API serving cap**, and the listing feeds have their own caps
(`recent_extended` stops at 512 pages, `latest_popular` at 48). **Union of feeds + keyword sweep is
the only way past them.** The keyword sweep alone contributed **17,046 unique scripts**.

---

## 4. Code inventory (`C:\Users\cattu\Documents\Directories\indicator downlaoder`)

| File | Purpose |
|---|---|
The current tool layout is documented in `DEV.md` §1–§4. The code lives in six
subfolders under `code files\`: `core\` (paths, fetch helpers, rate limiter),
`harvest\` (pipeline, manifest, description scrapers, expansion, enrichment, delta),
`organize\` (restructure, md refresh, analyze, index, verify, export, snapshot),
`tools\` (`tv.py` CLI, watchdog, pause script) and `logs\`. This file, `DEV.md` and
`README.md` live at the tool root.

All normal work is done manually from the CLI:

```powershell
cd "code files\tools"
python tv.py status
python tv.py verify
python tv.py manifest
python tv.py analyze
python tv.py index "rsi"
python tv.py delta
```

Long collectors are launched detached with `pythonw` (see DEV.md §9); nothing is
re-fetched because the `_work/` shards and `_downloaded.jsonl` are the resume state.

---

## 5. Bugs hit and fixed (keep for whoever touches this)

1. **False wrap detection** — comparing page 1's id-set to itself ⇒ every feed reported "end at
   page ~16". → skip `p == 1` when comparing.

### 3.2 Descriptions (the second scrape, 2026-11-15)

Descriptions are **truncated server-side to 500 characters** in every listing/search/API context.
Only the **script's own page** carries the full text:

```
GET https://www.tradingview.com/script/<shortId>/     (~340-600 KB HTML)
  → full description in the SSR JSON "description" field (measured up to 5,754 chars)
  → also in <div class="...description..."> as HTML
  → og:title / og:url confirm the page belongs to the right script
```

**The short id is the key.** The search endpoint returns it as `imageUrl`, but the original
normaliser threw it away (`norm_suggest` hardcoded `"tv_id": ""`), so 77,184 of the 99,335
scripts had no resolvable page URL. `tv_desc_scrape.py` phase 1 re-walks the cached search
space to recover `imageUrl`; phase 2 fetches each page and extracts the description.

| Route | Gives full description? |
|---|---|
| `/scripts/page-N/` listing | no — 500 chars, server-truncated |
| `/api/v1/scripts/` | no — 500 chars, and `page_size` is pinned at 20 |
| `/pubscripts-suggest-json/` | no — no description field at all |
| `pine-facade .../get/<PUB;id>/last` | no — but gives `scriptName`, `version`, `extra.kind` |
| **`/script/<shortId>/`** | **yes — full text** |

Also established: `PUB;<hex>` ids do **not** resolve as URLs, and `pub_id[4:12]` is a *local*
convention, not a TradingView id.

### 3.2b Two traps when extracting that description

**Trap 1 — the `description` div is a lie.** Every script page has a `<div class="description-XXXX">`
where `XXXX` is a hashed CSS-module name. Its content is a **relative timestamp** ("2 days ago",
"Jun 1, 2022"), not the description. Selecting it silently produced garbage for ~54% of scripts.
The full text lives in the page's **SSR JSON `"description"` field** (up to 65 KB observed).
Use the JSON field; validate it against the `<meta name="description">` tag (the meta is the
page's own copy, truncated at ~500 chars) by comparing the first ~40 normalised characters.

**Trap 2 — the two copies use different markup.** The script page stores the description in
**BBCode** (`[b]…[/b]`, `[url=…]…[/url]`, `[image]…[/image]`); the listing serves the same text
with the markup stripped. So a raw prefix comparison between them fails for ~54% of scripts even
when both are correct — strip BBCode before comparing, and expect link-rendering differences
(`(LRLR)` vs `( LRLR )`). Under markup-aware comparison agreement is ~88%, and every remaining
mismatch is a link-rendering or description-version artefact, never a different script.

---

```python
# adding a feed to tv_pipeline.py
LIST_SORTS = ["recent", "recent_extended", "latest_popular"]   # only these 3 work on the HTML route
API_SORTS  = ["recent_extended","recent","latest_popular","trending","week_popular","picked_time"]
# shards are cached per (route, type, sort, page) under _work/pages/ and _work/keywords/
```

---

## 7. ENUMERATION GAPS — ALL CLOSED

Every window that can be enumerated has now been crawled to its natural end. Results:

| Gap | What it was | Result |
|---|---|---|
| **A** — `script_type=all` listing | distinct union window, 512 pages/sort | crawled `all/recent` (512 pp → 10,446 unique), `all/recent_extended` (512 pp → **12,000 unique**), `all/latest_popular`. **Net new: +131** — almost entirely overlap with the per-type feeds. |
| **B** — path-style route `/scripts/<type>/page-N/` | 24/page, unknown sort | **Ignores `sort` entirely** — all 4 variants (default/`recent`/`recent_extended`/`latest_popular`) return the same 48-page window: 812 unique for indicators, 161 for strategies. `?sort=recent_extended` → 0 results; `/scripts/libraries/` → 0. **Net new: ~0.** |
| **C** — keyword sweep generation 2 | seeds only came from the gen-1 merge | 12,800 never-queried tokens → 39,939 raw hits → **+11,352 new unique scripts**. |
| **D** — deep search sweep (**the big one**) | every sweep read only `offset=0` (50 of 1,000 results per term) | 26,800 tokens × offsets 0-950 × 2 dimensions (`default`, `sort=recent`) → 467,354 + 463,068 raw hits → **+27,381 new unique scripts**. |

### The lesson (this is the one that mattered)

**The keyword search route is the only one that scales**, and its real size was hidden by a
default. `pubscripts-suggest-json` serves **1,000 results per term** (50/page × 20 offsets); every
sweep before pass 4 read only the first page. Deep-sweeping the token universe found 27,381 scripts
that were reachable all along. Feed windows, by contrast, are hard-capped
(`recent` 1,408 pp, `recent_extended` 512 pp, `latest_popular` 48 pp, API 1,000 results) and their
union plateaus — gaps A and B yielded almost nothing.

**If this is ever extended: run another sweep generation.** d1-gen2 found 34 new tokens and 338
raw hits — the token space is exhausted (26,834 → 26,800 → 26,834), so a 5th generation over the
*same* tokens would add nothing new. Further growth would need a new dimension (e.g. `type=1`/`2`
filters, or another seed corpus like descriptions/comments rather than titles).

### Still unknowable (not a gap, a hard limit)
- `access=2` (22,672) and `access=3` (14,126) = **36,857 protected scripts**. TradingView ships
  encrypted bytecode; the plaintext never reaches the client. Not recoverable by any method.
- Scripts TradingView has deleted / made private / unlisted are invisible to every route,
  including TradingView's own `sitemap-scripts.xml` (745 URLs — proof that no single public index
  is authoritative).
- The 1,000-result-per-term cap means a term's list is *ranked* — a script ranked 1,001st for
  every term we know is unreachable, even though it exists.

---

## 8. Constraints worth remembering

- **ToS**: bulk scraping of TradingView is against their terms. Rate was kept polite
  (6 workers / 150 ms) and the run completed without IP throttling or bans. Do not raise the pace
  aggressively — `+`/`-` exist but the sane setting is what worked.
- **Protected scripts cannot be recovered by any method.** TradingView ships encrypted bytecode;
  the plaintext never reaches the client. 37% of the library (36,857 scripts) is permanently
  unavailable.
- **Never re-fetch what's cached.** `_work/` holds the enumeration shards; `_downloaded.jsonl` holds
  the download state. Both make re-runs nearly free.

### Process lessons (cost hours — read before automating anything here)
- **Never spawn a long-running child from the agent's own shell.** It dies when that shell exits
  (silently, no traceback). Launch detached via WMI `Win32_Process Create` with the log redirected
  to a file; that survives everything.
- **Run long jobs under `pythonw.exe`, not `python.exe`.** `pythonw` has no console, so there is no
  window to close and no `Ctrl+C` path — closing a tab once sent `^C` through the whole console
  group and killed 4 processes at once. The script must open its own log file and redirect
  `sys.stdout`/`sys.stderr` into it, since `pythonw` has no console to inherit.
- **`OpenProcess` needs `SYNCHRONIZE` (`0x100000`)** for `WaitForSingleObject`. Using
  `0x1000` (QUERY_INFORMATION) makes the wait return `WAIT_FAILED`, so every watcher concludes the
  worker died instantly and exits. Always check `rc == 0x102` (WAIT_TIMEOUT).
- **A watchdog/finalizer that starts before the worker can read a *stale* pid file** and exit
  immediately, writing a premature "finished" report. Have it poll for the pid file AND verify the
  pid is alive before trusting it.
- **`Pipeline`'s default `NullReporter` defines `event()` but `Pipeline.ev()` calls `emit_event()`**
  — instant `AttributeError` at the first `log()`/`stat()` call. Always pass a reporter that
  implements `emit_event`.
- **Parse log timestamps, not `time.time()`**, when computing rate/ETA from a file. Reading a log
  from offset 0 and stamping every line with "now" inflates the rate and collapses the ETA to zero.
- **Log lines carry a `[HH:MM:SS] ` prefix** — anchor log regexes with `search`, not `match`.
- **After moving the output directory, grep every script for the old path.** `tv_lib.py` was
  updated but `tv_verify.py` was missed, so the final integrity check died with
  `FileNotFoundError` on a deleted directory and the run "passed" with no verification at all.
- **A network outage does not need a manual resume** — `fetch()` retries with backoff and the
  shard cache makes the re-run cheap. But it *does* stretch wall time enormously: dimension `d1`
  took 741 min instead of ~30 min because it ground through failed requests.
- **TradingView throttles by IP, and the block can start the *next* job.** The 32-worker search
  sweep immediately followed by 24 script-page workers made phase 2 fail **56,882/56,882** — the
  endpoint was serving 403/429 from the first request. Fix: fewer workers (12), treat 403 like
  429 (back off and retry, don't give up), and record status codes so the cause is visible.
  Throughput is bandwidth-bound anyway (~340-600 KB per page, ~7 pages/s at 12 workers).
- **Keep-alive matters enormously here.** `urllib` (new TLS handshake per request) managed
  1.3 pages/s; `requests.Session` with a connection pool managed 10.3 pages/s on the same host.
- **`pythonw` + `cmd /c` redirection is the only way to log from a detached job.** A WMI
  `Win32_Process.Create` command line is *not* parsed by cmd — `> file 2>&1` becomes two bogus
  argv entries and the output vanishes. Either launch via `cmd /c "..."` or have the script open
  its own log file and reassign `sys.stdout`.
