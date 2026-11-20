# TradingView Pine Harvester

A portable Python toolkit that downloads TradingView's **open-source Pine Scripts** and
stores each as a folder with its source (`.pine`), full description (`.md`) and
machine-readable metadata (`meta.json`). Everything is driven from the command line —
no UI, no GUI, no build step.

**Reference corpus used during development:** 99,335 scripts enumerated · 62,478 with
source · 36,857 protected (manifest only) · 638 MB of Pine code. These numbers describe
the corpus the tool was built against — they are **not** a target your own run must
match. Your counts depend on what you choose to download.

This single document is both the **user guide** (below) and the **developer reference**
(second half). There is no separate `DEV.md` — architectural details, module map, feed
mechanics, traps and extension recipes all live in the Developer Reference section near
the end. Nothing in this repository is tied to one machine: all paths are relative to the
repository or configured by you, and no personal paths or credentials are included.

## Features

- Five enumeration routes: HTML listings, JSON API, paginated keyword search, path
  listings and title resolution — all cached and resumable.
- Full descriptions from each script's own page (74% exceed TradingView's 500-char
  listing limit).
- One folder per script: `<Name> [TVid].pine`, `<Name> [TVid].md`, `meta.json`.
- SQLite FTS5 index over every name, author and description.
- Enrichment: facade metadata, versions, preview images, comments, localized
  descriptions, import graphs, input parameters and SHA-256 hashes.
- Configuration via one JSON file or an environment variable; no absolute paths in code.

## Quick start

1. Install Python 3.12 and the single third-party dependency:

   ```powershell
   pip install -r requirements.txt
   ```

2. Copy/clone the repository anywhere, then change into `code files/tools` and check
   the setup:

   ```powershell
   cd "code files/tools"
   python tv.py status
   python tv.py verify
   ```

