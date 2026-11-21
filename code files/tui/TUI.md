# Pine Harvester TUI — Developer Guide

This is the code-level guide to the live terminal dashboard. For the short user guide
and key table, see the repository `README.md`; this document explains how the TUI is
put together so you can change it safely.

## 1. Where it lives and how it boots

```
<repo>/
├── Pine Harvester TUI.bat        launcher (finds a Python with Textual)
└── code files/
    └── tui/                      everything in this document
```

`paths.py` is the first module imported, and it does all bootstrap work:

- `HERE` = `code files/tui`
- `CODE` = `code files` (the CLI code tree)
- `ROOT` = repository root
- inserts `CODE` on `sys.path`, imports `bootstrap` (which adds `core`, `harvest`,
  `organize`, `tools`), then imports `tv_config` for `OUT` and `LOGS`.
- `JOB_PY` comes from `job.find_job_python()`: `TV_PYTHON` first, then a `python` on
  PATH that can `import requests`, then `sys.executable`.

Never hardcode a data path anywhere else. Every path in the TUI derives from `OUT` or
`LOGS`, so `tv.py configure` and `TV_DATA_DIR` keep the TUI and the CLI in agreement.

The entry point is `harvester_tui.py`. It sets `sys.dont_write_bytecode = True` before
importing anything, so running the TUI never creates `__pycache__`.

## 2. File map

| File | Responsibility |
|---|---|
| `harvester_tui.py` | `HarvesterTUI(App)`: state, layout, job lifecycle, actions, status scan, log pipeline |
| `screens.py` | all modal screens: search, help, palette, details, history, configure, maintenance, danger, quit |
| `widgets.py` | `KpiCard` (value + delta rendering and flash) and count/MB formatters |
| `motion.py` | tween engine (`Motion`, `Tween`, easings) for entrances, count-ups, progress smoothing, modal fades |
| `theme.py` | `PALETTE` tokens and the full Textual CSS string |
| `job.py` | `Job` dataclass, `find_job_python()`, `parse_progress()`, `classify()` |
| `paths.py` | bootstrap described above |
| `sync.py` | driver behind the `s` action (merge, download new, folder-safe catalog, manifest/index/analyze) |
| `clear.py` | standalone guarded deletion engine used by Maintenance |
| `smoke_test.py` | headless render + interaction proof |
| `TUI.md` | this document |

## 3. Runtime architecture

There is one app object and one source of truth. Widgets never own data; they are
re-rendered from `HarvesterTUI` fields after a mutation.

Key state on `HarvesterTUI`:

| Field | Meaning |
|---|---|
| `job` | current `Job` or `None` |
| `queue` | list of `(label, argv)` waiting to run (max 8) |
| `_history` | `deque(maxlen=6)` of finished/stopped runs |
| `_stats`, `_prev` | latest and previous status snapshot (deltas) |
| `_log_buffer` | `deque(maxlen=2000)` raw log lines for filtering |
| `_log_filter`, `_log_name` | active filter and source log name |
| `_rates` | recent rate samples for the sparkline |
| `_growth` | downloaded counts over the last 40 scans |
| `_session_jobs`, `_last_*` | session counters and last result |
| `_log_counts` | live error/warning counts |
| `_disk_free_gb`, `_started_at`, `_maint_summary` | telemetry and maintenance snapshot |
| `_wide_toolbar`, `_wide_sidebar` | responsive flags |
| `motion` | `Motion` instance (disabled by calm mode) |

Rendering is split into small methods, all pure reads of state: `_render_badge`,
`_render_progress`, `_render_sidebar`, `_render_status`, `_render_log`,
`_render_toolbar`, and the card updates through `_update_card`. Mutate state first,
then call the relevant renderers.

`on_mount` sets border titles, applies responsiveness, renders everything once, seeds
the log, starts the 0.5 s ticker, runs the entrance animation and schedules the first
scan.

Timers:

- `set_interval(0.5, _tick)`: updates elapsed time while a job runs, flushes dirty
  status/sidebar counters, and triggers an adaptive status scan.
- `Motion` starts a 30 fps timer only while tweens exist and stops it at zero, so idle
  cost is zero.
- The running spinner belongs to Textual's `LoadingIndicator`.

## 4. Job engine

Everything that runs a collector goes through `_start` and `_launch`.

`_start(label, argv)`:

