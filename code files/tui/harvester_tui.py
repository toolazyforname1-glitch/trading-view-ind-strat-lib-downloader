#!/usr/bin/env python3
"""Pine Harvester — live terminal dashboard for the TradingView downloader."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    LoadingIndicator,
    ProgressBar,
    RichLog,
    Sparkline,
    Static,
)

from job import Job, classify, parse_progress
from motion import Motion
from paths import CODE, HERE, JOB_PY, LOGS, OUT
from screens import (
    ConfigureScreen,
    ConfirmQuit,
    DangerScreen,
    DetailsScreen,
    HelpScreen,
    HistoryScreen,
    MaintenanceScreen,
    PaletteScreen,
    SearchScreen,
)
from theme import CSS, P
from widgets import KpiCard, fmt_count, fmt_mb

TICK_SECONDS = 0.5
SCAN_RUNNING = 4.0
SCAN_IDLE = 15.0
QUEUE_MAX = 8
LOG_LINES = 60


def env_flag(*names: str) -> bool:
    return any(os.environ.get(name) for name in names)


def count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as handle:
        return sum(1 for _ in handle)


def read_downloaded(path: str) -> tuple[int, int]:
    if not os.path.exists(path):
        return 0, 0
    count = 0
    total = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except Exception:
                continue
            count += 1
            try:
                total += int(record.get("bytes") or 0)
            except Exception:
                pass
    return count, total


def short_path(path: str, limit: int, ascii_only: bool = False) -> str:
    if len(path) <= limit:
        return path
    lead = "..." if ascii_only else "…"
    return lead + path[-(limit - len(lead)):]


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


BUTTON_ACTIONS = {
    "btn-sync": "sync",
    "btn-expand": "expand",
    "btn-desc": "desc",
    "btn-index": "index",
    "btn-find": "find",
    "btn-pause": "pause_toggle",
    "btn-stop": "stop_job",
    "btn-maint": "maintenance",
}


class HarvesterTUI(App):
    """Live status, progress, queue and controls for the Pine harvester."""

    TITLE = "PINE HARVESTER"
    SUB_TITLE = "TradingView ind / strat / lib downloader"
    CSS = CSS
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("s", "sync", "Sync"),
        Binding("e", "expand", "Expand"),
        Binding("c", "desc", "Descriptions"),
        Binding("f", "find", "Find"),
        Binding("ctrl+p", "palette", "Commands", key_display="^p"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+c", "quit_app", "Quit", show=False, priority=True),
        Binding("f1", "help", "Help", show=False),
        Binding("m", "enrich", "Enrich", show=False),
        Binding("a", "analyze", "Analyze", show=False),
        Binding("i", "index", "Index", show=False),
        Binding("v", "verify", "Verify", show=False),
        Binding("o", "open_folder", "Open folder", show=False),
        Binding("l", "open_log", "Open log", show=False),
        Binding("y", "copy_path", "Copy path", show=False),
        Binding("p", "pause", "Pause", show=False),
        Binding("u", "resume", "Resume", show=False),
        Binding("x", "stop_job", "Stop job", show=False),
        Binding("shift+x", "stop_all", "Stop all", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("t", "calm", "Calm mode", show=False),
        Binding("g", "ascii", "ASCII glyphs", show=False),
        Binding("j", "history", "Job history", show=False),
        Binding("shift+d", "maintenance", "Maintenance", show=False),
        Binding("slash", "log_filter", "Filter log", show=False),
        Binding("shift+y", "copy_log", "Copy log", show=False),
        Binding("escape", "dismiss_filter", "Close filter", show=False),
        Binding("end", "log_end", "Latest log", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._calm = env_flag("TV_TUI_CALM", "NO_ANIMATIONS")
        self.motion = Motion(self, enabled=not self._calm)
        self.job: Job | None = None
        self.queue: list[tuple[str, list[str]]] = []
        self._seq = 0
        self._state = "idle"
        self._scanning = False
        self._no_scan = env_flag("TV_TUI_NO_SCAN")
        self._ascii = False
        self._rates: list[float] = []
        self._last_prog: tuple[float, float] | None = None
        self._stats: dict = {}
        self._prev: dict = {}
        self._last_scan = 0.0
        self._refresh_at = "—"
        self._session_jobs = 0
        self._last_label = "—"
        self._last_rc: int | None = None
        self._last_duration = 0.0
        self._log_counts = {"error": 0, "warn": 0}
        self._dirty_status = False
        self._wide_toolbar = False
        self._wide_sidebar = False
        self._log_buffer: deque[str] = deque(maxlen=2000)
        self._log_filter = ""
        self._log_name = "no logs yet"
        self._history: deque[dict] = deque(maxlen=6)
        self._growth: list[float] = []
        self._disk_free_gb = 0.0
        self._started_at = time.monotonic()
        self._maint_summary: dict = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, icon="◆")
        with Horizontal(id="toolbar"):
            yield Button("Sync", id="btn-sync", variant="primary")
            yield Button("Expand", id="btn-expand")
            yield Button("Descriptions", id="btn-desc")
            yield Button("Index", id="btn-index")
            yield Button("Find", id="btn-find")
            yield Button("Pause", id="btn-pause")
            yield Button("Stop", id="btn-stop", variant="error")
            yield Button("Cleanup", id="btn-maint", variant="warning")
        with Horizontal(id="overview"):
            yield KpiCard("ENUMERATED", "card-enumerated", fmt_count)
            yield KpiCard("DOWNLOADED", "card-downloaded", fmt_count)
            yield KpiCard("PROTECTED", "card-protected", fmt_count)
            yield KpiCard("INDEX", "card-index", fmt_mb)
        with Horizontal(id="body"):
            with Vertical(id="main"):
                with Vertical(id="progress"):
                    with Horizontal(id="progrow"):
                        yield LoadingIndicator(id="spin")
                        yield Static("", id="jobtitle")
                        yield Sparkline([], id="spark")
                        yield Static("", id="badge")
                    yield ProgressBar(id="progbar")
                    yield Static("", id="meta")
                with Vertical(id="logpanel"):
                    with Horizontal(id="logfilter"):
                        yield Input(placeholder="filter log…", id="logquery")
                        yield Static(
                            "Enter apply · Esc clear", id="logfilterhint"
                        )
                    yield RichLog(
                        id="log", max_lines=2500, wrap=True, markup=False, highlight=False
                    )
            with Vertical(id="sidebar"):
                with Vertical(id="queue-panel", classes="panel"):
                    yield Static("", id="queue-text")
                with Vertical(id="session-panel", classes="panel"):
                    yield Static("", id="session-text")
                with Vertical(id="data-panel", classes="panel"):
                    yield Static("", id="data-text")
                    yield Sparkline(
                        [],
                        id="growth",
                        min_color=P["border"],
                        max_color=P["accent"],
                    )
        with Horizontal(id="statusbar"):
            yield Static("", id="status-left")
            yield Static("", id="status-right")
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#progress").border_title = "JOB"
        self.query_one("#logpanel").border_title = "ACTIVITY"
        self.query_one("#queue-panel").border_title = "QUEUE"
        self.query_one("#session-panel").border_title = "SESSION"
        self.query_one("#data-panel").border_title = "DATA"
        self._apply_responsive(self.size.width)
        self.query_one("#growth", Sparkline).display = False
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self._render_toolbar()
        self._seed_log()
        self.set_interval(TICK_SECONDS, self._tick)
        self._entrance()
        self._schedule_scan()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive(event.size.width)
        self._render_status()

    def _apply_responsive(self, width: int) -> None:
        toolbar = width >= 100
        sidebar = width >= 120
        if toolbar != self._wide_toolbar:
            self._wide_toolbar = toolbar
            self.query_one("#toolbar").display = toolbar
        if sidebar != self._wide_sidebar:
            self._wide_sidebar = sidebar
            self.query_one("#sidebar").display = sidebar
            if sidebar:
                self._render_sidebar()

    def _entrance(self) -> None:
        if not self.motion.enabled:
            return
        widgets = list(self.query(".card")) + [
            self.query_one("#progress"),
            self.query_one("#logpanel"),
        ]
        for index, widget in enumerate(widgets):
            widget.styles.opacity = 0
            self.motion.to(
                "enter-%d" % index,
                0.0,
                1.0,
                0.22,
                lambda value, target=widget: setattr(target.styles, "opacity", value),
                delay=0.03 * index,
            )

    def _tick(self) -> None:
        if self.job:
            self._render_progress()
        if self._dirty_status:
            self._dirty_status = False
            self._render_status()
            self._render_sidebar()
        if self._no_scan:
            return
        interval = SCAN_RUNNING if self.job else SCAN_IDLE
        if time.monotonic() - self._last_scan >= interval:
            self._schedule_scan()

    def _schedule_scan(self) -> None:
        if self._no_scan or self._scanning:
            return
        self._scanning = True
        self._last_scan = time.monotonic()
        self.run_worker(self._scan, thread=True, group="scan")

    def _scan(self) -> None:
        stats = {
            "path": str(OUT),
            "folders": 0,
            "downloaded": 0,
            "bytes": 0,
            "manifest": 0,
            "index_mb": 0.0,
            "disk_gb": 0.0,
            "refresh": time.strftime("%H:%M:%S"),
        }
        try:
            if os.path.isdir(OUT):
                stats["folders"] = sum(
                    1
                    for entry in os.scandir(OUT)
                    if entry.is_dir() and entry.name != "_work"
                )
            downloaded, total_bytes = read_downloaded(
                os.path.join(OUT, "_downloaded.jsonl")
            )
            stats["downloaded"] = downloaded
            stats["bytes"] = total_bytes
            stats["manifest"] = count_lines(os.path.join(OUT, "_manifest.jsonl"))
            index = os.path.join(OUT, "library.sqlite")
            index_bytes = 0
            for suffix in ("", "-wal", "-shm"):
                path = index + suffix
                if os.path.exists(path):
                    index_bytes += os.path.getsize(path)
            stats["index_mb"] = index_bytes / 1048576
            if os.path.isdir(OUT):
                stats["disk_gb"] = shutil.disk_usage(OUT).free / (1024 ** 3)
        except Exception as exc:
            self.call_from_thread(
                self.notify, "Status scan failed: %s" % exc, severity="error"
            )
        finally:
            self._scanning = False
        self.call_from_thread(self._apply_stats, stats)

    def _apply_stats(self, stats: dict) -> None:
        previous = self._prev
        self._stats = stats
        self._prev = dict(stats)
        self._refresh_at = stats["refresh"]

        manifest = float(stats["manifest"])
        downloaded = float(stats["downloaded"])
        protected = max(0.0, manifest - downloaded)
        index_mb = float(stats["index_mb"])
        self._disk_free_gb = float(stats.get("disk_gb", 0.0))
        self._growth.append(downloaded)
        if len(self._growth) > 40:
            self._growth = self._growth[-40:]
        growth = self.query_one("#growth", Sparkline)
        growth.display = bool(self._growth)
        growth.data = list(self._growth)

        old_manifest = float(previous.get("manifest", manifest))
        old_downloaded = float(previous.get("downloaded", downloaded))
        old_protected = max(0.0, old_manifest - old_downloaded)
        old_index = float(previous.get("index_mb", index_mb))

        self._update_card("card-enumerated", manifest, manifest - old_manifest)
        self._update_card("card-downloaded", downloaded, downloaded - old_downloaded)
        self._update_card("card-protected", protected, protected - old_protected)
        self._update_card("card-index", index_mb, index_mb - old_index)
        self._render_status()
        self._render_sidebar()

    def _update_card(self, card_id: str, value: float, delta: float) -> None:
        card = self.query_one("#" + card_id, KpiCard)
        old = card.value
        card.set_data(old, delta)
        self.motion.to(
            "card-" + card_id,
            old,
            value,
            0.45,
            lambda current, target=card: target.set_value(current),
        )
        if abs(value - old) >= 0.5:
            card.flash()

    def _render_badge(self) -> None:
        if self.job:
            state = "PAUSED" if self._state == "paused" else "RUNNING"
            color = P["warning"] if self._state == "paused" else P["accent"]
        else:
            state = self._state.upper()
            color = {
                "IDLE": P["muted"],
                "DONE": P["success"],
                "ERROR": P["danger"],
                "PAUSED": P["warning"],
            }.get(state, P["muted"])
        glyph = "*" if self._ascii else "●"
        self.query_one("#badge", Static).update(
            Text("%s %s" % (glyph, state), style="bold " + color)
        )

    def _render_progress(self) -> None:
        panel = self.query_one("#progress")
        title = self.query_one("#jobtitle", Static)
        bar = self.query_one("#progbar", ProgressBar)
        meta = self.query_one("#meta", Static)
        spark = self.query_one("#spark", Sparkline)
        spin = self.query_one("#spin", LoadingIndicator)
        job = self.job

        spin.display = bool(job) and not self._calm
        if job is None:
            panel.styles.height = 4
            panel.remove_class("running")
            title.update(
                Text("idle — s sync · e expand · D cleanup · ? keys", style=P["muted"])
            )
            bar.display = False
            spark.display = False
            meta.update(Text(self._idle_meta(), style=P["muted"]))
            return

        panel.styles.height = 5
        panel.add_class("running")
        bar.display = True
        spark.display = bool(self._rates)
        stage = job.stage or job.label
        title.update(
            Text("%s  ·  %s" % (job.label, stage), style="bold " + P["text"])
        )
        if job.total and job.total > 0:
            bar.update(
                total=float(job.total),
                progress=min(job.display_done, float(job.total)),
            )
        else:
            bar.update(total=None)
        meta.update(Text(self._progress_meta(job), style=P["muted"]))

    def _idle_meta(self) -> str:
        parts: list[str] = []
        if self._last_rc is not None:
            parts.append(
                "last %s · rc=%s · %s"
                % (self._last_label, self._last_rc, format_duration(self._last_duration))
            )
        if self.queue:
            parts.append("queue %d" % len(self.queue))
        if not parts:
            parts.append("no job running")
        return "  ·  ".join(parts)

    def _progress_meta(self, job: Job) -> str:
        parts: list[str] = []
        if job.total:
            parts.append("%s / %s" % (fmt_count(job.done), fmt_count(job.total)))
            parts.append(
                "%.0f%%" % (100.0 * min(job.done, job.total) / job.total)
            )
        else:
            parts.append("%s done" % fmt_count(job.done))
        if job.rate:
            parts.append("%.1f/s" % job.rate)
        if job.eta_min:
            parts.append("ETA %.0f min" % job.eta_min)
            parts.append(
                "ends %s"
                % time.strftime(
                    "%H:%M", time.localtime(time.time() + job.eta_min * 60)
                )
            )
        parts.append("elapsed %s" % format_duration(time.monotonic() - job.started))
        if job.counters:
            parts.append(job.counters)
        if self.queue:
            parts.append("queue %d" % len(self.queue))
        return "  ·  ".join(parts)

    def _render_sidebar(self) -> None:
        queue_text = Text()
        if self.queue:
            for index, (label, _argv) in enumerate(self.queue, 1):
                queue_text.append("%d. " % index, style="bold " + P["accent"])
                queue_text.append(label + "\n", style=P["text"])
        else:
            queue_text.append("empty\n", style=P["muted"])
            queue_text.append("press s / e / c to queue work", style=P["muted"])
        self.query_one("#queue-text", Static).update(queue_text)

        session = Text()
        session.append("jobs run   ", style=P["muted"])
        session.append("%d\n" % self._session_jobs, style=P["text"])
        session.append("last       ", style=P["muted"])
        session.append(self._last_label + "\n", style=P["text"])
        session.append("result     ", style=P["muted"])
        if self._last_rc is None:
            session.append("—\n", style=P["muted"])
        elif self._last_rc == 0:
            session.append("rc=0 ✓\n", style=P["success"])
        else:
            session.append("rc=%s ✗\n" % self._last_rc, style=P["danger"])
        session.append("elapsed    ", style=P["muted"])
        session.append(format_duration(self._last_duration) + "\n", style=P["text"])
        session.append("uptime     ", style=P["muted"])
        session.append(
            format_duration(time.monotonic() - self._started_at), style=P["text"]
        )
        self.query_one("#session-text", Static).update(session)

        data = Text()
        data.append(short_path(str(OUT), 34, self._ascii) + "\n", style=P["accent"])
        data.append("workers    ", style=P["muted"])
        data.append(self._workers_state() + "\n", style=P["text"])
        data.append("source     ", style=P["muted"])
        data.append(
            "%.1f MB\n" % (self._stats.get("bytes", 0) / 1048576), style=P["text"]
        )
        data.append("folders    ", style=P["muted"])
        data.append(fmt_count(self._stats.get("folders", 0)) + "\n", style=P["text"])
        data.append("refresh    ", style=P["muted"])
        data.append(self._refresh_at + "\n", style=P["text"])
        data.append("disk free  ", style=P["muted"])
        data.append("%.1f GB\n" % self._disk_free_gb, style=P["text"])
        data.append("growth", style=P["muted"])
        self.query_one("#data-text", Static).update(data)

    def _workers_state(self) -> str:
        if self.job:
            return "paused" if self._state == "paused" else "running"
        return "idle"

    def _render_status(self) -> None:
        compact = self.size.width < 110
        left = Text()
        if not os.path.isdir(OUT):
            left.append("! ", style="bold " + P["danger"])
            left.append("data folder missing ", style=P["danger"])
            left.append(
                short_path(str(OUT), 24 if compact else 40, self._ascii),
                style=P["muted"],
            )
        else:
            glyph = "*" if self._ascii else "●"
            if self.job:
                glyph_color = P["accent"]
            elif self._state == "error":
                glyph_color = P["danger"]
            elif self._state == "done":
                glyph_color = P["success"]
            else:
                glyph_color = P["muted"]
            left.append(glyph + " ", style="bold " + glyph_color)
            left.append(self._state.upper() + "  ", style="bold " + P["text"])
            left.append(
                short_path(str(OUT), 28 if compact else 50, self._ascii),
                style=P["muted"],
            )
        if self.queue and not compact:
            left.append("  queue %d" % len(self.queue), style=P["warning"])

        marker = "~" if self._ascii else "⟳"
        right = Text()
        right.append("%s %s" % (marker, self._refresh_at), style=P["muted"])
        if compact:
            right.append(
                "  q%d" % len(self.queue),
                style=P["warning"] if self.queue else P["muted"],
            )
        else:
            right.append("  jobs %d" % self._session_jobs, style=P["muted"])
            right.append(
                "  err %d" % self._log_counts["error"],
                style=P["danger"] if self._log_counts["error"] else P["muted"],
            )
            right.append(
                "  warn %d" % self._log_counts["warn"],
                style=P["warning"] if self._log_counts["warn"] else P["muted"],
            )
        self.query_one("#status-left", Static).update(left)
        self.query_one("#status-right", Static).update(right)

    def _log_write(self, text: Text) -> None:
        self.query_one("#log", RichLog).write(text)

    def _styled_line(self, line: str) -> Text:
        match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s?(.*)$", line)
        stamp, rest = (match.group(1), match.group(2)) if match else ("", line)
        kind = classify(rest)
        text = Text()
        if stamp:
            text.append(stamp + " ", style=P["muted"])
        if rest.startswith("PROG "):
            text.append(rest, style=P["muted"])
        else:
            text.append(rest, style=P[kind])
        return text

    def _log_line(self, line: str, count: bool = True) -> None:
        self._log_buffer.append(line)
        if count:
            match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s?(.*)$", line)
            rest = match.group(2) if match else line
            kind = classify(rest)
            if kind == "danger":
                self._log_counts["error"] += 1
                self._dirty_status = True
            elif kind == "warning":
                self._log_counts["warn"] += 1
                self._dirty_status = True
        if self._log_filter and self._log_filter.lower() not in line.lower():
            return
        self._log_write(self._styled_line(line))

    def _render_log(self) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        needle = self._log_filter.lower()
        for line in self._log_buffer:
            if not needle or needle in line.lower():
                log.write(self._styled_line(line))
        self._update_log_subtitle()

    def _update_log_subtitle(self) -> None:
        subtitle = self._log_name
        if self._log_filter:
            subtitle = "%s · filter: %s" % (subtitle, self._log_filter)
        self.query_one("#logpanel").border_subtitle = subtitle

    def _seed_log(self) -> None:
        logs: list[Path] = []
        try:
            if os.path.isdir(LOGS):
                logs = sorted(
                    Path(LOGS).glob("*.log"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
        except Exception:
            pass
        if not logs:
            self._log_name = "no logs yet"
            self._update_log_subtitle()
            self._log_write(
                Text(
                    "No collector logs yet — press s to sync or e to expand.",
                    style=P["muted"],
                )
            )
            return
        newest = logs[0]
        self._log_name = newest.name
        self._update_log_subtitle()
        self._log_write(
            Text("── tail of %s ──" % newest.name, style="bold " + P["accent"])
        )
        try:
            lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()[
                -LOG_LINES:
            ]
            for line in lines:
                self._log_line(line, count=False)
        except Exception as exc:
            self._log_write(Text("log read failed: %s" % exc, style=P["danger"]))
        self._log_counts = {"error": 0, "warn": 0}
        self._dirty_status = False

    def _start(self, label: str, argv: list[str]) -> None:
        if len(self.queue) >= QUEUE_MAX:
            self.notify("Queue is full (max %d)." % QUEUE_MAX, severity="warning")
            return
        if self.job:
            if any(label == item[0] for item in self.queue):
                self.notify("%s is already queued." % label, severity="warning")
                return
            self.queue.append((label, argv))
            self._flash_panel("#queue-panel", "flash")
            self.notify("Queued: %s" % label)
            self._render_sidebar()
            self._render_status()
            self._render_progress()
            return
        self._launch(label, argv)

    def _launch(self, label: str, argv: list[str]) -> None:
        if self.job:
            return
        self._seq += 1
        job = Job(label=label, argv=argv, seq=self._seq, started=time.monotonic())
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            job.proc = subprocess.Popen(
                [JOB_PY, "-u", *argv],
                cwd=str(CODE),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except Exception as exc:
            self.notify("Could not start: %s" % exc, severity="error")
            return
        self.job = job
        self._state = "running"
        self._rates.clear()
        self._last_prog = None
        self._log_write(Text("── %s ──" % label, style="bold " + P["accent"]))
        self._log_write(Text("$ %s" % " ".join(argv), style=P["muted"]))
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self._render_toolbar()
        self.notify("Started: %s" % label)
        threading.Thread(target=self._pump, args=(job,), daemon=True).start()

    def _pump(self, job: Job) -> None:
        proc = job.proc
        assert proc is not None and proc.stdout is not None
        try:
            for raw in proc.stdout:
                try:
                    self.call_from_thread(self._on_line, raw.rstrip("\n"), job.seq)
                except Exception:
                    break
        finally:
            try:
                code = proc.wait(timeout=5)
            except Exception:
                code = -1
            try:
                self.call_from_thread(self._on_job_done, job.seq, code)
            except Exception:
                pass

    def _on_line(self, line: str, seq: int) -> None:
        if not self.job or self.job.seq != seq:
            return
        self._log_line(line)
        data = parse_progress(line)
        if data:
            self._apply_progress(data)

    def _apply_progress(self, data: dict) -> None:
        job = self.job
        if job is None:
            return

        now = time.monotonic()
        if "done" in data:
            done = float(data["done"])
            total = data.get("total")
            if total:
                job.total = float(total)
            if self._last_prog and now > self._last_prog[0] and done >= self._last_prog[1]:
                delta = now - self._last_prog[0]
                if delta >= 0.2:
                    job.rate = (done - self._last_prog[1]) / delta
            self._last_prog = (now, done)
            job.done = done
            if job.total and job.total > 0:
                self.motion.to(
                    "bar-%d" % job.seq,
                    job.display_done,
                    min(done, float(job.total)),
                    0.25,
                    lambda value, target=job: self._set_bar(target, value),
                )
            else:
                job.display_done = done

        if data.get("stage"):
            job.stage = str(data["stage"])
        if data.get("rate"):
            job.rate = float(data["rate"])
        if data.get("eta_min") is not None:
            job.eta_min = float(data["eta_min"])
        elif job.total and job.rate > 0:
            job.eta_min = max(0.0, (job.total - job.done) / job.rate / 60)
        if data.get("counters"):
            job.counters = str(data["counters"])

        if job.rate > 0:
            self._rates.append(job.rate)
            if len(self._rates) > 60:
                self._rates = self._rates[-60:]
            self.query_one("#spark", Sparkline).data = list(self._rates)

        self._render_progress()

    def _set_bar(self, job: Job, value: float) -> None:
        job.display_done = float(value)
        try:
            self.query_one("#progbar", ProgressBar).update(progress=float(value))
        except Exception:
            pass

    def _on_job_done(self, seq: int, code: int) -> None:
        if not self.job or self.job.seq != seq:
            return
        label = self.job.label
        duration = time.monotonic() - self.job.started
        self.motion.cancel("bar-%d" % seq)
        self.job = None
        self._session_jobs += 1
        self._last_label = label
        self._last_rc = code
        self._last_duration = duration
        self._history.append(
            {
                "label": label,
                "rc": code,
                "duration": duration,
                "time": time.strftime("%H:%M:%S"),
            }
        )
        self._state = "done" if code == 0 else "error"
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self._render_toolbar()
        self._log_write(
            Text(
                "── %s finished (rc=%s, %.1fs) ──" % (label, code, duration),
                style=P["success"] if code == 0 else P["danger"],
            )
        )
        self._flash_panel(
            "#logpanel", "flash-success" if code == 0 else "flash-error"
        )
        self.notify(
            "%s finished (rc=%s)" % (label, code),
            severity="information" if code == 0 else "error",
            timeout=6,
        )
        self._schedule_scan()
        if self.queue:
            next_label, next_argv = self.queue.pop(0)
            self._render_sidebar()
            self._render_status()
            self.set_timer(0.35, lambda: self._launch(next_label, next_argv))

    def _flash_panel(self, selector: str, css_class: str) -> None:
        panel = self.query_one(selector)
        panel.add_class(css_class)
        self.set_timer(0.7, lambda: panel.remove_class(css_class))

    def _stop_job(self, silent: bool = False) -> None:
        job = self.job
        if not job or not job.proc:
            if not silent and self.queue:
                next_label, next_argv = self.queue.pop(0)
                self.notify("Starting queued: %s" % next_label, severity="information")
                self._render_sidebar()
                self._render_status()
                self._render_progress()
                self._launch(next_label, next_argv)
                return
            if not silent:
                self.notify("No job running.", severity="warning")
            return
        label = job.label
        started = job.started
        proc = job.proc
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.job = None
        self._state = "idle"
        if not silent:
            duration = time.monotonic() - started
            self._session_jobs += 1
            self._last_label = label
            self._last_rc = -1
            self._last_duration = duration
            self._history.append(
                {
                    "label": label,
                    "rc": -1,
                    "duration": duration,
                    "time": time.strftime("%H:%M:%S"),
                }
            )
            self._log_write(
                Text("── %s stopped ──" % label, style=P["warning"])
            )
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self._render_toolbar()
        if not silent:
            self.notify("Job stopped.", severity="warning")
            self._schedule_scan()
            if self.queue:
                next_label, next_argv = self.queue.pop(0)
                self._render_sidebar()
                self._render_status()
                self._render_progress()
                self.notify(
                    "Starting next queued: %s" % next_label, severity="information"
                )
                self.set_timer(0.35, lambda: self._launch(next_label, next_argv))

    def _quick(self, argv: list[str], done_message: str) -> None:
        try:
            result = subprocess.run(
                [JOB_PY, "-u", *argv],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                cwd=str(CODE),
            )
            lines = (result.stdout or "").strip().splitlines()
            message = lines[-1] if lines else done_message
            self.call_from_thread(self.notify, message, severity="information")
        except Exception as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")

    def _render_toolbar(self) -> None:
        if not self._wide_toolbar:
            return
        running = self.job is not None
        for button_id in ("btn-sync", "btn-expand", "btn-desc", "btn-index"):
            self.query_one("#" + button_id, Button).disabled = running
        pause = self.query_one("#btn-pause", Button)
        pause.label = "Resume" if self._state == "paused" else "Pause"
        pause.disabled = not running
        self.query_one("#btn-stop", Button).disabled = not running
        self.query_one("#btn-maint", Button).disabled = running or bool(self.queue)

    def _session_snapshot(self) -> dict:
        return {
            "jobs": self._session_jobs,
            "last": self._last_label if self._last_rc is not None else "—",
            "rc": self._last_rc,
            "duration": self._last_duration,
        }

    def _invoke(self, action: str) -> None:
        handler = getattr(self, "action_" + action, None)
        if handler:
            handler()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = BUTTON_ACTIONS.get(event.button.id or "")
        if action:
            self._invoke(action)

    def on_click(self, event: events.Click) -> None:
        if isinstance(event.widget, KpiCard):
            payload = dict(self._stats)
            payload["path"] = str(OUT)
            payload["disk_gb"] = self._disk_free_gb
            payload["uptime"] = format_duration(time.monotonic() - self._started_at)
            self.push_screen(
                DetailsScreen(
                    payload,
                    [label for label, _argv in self.queue],
                    self._session_snapshot(),
                    self._workers_state(),
                )
            )

    def action_sync(self) -> None:
        self._start("Sync", [str(HERE / "sync.py")])

    def action_expand(self) -> None:
        self._start("Expand coverage", [str(CODE / "tools" / "tv.py"), "expand", "all"])

    def action_desc(self) -> None:
        self._start("Descriptions · phase 2", [str(CODE / "tools" / "tv.py"), "desc", "2"])

    def action_enrich(self) -> None:
        self._start("Enrich · meta", [str(CODE / "tools" / "tv.py"), "enrich", "meta"])

    def action_analyze(self) -> None:
        self._start("Analyze", [str(CODE / "tools" / "tv.py"), "analyze"])

    def action_index(self) -> None:
        self._start("Rebuild index", [str(CODE / "tools" / "tv.py"), "index"])

    def action_verify(self) -> None:
        self._start("Verify", [str(CODE / "tools" / "tv.py"), "verify"])

    def action_manifest(self) -> None:
        self._start("Rebuild manifest", [str(CODE / "tools" / "tv.py"), "manifest"])

    def action_find(self) -> None:
        self.push_screen(SearchScreen())

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_palette(self) -> None:
        self.push_screen(PaletteScreen(), self._palette_result)

    def _palette_result(self, action: str | None) -> None:
        if action:
            self._invoke(action)

    def action_history(self) -> None:
        self.push_screen(HistoryScreen(list(reversed(self._history))))

    def action_maintenance(self) -> None:
        if self.job or self.queue:
            self.notify("Stop active and queued jobs first.", severity="warning")
            return
        self._maint_summary = self._maintenance_summary()
        self.push_screen(
            MaintenanceScreen(self._maint_summary), self._maintenance_result
        )

    def _maintenance_summary(self) -> dict:
        summary = {
            "source_folders": 0,
            "source_bytes": 0,
            "index_bytes": 0,
            "manifest_bytes": 0,
            "logs_bytes": 0,
        }
        if os.path.isdir(OUT):
            summary["source_folders"] = sum(
                1
                for entry in os.scandir(OUT)
                if entry.is_dir() and entry.name != "_work"
            )
            summary["source_bytes"] = read_downloaded(
                os.path.join(OUT, "_downloaded.jsonl")
            )[1]
            for suffix in ("", "-wal", "-shm"):
                path = os.path.join(OUT, "library.sqlite" + suffix)
                if os.path.exists(path):
                    summary["index_bytes"] += os.path.getsize(path)
            for name in ("_manifest.csv", "_manifest.jsonl", "_manifest_stats.json"):
                path = os.path.join(OUT, name)
                if os.path.exists(path):
                    summary["manifest_bytes"] += os.path.getsize(path)
        if os.path.isdir(LOGS):
            for name in os.listdir(LOGS):
                if name.lower().endswith(".log"):
                    try:
                        summary["logs_bytes"] += os.path.getsize(
                            os.path.join(LOGS, name)
                        )
                    except OSError:
                        pass
        return summary

    def _maintenance_result(self, result: dict | None) -> None:
        if not result:
            return
        action = result.get("action")
        if not action:
            return
        if self.job or self.queue:
            self.notify("Stop active and queued jobs first.", severity="warning")
            return
        if action == "session":
            self.push_screen(
                DangerScreen(
                    "Clear session",
                    [
                        "Queue, history, log view and counters",
                        "No files will be deleted",
                    ],
                    None,
                    "This only resets the dashboard.",
                ),
                self._session_confirm,
            )
            return
        labels = {
            "logs": "Clear logs",
            "cache": "Clear work cache",
            "index": "Clear index",
            "manifests": "Clear manifests",
            "source": "Clear downloaded source",
            "everything": "Clear EVERYTHING",
        }
        word = "CLEAR" if action in ("logs", "cache", "index", "manifests") else "DELETE"
        self.push_screen(
            DangerScreen(
                labels.get(action, action),
                self._maintenance_targets(
                    action,
                    int(result.get("work_files", 0)),
                    int(result.get("work_bytes", 0)),
                ),
                word,
                "This cannot be undone.",
            ),
            lambda confirmed: self._clear_confirmed(action, confirmed),
        )

    def _maintenance_targets(
        self, action: str, work_files: int, work_bytes: int
    ) -> list[str]:
        summary = self._maint_summary
        if action == "logs":
            return [
                "code files\\logs\\*.log",
                "%.1f KB" % (summary.get("logs_bytes", 0) / 1024),
            ]
        if action == "cache":
            detail = (
                "%s files · %.1f MB"
                % ("{:,}".format(work_files), work_bytes / 1048576)
                if work_files
                else "work cache folder"
            )
            return ["%s\\_work" % OUT, detail]
        if action == "index":
            return [
                "library.sqlite + WAL/SHM",
                "%.1f MB" % (summary.get("index_bytes", 0) / 1048576),
            ]
        if action == "manifests":
            return [
                "_manifest.csv, _manifest.jsonl, _manifest_stats.json",
                "%.1f MB" % (summary.get("manifest_bytes", 0) / 1048576),
            ]
        if action == "source":
            return [
                "%s script folders" % "{:,}".format(int(summary.get("source_folders", 0))),
                "_downloaded.jsonl and catalog.md",
                "%.1f MB" % (summary.get("source_bytes", 0) / 1048576),
            ]
        if action == "everything":
            total = (
                summary.get("source_bytes", 0)
                + summary.get("index_bytes", 0)
                + summary.get("manifest_bytes", 0)
                + work_bytes
            )
            return [
                "source, manifests, index and work cache",
                "the data folder itself is kept",
                "%.1f GB total" % (total / 1073741824),
            ]
        return []

    def _session_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self._clear_session()

    def _clear_session(self) -> None:
        if self.job or self.queue:
            self.notify("Stop active and queued jobs first.", severity="warning")
            return
        self.queue.clear()
        self._history.clear()
        self._log_buffer.clear()
        self.query_one("#log", RichLog).clear()
        self._log_counts = {"error": 0, "warn": 0}
        self._rates.clear()
        self._session_jobs = 0
        self._last_label = "—"
        self._last_rc = None
        self._last_duration = 0.0
        self._state = "idle"
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self.notify("Session cleared — no files deleted.")

    def _clear_confirmed(self, action: str, confirmed: bool) -> None:
        if not confirmed:
            return
        self._start(
            "Clear %s" % action,
            [str(HERE / "clear.py"), action, "--yes"],
        )

    def action_configure(self) -> None:
        self.push_screen(ConfigureScreen(), self._configure_result)

    def _configure_result(self, path: str | None) -> None:
        if path:
            self.run_worker(
                lambda: self._apply_configure(path), thread=True, group="configure"
            )

    def _apply_configure(self, path: str) -> None:
        try:
            result = subprocess.run(
                [JOB_PY, "-u", str(CODE / "tools" / "tv.py"), "configure", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
            message = output[-1] if output else "configure done"
            if result.returncode == 0:
                self.call_from_thread(self._reload_config)
            self.call_from_thread(
                self.notify,
                message,
                severity="information" if result.returncode == 0 else "error",
            )
        except Exception as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")

    def _reload_config(self) -> None:
        global OUT
        import importlib

        import tv_config

        importlib.reload(tv_config)
        OUT = tv_config.OUT
        import paths

        paths.OUT = OUT
        self._stats = {}
        self._prev = {}
        self._growth.clear()
        self.query_one("#growth", Sparkline).display = False
        self._render_status()
        self._render_sidebar()
        self._render_progress()
        self._schedule_scan()
        self.notify("Data folder set to %s" % OUT)

    def action_open_folder(self) -> None:
        if not os.path.isdir(OUT):
            self.notify("Data folder does not exist: %s" % OUT, severity="warning")
            return
        try:
            os.startfile(OUT)
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_open_log(self) -> None:
        logs: list[Path] = []
        try:
            if os.path.isdir(LOGS):
                logs = sorted(
                    Path(LOGS).glob("*.log"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
        except Exception:
            pass
        if not logs:
            self.notify("No log files yet.", severity="warning")
            return
        try:
            os.startfile(str(logs[0]))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_copy_path(self) -> None:
        try:
            self.copy_to_clipboard(str(OUT))
            self.notify("Data-folder path copied.")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_log_filter(self) -> None:
        bar = self.query_one("#logfilter")
        if bar.display:
            self.action_dismiss_filter()
            return
        bar.display = True
        field = self.query_one("#logquery", Input)
        field.value = self._log_filter
        field.focus()

    def action_dismiss_filter(self) -> None:
        bar = self.query_one("#logfilter")
        if not bar.display:
            return
        bar.display = False
        self._log_filter = ""
        self._render_log()
        self.set_focus(None)

    def action_copy_log(self) -> None:
        lines = "\n".join(list(self._log_buffer)[-50:])
        try:
            self.copy_to_clipboard(lines)
            self.notify("Copied last %d log line(s)." % min(50, len(self._log_buffer)))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "logquery":
            self._log_filter = event.value.strip()
            self._render_log()
            self.notify("Log filter: %s" % (self._log_filter or "cleared"))

    def action_log_end(self) -> None:
        self.query_one("#log", RichLog).scroll_end(animate=not self._calm)

    def action_pause(self) -> None:
        if self.job:
            self._state = "paused"
            self._render_badge()
            self._render_progress()
            self._render_sidebar()
            self._render_status()
            self._render_toolbar()
        self.run_worker(
            lambda: self._quick(
                [str(CODE / "tools" / "tv.py"), "pause"], "workers paused"
            ),
            thread=True,
            group="quick",
        )

    def action_resume(self) -> None:
        if self.job:
            self._state = "running"
            self._render_badge()
            self._render_progress()
            self._render_sidebar()
            self._render_status()
            self._render_toolbar()
        self.run_worker(
            lambda: self._quick(
                [str(CODE / "tools" / "tv.py"), "resume"], "workers resumed"
            ),
            thread=True,
            group="quick",
        )

    def action_pause_toggle(self) -> None:
        if self._state == "paused":
            self.action_resume()
        else:
            self.action_pause()

    def action_stop_job(self) -> None:
        self._stop_job()

    def action_stop_all(self) -> None:
        queued = len(self.queue)
        self.queue.clear()
        self._stop_job(silent=True)
        self._render_sidebar()
        self._render_status()
        self._render_progress()
        self._render_toolbar()
        self.notify(
            "Stopped job and cleared %d queued item(s)." % queued, severity="warning"
        )

    def action_refresh(self) -> None:
        self._schedule_scan()

    def action_calm(self) -> None:
        self._calm = not self._calm
        self.motion.set_enabled(not self._calm)
        self._render_badge()
        self._render_progress()
        self.notify("Calm mode %s" % ("on" if self._calm else "off"))

    def action_ascii(self) -> None:
        self._ascii = not self._ascii
        self._render_badge()
        self._render_progress()
        self._render_sidebar()
        self._render_status()
        self.notify("ASCII glyphs %s" % ("on" if self._ascii else "off"))

    def action_quit_app(self) -> None:
        if self.job or self.queue:
            self.push_screen(ConfirmQuit(), self._after_quit)
        else:
            self.exit()

    def _after_quit(self, confirmed: bool) -> None:
        if confirmed:
            self.queue.clear()
            self._stop_job(silent=True)
            self.exit()

    def on_unmount(self) -> None:
        self.motion.finish_all()
        self._stop_job(silent=True)


def main() -> None:
    HarvesterTUI().run()


if __name__ == "__main__":
    main()