3. Tell the tool where your corpus should live (see
   [Configure the data folder](#configure-the-data-folder)), then start a scrape.

All commands are run manually with Python. There is no dashboard, launcher, or
executable. Python bytecode caches are disabled in this repository (`-B` in the launch
commands and `sys.dont_write_bytecode` at startup), so no `__pycache__` folders or `.pyc`
files are created while running it. A full scrape from scratch is:

```powershell
python -u ..\harvest\tv_pipeline.py
```

On Linux/macOS use forward slashes (`../harvest/tv_pipeline.py`) and `python3` if that
is how your interpreter is named. The Windows-only pieces are the `.ps1` helpers and
detached `pythonw` jobs; every collector itself is plain Python and runs in the
foreground on any OS.

## CLI reference

| Command | What it does |
|---|---|
| `python tv.py status` | data folder, script-folder and file counts, index size |
| `python tv.py configure <folder>` | choose where the indicators are stored |
| `python tv.py verify` | integrity check — counts, empty files, Pine signature sample |
| `python tv.py manifest` | rebuild `_manifest.csv` / `.jsonl` / stats from cache |
| `python tv.py analyze` | hashes, tags, imports, inputs, `meta.json` per script |
| `python tv.py index` | build `library.sqlite` (FTS5) |
| `python tv.py index <query>` | search names, authors and full descriptions |
| `python tv.py expand type` | crawl `type=1` / `type=2` search dimensions |
| `python tv.py expand all` | type + description seeds + authors + sliced queries |
| `python tv.py enrich meta` | fetch facade metadata for every open script |
| `python tv.py delta` | merge all caches, download new scripts, rebuild indexes |
| `python tv.py desc 2` | fetch full descriptions (phase 2) |
| `python tv.py refresh` | rewrite `.md` files from scraped descriptions |
| `python tv.py export <name>` | ZIP one script, or `--prefix X` / `--all` |
| `python tv.py snapshot` | commit catalog state to git |
| `python tv.py pause` / `resume` | suspend / resume detached workers |

## Configure the data folder

The shipped default is `code files/core/config.json`:

```json
{ "output_dir": "..\\..\\indicators" }
```

`..\\..\\indicators` means "an `indicators` folder at the repository root" — a neutral
default that works on any checkout. The path is resolved relative to the config file, so
you can change it to anywhere you like; absolute paths work too. The `TV_DATA_DIR`
environment variable overrides both and has the highest precedence. The easiest option
is to let the tool write the config for you:

```powershell
python tv.py configure "<folder where your indicators should live>"
```

Use a path that exists (or that you want created) on **your** machine — for example
`$HOME/indicators` on Linux/macOS or `D:\data\indicators` on Windows. Then run
`python tv.py status` and confirm the printed data folder is the one you intended.

## Running long collectors

On Windows, long jobs can be launched detached with `pythonw.exe` so they survive the
shell that started them and open no console windows. Resolve both paths from your own
environment instead of hardcoding them:

```powershell
$repo = (Get-Location).Path                      # run this from the repository root
$pyw  = (Get-Command pythonw).Source              # or (Get-Command python).Source
$script = Join-Path $repo "code files\harvest\tv_expand.py"
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = "`"$pyw`" -B -u `"$script`" type"
}
```

If `pythonw` is not on your PATH, point `(Get-Command pythonw)` at your interpreter's
`pythonw.exe` — the name and location differ between installations. Progress goes to
`code files\logs\*.log`. Pause/resume with `python tv.py pause` / `resume` (uses Win32
`NtSuspendProcess` / `NtResumeProcess`). On other operating systems, simply run the
collector in a terminal you keep open (or under your own process manager such as
`nohup`/`systemd`), since the `.ps1` helpers are Windows-specific.

## Status, progress and logs

There is no GUI or dashboard. Everything is reported as plain text on stdout, or, for
detached jobs, into a log file.

**`python tv.py status`** prints a point-in-time snapshot:

- the **data folder** path currently in use (the resolved `OUT`);
- the number of **script folders** (top-level directories in the data folder, excluding
  `_work`);
- the number of **`.pine` files**, counted by walking the folder tree (also excluding
  `_work`);
- the size in MB of `catalog.md`, `_manifest.csv` and `library.sqlite`, or `-` if a file
  is missing.

If the data folder does not exist, it prints a hint to run `configure` or a full scrape.
Two important details: the counts come from **walking the data folder, not from the
manifest**, and the path printed is the authoritative one. A wrong `config.json` is the
usual reason a "successful" `status` or `verify` reports zero files — always check that
path first.

**Foreground commands** print timestamped lines of the form `[HH:MM:SS] message` with
`flush=True`, so text appears immediately rather than being buffered until exit.

**Long collectors** (`expand`, `enrich`, `desc`, `delta`, `tv_pipeline`) additionally
print periodic progress at fixed intervals (for example every 50 downloads, every 100
search terms or script pages, every 200/500 enrichment records). Each line carries the
item index and total (`i/N`), result counters (`ok`, `empty`, `fail`) where relevant, the
current rate (items or pages per second), an ETA in minutes, and a projected finish
**clock time** (`ends=HH:MM`). The ETA is computed from elapsed timestamps, so time spent
paused does not distort it. Sibling machine-readable lines such as
`PROG expand|<done>|<total>|<mode>` and `PROG task|<name>|<done>|<total>|<eta>` exist for
log parsers and watchers.

**The full pipeline** (`tv_pipeline.py`) is more structured: it emits events through a
reporter's `emit_event()` method — `plan` (the phase list), `phase` (start/done for
ENUMERATE → KEYWORDS → DOWNLOAD → VERIFY → DONE), `task` (done/total/rate/eta/end time and
counters), `stat`, `log`, and a final `final` summary with the script count and elapsed
time. A reporter passed into `Pipeline()` **must** implement `emit_event()`; the built-in
`NullReporter` only has `event()` and silently discards everything.

**Detached jobs** have no console (`pythonw.exe`), so each script opens its own log file
under `code files\logs\` (for example `expand.log`) and reassigns `sys.stdout` /
`sys.stderr` to it. Live progress is read by tailing that log. `tv.py pause` / `resume`
suspend and resume the worker processes without dropping sockets or in-flight state, and
`tv_watchdog.py` polls worker liveness and writes a completion summary containing the
last 60 log lines.

**HTTP health** is tracked by `StatusTracker` in `tv_rate.py`: it counts response status
codes, exposes `bad_fraction()` (the share of non-2xx responses) and `report()`, and the
collectors use a 403/429 spike to trigger adaptive backoff via `RateLimiter.slow()`.

## Typical workflows

From a fresh clone, with all commands run from `code files\tools`:

1. **Configure once.** `python tv.py configure <folder>` (or set `TV_DATA_DIR`, or edit
   `core\config.json`). Confirm with `python tv.py status` that the printed data folder is
   the one you intend.
2. **Full scrape from scratch.** `python -u ..\harvest\tv_pipeline.py` enumerates all
   feeds, downloads source, writes the catalog and verifies. For an unattended run,
   launch it detached with the WMI/`pythonw` command shown above and tail
   `code files\logs\`. A finalizer then chains manifest → index → verify.
3. **Incremental update.** `python tv.py delta` re-merges cached shards, downloads only
   new scripts and rebuilds the indexes.
4. **Widen coverage.** `python tv.py expand all` sweeps additional search dimensions into
   cached shards, then run `delta` to pull in anything new.
5. **Full descriptions.** `python tv.py desc 2` fetches the untruncated descriptions,
   then `python tv.py refresh` rewrites each script's `.md`.
6. **Enrich and analyse.** `python tv.py enrich meta` (also `versions`, `images`,
   `comments`, `lang`), `python tv.py analyze` for local hashes/tags/imports/inputs, then
   `python tv.py index` to build the searchable SQLite FTS5 index.
7. **Search.** `python tv.py index "<query>"` searches names, authors and full
   descriptions.
8. **QA before calling a change done.** `python tv.py status`, `python tv.py verify`,
   `python tv.py index "fibonacci"` — all must succeed, the counts must match what
   **your** corpus should contain at that point, and the data-folder path printed by
   `status` must be the one you configured.
9. **Package or archive.** `python tv.py export <name|--prefix P|--all>` writes ZIPs;
   `python tv.py snapshot` commits the catalog state to git.

## Project layout

```
indicator downlaoder/
├── README.md                  this file (user guide + developer reference)
└── code files/
    ├── bootstrap.py           makes every subfolder importable
    ├── core/                  tv_config.py, config.json, tv_lib.py, tv_rate.py
    ├── harvest/               tv_pipeline, tv_manifest, tv_desc_scrape,
    │                          tv_desc_phase3, tv_finalize2, tv_expand,
    │                          tv_delta, tv_enrich
    ├── organize/              tv_restructure, tv_md_refresh, tv_analyze,
    │                          tv_index, tv_export, tv_verify,
    │                          tv_verify_desc, tv_snapshot
    ├── tools/                 tv.py (CLI), tv_watchdog.py, tv_pause.ps1
    └── logs/                  collector logs
```

## Data layout

```
<your data folder>/            (default: indicators/ at the repository root)
├── <Name> [TVid]/
│   ├── <Name> [TVid].pine     Pine source
│   ├── <Name> [TVid].md       metadata + full description
│   └── meta.json              author, type, tags, hash, inputs, description
├── catalog.md                 every script, author, version, link
├── _manifest.csv / .jsonl     every script you have enumerated
├── library.sqlite             FTS5 search index
├── _work/                     resumable scrape cache (safe to delete, costly to rebuild)
└── README.md
```

Protected scripts (access `2` / `3`) have no source and therefore no folder — they
appear in the catalog and manifest only. TradingView ships them as encrypted bytecode;
the plaintext never reaches the client.

## Requirements

- Python 3.12 (tested). Install the single dependency with
  `pip install -r requirements.txt` (`requests`, used by the description scraper).
- Windows for the `.ps1` process helpers and detached `pythonw` jobs. Every Python
  module itself is platform-independent and uses only relative paths, so collectors can
  be run in the foreground on Linux/macOS too.
- No account, API key, or personal configuration is required to fetch open-source
  scripts.

## Note

Bulk scraping of TradingView is against their terms of use. The defaults are deliberately
polite (6 download workers with 150 ms spacing, adaptive backoff on 403/429). Use
responsibly.

---

# Developer Reference

Read this before modifying anything. It describes the code that exists now. The sections
below go deeper than the user guide above: exact paths, URL shapes, field semantics,
traps, and extension recipes.

## D1. Layout

```
indicator downlaoder/
├── README.md, requirements.txt, .gitignore
└── code files/
    ├── bootstrap.py               puts every subfolder on sys.path
    ├── core/        tv_config.py, config.json, tv_lib.py, tv_rate.py
    ├── harvest/     tv_pipeline, tv_manifest, tv_desc_scrape,
    │                tv_desc_phase3, tv_finalize2, tv_expand, tv_delta, tv_enrich
    ├── organize/    tv_restructure, tv_md_refresh, tv_analyze, tv_index,
    │                tv_export, tv_verify, tv_verify_desc, tv_snapshot
    ├── tools/       tv.py (CLI), tv_watchdog.py, tv_pause.ps1
    └── logs/        collector logs
<your data folder>/                 the DATA (default: indicators/ at the repo root)
```

The tool never writes into the data folder except through explicit commands, and the
data folder contains no code. The two trees are deliberately separate: `code files/`
holds all logic and configuration, your data folder holds only generated data. That is
why the whole tool can be copied anywhere and repointed at a different corpus simply by
changing `config.json` or setting `TV_DATA_DIR`.

**Imports.** Each script begins with three lines that put the `code files` root on
`sys.path` and import `bootstrap`, which then adds every subfolder (`core`, `harvest`,
`organize`, `tools`) to `sys.path`. That is why `from tv_config import OUT` works
uniformly from `harvest\`, `organize\` and `tools\` without any package-relative
imports. A new subfolder is picked up automatically — no edits to `bootstrap.py` are
needed for it. If a moved script raises `ModuleNotFoundError`, the first thing to check
is that its three-line header still imports `bootstrap`.

## D2. Path resolution (`core/tv_config.py`)

```
env TV_DATA_DIR → config.json["output_dir"] → sibling folder "indicators"
```

Resolution order is strictly top-down: the `TV_DATA_DIR` environment variable wins, then
the `output_dir` value in `config.json`, then a fallback folder named `indicators`
beside `code files`. When `output_dir` comes from `config.json`, it is resolved
**relative to the config file's own folder**, not the current working directory. The
shipped default `"..\\..\\indicators"` in `code files\core\config.json` walks up two
levels to the repository root and into `indicators`. An absolute path is also accepted.

`OUT` is the single source of truth for every data path. Everything else is derived
from it, so changing one value redirects the entire tool:

- `WORK = OUT/_work` — resumable scrape cache
- `PAGES = WORK/pages` — cached listing/API/search pages
- `KEYS = WORK/keywords` — cached keyword-search shards
- `LOGS = <code files>/logs` — collector logs (these live beside the code, not the data)

`set_data_dir(path)` writes the new value back into `config.json`; this is what
`python tv.py configure <folder>` calls. **Never hardcode a data path in a module** —
always derive it from `OUT`. A hardcoded path was the cause of a past incident where
`tv_verify.py` kept pointing at a deleted directory and "passed" while verifying zero
files.

## D3. Data model

`pub_id` is the primary key everywhere — manifest rows, `_downloaded.jsonl`, the
description and enrichment JSONLs, and database rows. It is usually `PUB;<32 hex>` but
is sometimes short, so never assume a fixed length or format. Treat it as an opaque
string.

`tv_id` is the 8-character TradingView short id used in `/script/<tv_id>/` URLs. It is
read from `image_url` on HTML listing rows or `imageUrl` on search rows. Note carefully:
`pub_id[4:12]` is a **local filename convention only** — it is not a real `tv_id` and
does not resolve as a URL. Scripts without a genuine `tv_id` get the `pub_id[4:12]`
fallback in their filename, but that string cannot be used to fetch the script page.

Access levels determine what can be recovered:

| Level | Meaning | Result |
|---|---|---|
| `1` | open source | `.pine` source obtainable via the facade endpoint |
| `2` | protected bytecode | source is encrypted; only a manifest row |
| `3` | invite-only | source is encrypted; only a manifest row |

Only level `1` scripts get a `.pine` file; **all** levels get a manifest row. Levels
`2`/`3` are shipped to the client as encrypted bytecode, so the plaintext source never
reaches the client and cannot be recovered by this tool.

**JSONL convention.** One JSON object per line, UTF-8, no BOM. The helper
`write_jsonl()` writes to a `.tmp` file first and then `os.replace()`s it into place,
which makes a write atomic — a crash mid-write cannot leave a half-written file. Readers
skip malformed lines rather than dying. Every collector **appends** to its JSONL and
skips ids already present; this append-and-skip behaviour is the resume mechanism for
long jobs. A collector can be killed and restarted without redoing completed work.

## D4. Module map

| File | Responsibility | Edit it when |
|---|---|---|
| `tv_config.py` | path resolution | changing how locations are configured |
| `tv_lib.py` | `fetch()`, `extract_scripts()`, `norm()`, `norm_suggest()`, JSONL helpers | adding an endpoint or changing normalization |
| `tv_rate.py` | rate limiter + status telemetry | changing throttling |
| `tv_pipeline.py` | full enumeration + source download engine | adding a feed, changing download logic |
| `tv_manifest.py` | rebuild `_manifest.*` from all shards | changing manifest fields |
| `tv_verify.py` | integrity check (walks folders) | adding an integrity rule |
| `tv_verify_desc.py` | layout + description-length check | changing QA thresholds |
| `tv_restructure.py` | flat → per-script folders, writes `.md` | changing folder/file naming |
| `tv_md_refresh.py` | rewrite `.md` with scraped descriptions | changing `.md` content |
| `tv_desc_scrape.py` | descriptions: short-id recovery + page scrape | changing description extraction |
| `tv_desc_phase3.py` | title+author matching for missing short ids | changing the match heuristic |
| `tv_finalize2.py` | chain scrapers → refresh → manifest → verify | changing end-of-run sequence |
| `tv_expand.py` | search-dimension expansion | adding a dimension |
| `tv_delta.py` | re-merge shards, download new, rebuild indexes | changing incremental runs |
| `tv_enrich.py` | facade metadata, versions, images, comments, translations | adding metadata |
| `tv_analyze.py` | imports, inputs, hashes, tags, `meta.json` | adding local analysis |
| `tv_index.py` | SQLite FTS5 build + query | changing the index |
| `tv_export.py` | ZIP export | changing export format |
| `tv_snapshot.py` | git commit of catalog state | changing snapshot contents |
| `tv.py` | CLI dispatcher | adding a command |
| `tv_watchdog.py` | waits for worker exit | changing watchdog behaviour |
| `tv_pause.ps1` | suspend/resume detached workers | changing process control |

A few relationships worth noting:

- `tv_lib.py` is the shared HTTP/parsing toolbox. `fetch()` is the common request
  function; `extract_scripts()` and `norm()` / `norm_suggest()` normalize the two
  different row shapes returned by listings and search. Adding a new endpoint usually
  means a new helper here plus a feed in `tv_pipeline` or a mode in `tv_expand`.
- `tv_pipeline.py` is the main engine: it enumerates all routes, caches pages, and runs
  the source downloader (`_download()`). It is launched directly for a full scrape.
- `tv_finalize2.py` is the end-of-run orchestrator — it chains the description scrapers,
  runs the `.md` refresh, rebuilds the manifest, and verifies. Changing the order of
  those steps happens here.
- `tv_delta.py` is the incremental counterpart to a full scrape: re-merge shards,
  download only new scripts, rebuild the indexes.
- `tv_verify.py` and `tv_verify_desc.py` are the QA gates — the former checks integrity
  by walking folders, the latter checks layout and description lengths against
  thresholds.

## D5. Feed mechanics

Four enumeration routes exist, all cached under `_work/pages/` or `_work/keywords/`.
Caching means re-runs do not refetch already-seen pages, which is both polite and fast.

1. **HTML listing** —
   `/scripts/page-N/?script_type={indicators|strategies|libraries|all}&sort={recent|recent_extended|latest_popular}`,
   24 scripts per page. `extract_scripts()` finds the server-side-rendered JSON array by
   scanning **backwards** from the first occurrence of `"script_id_part"` and trying
   `JSONDecoder.raw_decode()` on each `[` it encounters, keeping the largest valid array
   it finds. This backwards scan is needed because the page contains many unrelated JSON
   blobs and inline data.
2. **JSON API** —
   `/api/v1/scripts/?page=N&script_type=X&sort=Y`, 20 per page, with a hard cap of 50
   pages. The `count` field reports the true feed depth even when the server stops
   serving further pages, so it is the authority on how much data exists.
3. **Search suggest** —
   `/pubscripts-suggest-json/?search=<term>&offset=<0..950>`, 50 per page, capped at
   1,000 results per term. The `&type=1|2` and `&sort=recent` parameters produce
   **near-disjoint** dimensions — different slices of results — so sweeping all of them
   yields more coverage. The parameters `page`, `limit`, `count` and `start` are ignored
   by this endpoint; only `offset` controls pagination.
4. **Path route** — `/scripts/<type>/page-N/`; it ignores `sort`, exposes a 48-page
   window, and yields comparatively little. It is the weakest route but is kept for
   completeness.

**Wrap detection.** Each page's id-set is compared to page 1's id-set; a repeat means
the feed has started looping and enumeration should stop. Never compare a page to
itself — that would always look like a wrap.

**Critical — the search endpoint paginates.** Earlier sweeps read only `offset=0`, i.e.
50 of the 1,000 available results per term. Adding deep offsets (up to 950) grew the
corpus from 71,954 to 99,335 scripts. Whenever a new route or search mode is added, the
first thing to check is which pagination parameters it honours and what its true cap is.

## D6. Source download

Source is fetched from a single endpoint:

```
GET https://pine-facade.tradingview.com/pine-facade/get/{quote(pub_id)}/last
```

No login or cookies are required. For `access=1` the endpoint returns HTTP 200 with a
JSON body containing `.source`. For `access=2`/`3` it returns 401 — those scripts are
encrypted bytecode and the plaintext never reaches the client, so they are
unrecoverable through this path.

`_download()` builds `todo = open_rows + unknown`: all known open-source rows plus rows
whose access level is not yet known. For each id it:

1. skips the id if it is already in `_downloaded.jsonl` **or** the `.pine` file already
   exists (this is the resume/deduplicate check);
2. otherwise fetches the source, sanitizes the filename, writes the `.pine` file, and
   appends the id to `_downloaded.jsonl`.

Defaults are **6 workers** with a **150 ms** delay between requests; both can be changed
by passing different values to `Pipeline()`.

**Filename format:** `<sanitized name> [<tv_id>].pine`. When a script has no real
`tv_id`, the local `pub_id[4:12]` convention is used in the brackets instead. That
fallback string is only a filename label — as noted in D3, it is not a usable URL id.

## D7. Descriptions

Descriptions are **server-truncated to 500 characters** in the HTML listings, the JSON
API, and search results. The full text — up to roughly 70 KB — exists only on the
script's own page, in the server-side-rendered JSON `"description"` field. That is why
the `.md` files hold far more than the listing snippets, and why 74% of descriptions
exceed the 500-char limit.

Two traps make naive extraction wrong:

1. The page contains a `<div class="description-XXXX">` element where `XXXX` is a hashed
   CSS-module class. Its content is a **relative timestamp** like "2 days ago", not the
   description. Never select that element.
2. The page stores descriptions in **BBCode** (`[b]`, `[url=…]`, etc.), while the listing
   serves the same text with the BBCode stripped. A raw prefix comparison between page
   text and listing text therefore fails even on correct data — strip BBCode from the
   page version before comparing.

`extract_description()` handles this by collecting **all** JSON `"description"` matches
on the page, choosing the one whose first ~40 normalized characters match the meta
description, and falling back to the longest match if none lines up.

`tv_desc_phase3.py` recovers missing short ids by searching for the exact script title
and matching on title + author. Phase 2 uses a `requests.Session` with a connection
pool, achieving roughly 17 pages/second versus about 1.3 with plain `urllib`.

**Back off on 403/429.** These status codes mean the IP is being throttled and must be
treated as a stop signal, not retried aggressively. A 32-worker sweep once triggered a
block that caused the *next* job to fail 56,882 out of 56,882 requests. The polite
defaults (6 workers, 150 ms spacing, adaptive backoff) exist to prevent this.

## D8. Collectors

- **`tv_expand.py`** — modes: `type`, `seeds`, `author`, `slice`, `all`. Capped at 25,000
  terms via the `TV_EXPAND_LIMIT` environment variable. Shards are named
  `KEYS/x<mode>__<safe>__<hash>__o<NNNN>.jsonl`. To add a mode, add a case to `sweep()`
  with a new tag and an `extra_for()` suffix; shards are then autogenerated.
- **`tv_enrich.py`** — modes: `meta`, `versions`, `images`, `comments`, `lang`. Writes
  `_work/enrich/<mode>.jsonl` keyed by `pub_id`, resumably — adding ids never disturbs
  existing ones.
- **`tv_analyze.py`** — fully local, no network. Extracts imports, `input()` labels,
  SHA-256 hashes, and heuristic tags, and writes a `meta.json` into each script folder.
  It is idempotent: re-running it produces the same result.
- **`tv_index.py`** — builds `library.sqlite` with a `scripts` table and a SQLite FTS5
  virtual table over name, author and description. `python tv.py index <query>` searches
  that index.

## D9. Running long jobs manually

Never launch a long job from a shell that will exit — the child dies silently with it.
On Windows, launch it detached with WMI so it survives; derive the interpreter and
script paths from your own environment:

```powershell
$repo = (Get-Location).Path
$pyw  = (Get-Command pythonw).Source
$script = Join-Path $repo "code files\harvest\tv_expand.py"
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = "`"$pyw`" -B -u `"$script`" type"
}
```

On Linux/macOS there is no `pythonw`; run the collector under your own process manager
(`nohup`, `tmux`, `systemd`, …) and tail its log instead.

`pythonw` has no console, so the script must open its own log file and reassign
`sys.stdout` / `sys.stderr` itself. A `> file 2>&1` redirection inside a WMI command line
is **not** parsed by `cmd.exe` and becomes bogus argv entries instead. Logs land in
`code files\logs\`.

`python tv.py pause` / `resume` suspend every `pythonw` process through Win32
`NtSuspendProcess` / `NtResumeProcess`, preserving sockets and in-flight state — useful
when a job needs to be held without losing work. `tv_watchdog.py` polls for worker exit
using `CreateToolhelp32Snapshot`, then runs a finalizer that chains manifest → index →
verify.

## D10. Known landmines

These are real bugs encountered during development. Each one has caused a failure or a
silent wrong result before; respect them when changing the corresponding code.

- **`NullReporter.event()` vs `Pipeline.ev()` calling `emit_event()`** — a reporter
  passed into the pipeline must implement `emit_event()`. A null reporter that only has
  `event()` will break telemetry. Always pass an object with `emit_event()`.
- **`OpenProcess` access mask** — `WaitForSingleObject` needs the `SYNCHRONIZE` right
  (`0x100000`). Using only `0x1000` returns `WAIT_FAILED`, which makes watchers believe
  a live worker has died. Combine them (`0x101000`) when opening the worker process.
- **Stale pid file** — a watchdog that starts before the worker writes its pid file
  reads a stale pid and quits immediately. The watchdog must verify **liveness** (that
  the pid actually refers to a running worker), not merely that the file exists.
- **`RateLimiter.wait()` lock** — the limiter must release its lock before sleeping,
  otherwise every worker serializes behind the sleeper and parallelism collapses.
- **Flat → folder restructure broke `os.listdir(OUT)`** — after scripts were reorganized
  into per-script folders, any code using `os.listdir(OUT)` to find `.pine` files
  silently saw zero files. Use `os.walk()` to descend into folders (see `tv_verify.py`).
- **Moving the tool folder** — requires updating `config.json`. `tv_verify.py` once kept
  pointing at a deleted directory and "passed" while verifying nothing.
- **ETA from timestamps, not `time.time()`** — suspended periods (`pause`/`resume`)
  inflate a wall-clock `time.time()` estimate. Estimate ETA from the log timestamps
  instead.
- **Batch file line endings** — `.bat`/`.cmd` files written by tools are often LF-only;
  `cmd.exe` needs CRLF or the lines get concatenated and the script misbehaves. Always
  save `.bat`/`.cmd` with CRLF.

## D11. Recipes

**Add a search dimension.** In `tv_expand.py`: add a case to `extra_for(mode)`, add a mode
function that calls `sweep("newtag", terms)`, and dispatch it in `main()`. Shards are
autogenerated from the tag — no manual shard files needed. Check the endpoint's
pagination parameters (D5) before writing the sweep.

**Add an enrichment field.** In `tv_enrich.py`: write a `by_<name>(row) -> dict` function,
then add the new mode to `main()`. `collect()` automatically adds `pub_id` to each
record. Re-run the collector; existing ids are skipped, so only new data is fetched.

**Add a local analyzer.** In `tv_analyze.py`: add the extraction logic inside `analyze()`
and a `write_jsonl()` output for the new data. If the field belongs in `meta.json`, also
add a key in `meta_json()`. The step is idempotent and offline.

**Add a CLI command.** Add the script path to the `MAP` dictionary in `tv.py` and a
corresponding line in `HELP`.

**Change the data folder.** Edit `core/config.json`, run
`python tv.py configure <folder>`, or set `TV_DATA_DIR`. Nothing else in the codebase
needs to change because every path derives from `OUT`.

## D12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "0 pine files" in verify | script lists the flat root; use `os.walk()` to descend into folders |
| Collector fails 100% of requests | IP throttle from a prior sweep; wait, reduce workers, back off on 403/429 |
| Watcher says worker finished instantly | stale pid file or wrong `OpenProcess` mask (use `0x101000`) |
| Manifest/catalog disagree | manifest rebuild ran before the final merge; run `python tv.py manifest` |
| `ModuleNotFoundError` after moving files | `bootstrap` not on path; check the three-line header of the script |
| Batch file does nothing | LF line endings; convert to CRLF |

## D13. Verification gate

Before reporting a change as done, run all three checks:

```powershell
cd "code files/tools"
python tv.py status
python tv.py verify
python tv.py index "fibonacci"
```

All must succeed, the reported counts must match what **your** corpus should contain,
and the data-folder path printed by `status` must be correct. A wrong config is the most
common reason a "successful" run actually verified zero files. The development corpus
(62,478 source files / 99,335 manifest rows) is a useful sanity reference, not a required
result.