- If a job is already running, enqueue `(label, argv)` (max 8, duplicate labels
  rejected), flash the queue panel and re-render.
- Otherwise call `_launch`.

`_launch(label, argv)`:

- Builds `subprocess.Popen([JOB_PY, "-u", *argv], cwd=CODE, stdout=PIPE,
  stderr=STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
  env=...)`.
- Adds `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1` to the child env.
- Creates a `Job`, resets rate/progress state, writes the `── label ──` and
  `$ command` lines to the activity log, renders, and starts `_pump` in a daemon
  thread.

`_pump(job)` reads `stdout` line by line and marshals each line back with
`call_from_thread(_on_line, line, seq)`. When the process exits it calls
`_on_job_done(seq, returncode)`. Every callback checks the sequence number, so a
late line from a stopped job cannot corrupt a newer one.

`_on_line` appends the line to the log pipeline and calls `parse_progress`; if the
line carries progress it calls `_apply_progress`.

`job.parse_progress` understands:

- `PROG task|<name>|<done>|<total>|<eta_min>` — the pipeline/delta format.
- `PROG expand|<done>|<total>|<mode>` (also `sweep`, `enrich`).
- Fallbacks: the last `i/N` pair, `x/s`, `eta N min`, and
  `ok=N empty=N fail=N` counters.

`_apply_progress` updates `done`, `total`, `rate`, `eta_min` and `counters`. When a
total is known it tweens `job.display_done` toward the new value with `Motion`
(key `bar-<seq>`, 0.25 s) and `_set_bar` updates the `ProgressBar`; without a total
the bar stays indeterminate. Rates are appended to `_rates` (last 60) and pushed to
the sparkline.

`_on_job_done(seq, code)`:

- cancels the bar tween, captures label/duration, clears `job`, increments the
  session counter, records the run in `_history` and `_last_*`, sets `done`/`error`;
- renders, writes the finish line, flashes the log border, notifies and rescans;
- if the queue is not empty, pops the next item and `set_timer(0.35, _launch)`.

`_stop_job(silent=False)` terminates (then kills) the process, records the run with
`rc=-1`, and advances the queue. If there is no running job but a queue exists,
calling it starts the next item — that is the recovery path for a parked queue. The
`X` action clears the queue as well. `silent=True` is used on unmount.

`_quick(argv, message)` runs a short command (`tv.py pause`/`resume`) on a worker
thread and reports its last output line. Pause/resume target detached `pythonw`
collectors; they do not suspend the TUI's own child unless it is one of those.

## 5. Status scan

`_schedule_scan` guards against overlapping scans and starts `_scan` on a Textual
worker thread.

`_scan` reads ledgers instead of walking the corpus:

- folder count: `os.scandir(OUT)`, excluding `_work`;
- downloaded count and source bytes: `read_downloaded` over `_downloaded.jsonl`;
- manifest rows: `count_lines` over `_manifest.jsonl`;
- index footprint: `library.sqlite` plus `-wal` and `-shm`;
- free space: `shutil.disk_usage(OUT).free`;
- a `refresh` timestamp.

It always clears `_scanning` and marshals the snapshot with
`call_from_thread(_apply_stats, stats)`.

`_apply_stats` computes deltas against `_prev` and feeds `_update_card`, which sets
the new delta, tweens the card value (key `card-<id>`, 0.45 s) and flashes the card
when the value changed. It also appends the downloaded count to `_growth` (last 40)
and updates the growth sparkline, then re-renders the status bar and sidebar.

`_tick` schedules a scan every 4 s while a job runs and every 15 s when idle.
`TV_TUI_NO_SCAN=1` disables scanning entirely (used by tests).

## 6. Activity log

`_styled_line(line)` parses the optional `[HH:MM:SS]` prefix, classifies the rest via
`job.classify` (error/warning/success), dims timestamps and `PROG` records, and
returns a Rich `Text`.

`_log_line(line, count=True)`:

- appends to `_log_buffer` (2,000 lines);
- when `count` is true, increments the live error/warning counters;
- if a filter is active and the line does not match, stops there;
- otherwise writes the styled line to the `RichLog`.

`_render_log` clears the widget and re-writes every buffer line that matches the
current filter. `_update_log_subtitle` writes `log name` plus ` · filter: …` into the
panel border.

`_seed_log` finds the newest `*.log` under `LOGS`, shows its last 60 lines with
`count=False` (so old failures do not inflate session counters), resets the counters,
and exits cleanly when no log exists.

`/` opens the one-row filter bar, Enter applies, Esc clears. `Y` copies the last 50
buffered lines; `End` scrolls to the newest line.

## 7. Screens and modal contracts

All screens subclass `ModalScreen[T]` and return a value through `dismiss(value)`.
The app pushes them with `push_screen(screen, callback)`; the callback receives that
value on the main thread.

| Screen | Returns | Notes |
|---|---|---|
| `SearchScreen` | `None` | FTS query; runs `tv.py index <query>` on a worker; table with Name/Author/Path; Enter opens the script folder, `y` copies the path, `o` opens it |
| `HelpScreen` | `None` | grouped key reference in a `VerticalScroll`; border subtitle says how to scroll |
| `PaletteScreen` | `str` action id | filters on action id, label and description; `↑↓` move the `OptionList`, Enter returns; the app calls `_invoke` |
| `DetailsScreen` | `None` | `Table.grid` of path, counts, sizes, disk, uptime, worker state, queue and refresh; `y`/`o` |
| `HistoryScreen` | `None` | `DataTable` of the last six runs with result, duration and finish time |
| `ConfigureScreen` | `str` path | input prefilled with a placeholder of the current `OUT`; Enter returns, Esc returns `""` |
| `MaintenanceScreen` | `dict` | inventory + seven actions; measures `OUT/_work` in a worker; returns `{action, work_files, work_bytes}` |
| `DangerScreen` | `bool` | target list, typed confirmation, Delete button disabled until the word matches (case-insensitive), Esc cancels |
| `ConfirmQuit` | `bool` | shown only when a job or queue exists |

`fade_in(screen, widget_id, key)` sets a panel's opacity to 0 and tweens it to 1 with
`Motion`; calm mode applies the final value immediately. Use it in every modal's
`on_mount`.

`PaletteScreen` and `MaintenanceScreen` use `OptionList` (from `textual.widgets`;
`Option` lives in `textual.widgets.option_list`). `DataTable` columns must be added
before rows.

`MaintenanceScreen._measure_work` walks `_work` on a thread. It checks `_alive`
(set false in `on_unmount`) and marshals results with `call_from_thread`, so closing
the screen early is safe.

## 8. Motion

`motion.py` is deliberately small:

```python
motion.to(key, begin, end, duration, apply, delay=0.0, easing=ease_out_cubic)
motion.cancel(key, final=None)
motion.finish_all()
motion.set_enabled(False)
```

- Numeric only; `apply` receives the interpolated value.
- Tweens are keyed, so a new tween with the same key replaces the old one — motion
  is interruptible.
- A 30 fps timer is created on demand and stopped when no tweens remain.
- `ease_out_cubic` is the default; `ease_in_out_sine` is available.

Current uses: entrance opacities (`enter-<i>`), KPI count-ups (`card-<id>`), progress
smoothing (`bar-<seq>`), and modal fades (`modal-*`).

Reduced motion: `t`, `TV_TUI_CALM=1` or `NO_ANIMATIONS=1` create the app with motion
disabled and hide the spinner. `g` toggles ASCII glyphs. Neither mode hides
information: final states are rendered immediately.

## 9. Theme and responsive layout

`theme.py` owns `PALETTE` and one f-string `CSS`. Every widget references those tokens;
changing a token restyles the whole app.

Notable rules:

- `.card` uses border titles and centered content; `.card:hover` and `.card.flash`
  provide affordances.
- `#progress.running` switches the job panel border/background to the accent colour.
- `#logpanel.flash-success` / `.flash-error` are completion feedback.
- `#logfilter` is a one-row bar; `#logquery` is borderless.
- `#sidebar` is 40 columns; `.panel` carries the QUEUE/SESSION/DATA border titles.

Responsive behaviour lives in `_apply_responsive(width)`:

- toolbar (`#toolbar`) is shown at width ≥ 100;
- sidebar (`#sidebar`) is shown at width ≥ 120;
- the status bar switches to a compact form below 110;
- the job panel is 5 rows while running and 4 when idle.

Resize calls `_apply_responsive` and `_render_status`; no state is lost.

## 10. Data folder and reconfiguration

`OUT` and `LOGS` come from `tv_config` at import time. `Set data folder` opens
`ConfigureScreen`, then `_apply_configure` runs `tv.py configure <path>` on a worker.
On success `_reload_config`:

- `importlib.reload(tv_config)`;
- assigns the module-global `OUT` and updates `paths.OUT`;
- clears stats, previous stats and the growth list;
- rescans and re-renders.

Because `OUT` is imported by name, any new module that copies it at import time must
also be updated on reload. Prefer reading `paths.OUT` or passing `OUT` explicitly.

## 11. Cleanup engine

`clear.py` is a standalone script so it can be audited and dry-run outside the TUI.
Modes: `logs`, `cache`, `index`, `manifests`, `source`, `everything`.

Targets:

- `logs`: `code files/logs/*.log`;
- `cache`: `OUT/_work` (recursive);
- `index`: `library.sqlite`, `library.sqlite-wal`, `library.sqlite-shm`;
- `manifests`: `_manifest.csv`, `_manifest.jsonl`, `_manifest_stats.json`;
- `source`: all directories except `_work`, plus `_downloaded.jsonl` and `catalog.md`;
- `everything`: source + manifests + index + cache.

Safety in `safe_root`:

- resolves `realpath` so junctions/symlinks cannot disguise a target;
- refuses a drive root;
- refuses the user home or a folder containing it;
- refuses a folder that contains `code files` or the repository root;
- for `source`/`everything`, requires a harvester ledger marker (`_manifest*`,
  `_downloaded.jsonl`, `library.sqlite` or `catalog.md`) so an arbitrary folder
  cannot be wiped;
- real runs require `--yes`; `--dry-run` is read-only.

The TUI flow is: Maintenance inventory → `DangerScreen` with exact targets → typed
`CLEAR`/`DELETE` → `_start("Clear …", [clear.py, mode, "--yes"])`. Because cleanup is
a normal job, it streams into the log, shows progress, can be queued and can be
stopped. Cleanup is refused while another job or the queue is active. The data folder
itself and `README.md` are never deleted.

## 12. The sync driver

The `s` action runs `sync.py`, not `tv_pipeline.py`, so it is safe on a restructured
corpus:

1. `Pipeline._merge()` re-reads every cached shard into `pipeline.by_pub`.
2. It diffs `by_pub` against `_manifest.jsonl` to find new scripts.
3. `Pipeline._download()` downloads only those.
4. `write_catalog()` walks the data folder with `os.walk` (folder-safe) and writes
   `catalog.md` with counts, sizes and a source/protected column.
5. It runs `tv.py manifest`, `tv.py index` and `tv.py analyze` as subprocesses,
   streaming their output.

`Reporter.emit_event` converts pipeline `task` events into the same `PROG task|...`
lines the TUI already parses, so the job panel and sparkline work unchanged.

## 13. Extension recipes

### Add a job action

1. Add `def action_<name>(self)` that calls `self._start("Label", [str(CODE / "tools" / "tv.py"), "subcommand", ...])`.
2. Add a `Binding("<key>", "<name>", "Label")`; use `show=False` if the footer is full.
3. Add a tuple to `PALETTE_ACTIONS` in `screens.py`.
4. Add a row to `HELP_SECTIONS`.
5. Optional toolbar: add a `Button(id="btn-<name>")`, map it in `BUTTON_ACTIONS`, and
   update `_render_toolbar` if it should disable while running.

### Add a modal

1. Subclass `ModalScreen[T]` in `screens.py`.
2. Build widgets in `compose`, set `border_title`, and call `fade_in` in `on_mount`.
3. Add `BINDINGS = [Binding("escape", "close", "Close")]`.
4. Return a value with `self.dismiss(value)`.
5. Add CSS to `theme.py`.
6. Push it with `self.push_screen(Screen(), callback)` and handle the value in the app.

### Add a KPI card

1. `yield KpiCard("LABEL", "card-<id>", fmt_count_or_fmt_mb)` inside `#overview`.
2. Feed it in `_apply_stats` through `_update_card("card-<id>", value, delta)`.
3. Add the same value to the details payload if it deserves a row.

### Teach the parser a new progress format

Extend `parse_progress` in `job.py`. Return a dict with any of `stage`, `done`,
`total`, `rate`, `eta_min`, `counters`. Keep the function side-effect free; the app
only reads the dict.

### Add a maintenance action

1. Add an entry to `MAINTENANCE_ITEMS`.
2. Handle it in `_maintenance_result` and describe it in `_maintenance_targets`.
3. Add a mode to `clear.py` with a guard in `safe_root` (require markers for anything
   that deletes bulk data).
4. Test it with `--dry-run` before wiring the TUI path.

### Add a status metric

1. Collect it in `_scan` (keep it cheap; do not walk 62k folders).
2. Add it to `_apply_stats`.
3. Surface it in `_render_sidebar`, `_render_status` or the details payload.

### Restyle

Edit a token in `theme.PALETTE` or add/change a rule in `theme.CSS`. Do not scatter
hex literals through widgets; `KpiCard` and the screens read `P["…"]`.

## 14. Invariants and gotchas

- **Never block the main thread.** Subprocesses are read on `_pump` threads;
  filesystem scans and `_work` measurement run on Textual workers; results come back
  with `call_from_thread`.
- **`App.run_action` is a coroutine in Textual 8.** Do not call it synchronously. The
  app's `_invoke(action)` helper resolves `action_<name>` and calls it.
- **`OptionList` lives in `textual.widgets`; `Option` lives in
  `textual.widgets.option_list`.**
- **Add `DataTable` columns before rows.**
- **`set_focus(None)` clears focus.**
- **Sequence numbers protect the UI.** Every job callback checks `job.seq`; a late
  line from a stopped job is ignored.
- **Queue invariants:** `_launch` only runs when `job is None`. `_on_job_done` and
  `_stop_job` are the only places that pop the queue.
- **`OUT` is a module global.** `_reload_config` reassigns it; modules that imported
  it by value must be updated too.
- **The TUI Python is not necessarily the job Python.** The TUI may run on a
  Textual-only venv; `JOB_PY` is the interpreter that can `import requests`.
- **No `__pycache__`.** Every executable entry point sets
  `sys.dont_write_bytecode = True` before imports. Add the same line to any new
  entry point.
- **Windows helpers:** `os.startfile` opens Explorer/Notepad; pause/resume uses the
  Win32 suspend script. The `.bat` must keep CRLF line endings.
- **The index is usually in WAL mode.** Always size `library.sqlite` plus `-wal` and
  `-shm`, as `_scan` does.
- **Cleanup must stay behind `safe_root`.** Never call `shutil.rmtree` on a path that
  came from a config without the guard.
- **Log filtering is a full re-render of the 2,000-line buffer.** Keep it on Enter,
  not on every keystroke.

## 15. Testing

```powershell
& "<textual-python>" "code files\tui\smoke_test.py"
```

`smoke_test.py` proves:

- renders at 80×24, 120×40 and 160×50;
- SVG screenshots for the dashboard, details, help, filter, history, configure,
  maintenance and danger screens under `code files/tui/_screens/` (ignored by git);
- queue plus double-job completion, palette → help, search, log filtering, history,
  details, configure, maintenance selection, typed confirmation, session clear, calm
  and ASCII toggles;
- a stop/queue test: stop job A (`rc=-1`), auto-start B, expect two session runs and
  two history entries;
- a live scan over the real data folder.

`TV_TUI_NO_SCAN=1` is set for the render/interaction tests. The suite never deletes
data.

Cleanup can be exercised without deleting anything:

```powershell
python "code files\tui\clear.py" index --yes --dry-run
python "code files\tui\clear.py" logs --yes --dry-run
python "code files\tui\clear.py" index --dry-run
```

The second-to-last lists targets; the last is a real-run form without `--yes` and
must exit 2. You can also point `TV_DATA_DIR` at the repo root or a drive root and
confirm the guard refuses.

## 16. Quick reference

| Entry point | Purpose |
|---|---|
| `Pine Harvester TUI.bat` | find a Python with Textual and launch the dashboard |
| `code files/tui/harvester_tui.py` | the app |
| `code files/tui/smoke_test.py` | headless proof |
| `code files/tui/sync.py` | the `s` action driver |
| `code files/tui/clear.py` | guarded cleanup CLI |

Read `harvester_tui.py` top-to-bottom in this order: `compose`, `on_mount`, `_tick`,
`_scan` → `_apply_stats`, `_start` → `_launch` → `_pump` → `_on_line` →
`_apply_progress` → `_on_job_done`, then the `action_*` methods.
