"""Modal screens for search, help, commands, details and quit."""
from __future__ import annotations

import os
import subprocess
import time

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, LoadingIndicator, OptionList, Static
from textual.widgets.option_list import Option

from paths import CODE, JOB_PY, OUT
from theme import P


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def fade_in(screen, widget_id: str, key: str) -> None:
    box = screen.query_one("#" + widget_id)
    box.styles.opacity = 0
    screen.app.motion.to(
        key, 0.0, 1.0, 0.16, lambda value: setattr(box.styles, "opacity", value)
    )


class SearchScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("y", "copy_path", "Copy path"),
        Binding("o", "open_row", "Open folder"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="searchbox"):
            yield Input(placeholder="FTS query — try: fibonacci", id="q")
            yield LoadingIndicator(id="searchload")
            yield DataTable(id="results")
            yield Static(
                "Enter search · ↑↓ select · y copy · o open · Esc close", id="hint"
            )

    def on_mount(self) -> None:
        fade_in(self, "searchbox", "modal-search")
        self.query_one("#searchbox").border_title = "SEARCH"
        table = self.query_one("#results", DataTable)
        table.add_columns("Name", "Author", "Path")
        table.cursor_type = "row"
        self.query_one("#searchload").display = False
        self.query_one("#q", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.query_one("#searchload").display = True
        self.query_one("#hint", Static).update("searching…")
        self.run_worker(lambda: self._search(query), thread=True, group="search")

    def _search(self, query: str) -> None:
        rows: list[tuple[str, str, str]] = []
        error = ""
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [JOB_PY, "-u", str(CODE / "tools" / "tv.py"), "index", query],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            for line in proc.stdout.splitlines():
                parts = line.split(" | ")
                if len(parts) >= 3:
                    rows.append((parts[0], parts[1], parts[2]))
            if proc.returncode != 0:
                error = (proc.stderr or "index query failed").strip().splitlines()[-1]
        except Exception as exc:
            error = str(exc)
        self.app.call_from_thread(self._fill, rows, error, time.monotonic() - started)

    def _fill(self, rows: list[tuple[str, str, str]], error: str, elapsed: float) -> None:
        self.query_one("#searchload").display = False
        table = self.query_one("#results", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)
        hint = self.query_one("#hint", Static)
        if error:
            hint.update(Text(error, style=P["danger"]))
        elif rows:
            hint.update(
                "%d result(s) · %.2fs · ↑↓ select · y copy · o open · Esc close"
                % (len(rows), elapsed)
            )
            table.focus()
        else:
            hint.update("no matches · %.2fs · Esc close" % elapsed)
            self.query_one("#q", Input).focus()

    def _selected_path(self) -> str | None:
        table = self.query_one("#results", DataTable)
        if table.row_count == 0:
            return None
        try:
            return str(table.get_row_at(table.cursor_row)[2])
        except Exception:
            return None

    def action_copy_path(self) -> None:
        path = self._selected_path()
        if not path:
            self.app.notify("No result selected.", severity="warning")
            return
        try:
            self.app.copy_to_clipboard(path)
            self.app.notify("Path copied.")
        except Exception as exc:
            self.app.notify(str(exc), severity="error")

    def action_open_row(self) -> None:
        path = self._selected_path()
        if not path:
            self.app.notify("No result selected.", severity="warning")
            return
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            self.app.notify("Folder not found: %s" % folder, severity="warning")
            return
        try:
            os.startfile(folder)
        except Exception as exc:
            self.app.notify(str(exc), severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_open_row()

    def action_close(self) -> None:
        self.dismiss(None)


HELP_SECTIONS = [
    (
        "JOBS",
        [
            ("s", "Sync: merge caches, download new, rebuild catalog/manifest/index"),
            ("e", "Expand coverage"),
            ("c", "Full descriptions, phase 2"),
            ("m", "Enrich metadata"),
            ("a", "Local analysis"),
            ("i", "Rebuild the FTS index"),
            ("v", "Verify integrity"),
            ("p / u", "Pause / resume detached workers"),
            ("x", "Stop the current job"),
            ("X", "Stop the job and clear the queue"),
        ],
    ),
    (
        "VIEW",
        [
            ("f", "Search the FTS index"),
            ("^p", "Command palette"),
            ("o", "Open the data folder"),
            ("l", "Open the newest log"),
            ("y", "Copy the data-folder path"),
            ("/", "Filter the activity log"),
            ("Y", "Copy the last 50 log lines"),
            ("j", "Job history"),
            ("End", "Jump the log to the latest line"),
            ("r", "Refresh status counts"),
        ],
    ),
    (
        "DATA",
        [
            ("D", "Maintenance & cleanup (double confirmation)"),
            ("^p", "Also: Rebuild manifest, Set data folder"),
        ],
    ),
    (
        "SYSTEM",
        [
            ("t", "Calm mode: disable motion and the spinner"),
            ("g", "ASCII glyphs"),
            ("?", "This help"),
            ("q", "Quit (confirms while a job runs)"),
        ],
    ),
]


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        body = Text()
        for title, rows in HELP_SECTIONS:
            body.append(title + "\n", style="bold " + P["accent2"])
            for key, description in rows:
                body.append("%-9s" % key, style="bold " + P["accent"])
                body.append(description + "\n", style=P["text"])
            body.append("\n")
        body.append(
            "Reduced motion: t, or set NO_ANIMATIONS=1 before launching.\n",
            style=P["muted"],
        )
        with VerticalScroll(id="helpbox"):
            yield Static(body, id="helptext")

    def on_mount(self) -> None:
        fade_in(self, "helpbox", "modal-help")
        box = self.query_one("#helpbox", VerticalScroll)
        box.border_title = "KEYS"
        box.border_subtitle = "↑↓ scroll · Esc close"
        box.focus()

    def action_close(self) -> None:
        self.dismiss(None)

PALETTE_ACTIONS = [
    ("sync", "Sync", "merge caches, download new, rebuild indexes"),
    ("expand", "Expand coverage", "crawl more search dimensions"),
    ("desc", "Descriptions", "fetch full descriptions, phase 2"),
    ("enrich", "Enrich metadata", "facade metadata for open scripts"),
    ("analyze", "Analyze", "hashes, tags, imports, inputs"),
    ("index", "Rebuild index", "rebuild the SQLite FTS index"),
    ("verify", "Verify", "integrity check"),
    ("manifest", "Rebuild manifest", "recreate _manifest.csv/.jsonl from cache"),
    ("history", "Job history", "recent runs, results and durations"),
    ("configure", "Set data folder", "choose where indicators live"),
    ("maintenance", "Maintenance & cleanup", "clear logs, cache, index, manifests or source"),
    ("find", "Find", "search the FTS index"),
    ("refresh", "Refresh", "rescan status counts"),
    ("open_folder", "Open data folder", "in Explorer"),
    ("open_log", "Open newest log", "in the default editor"),
    ("copy_path", "Copy data path", "to the clipboard"),
    ("copy_log", "Copy log", "last 50 activity lines"),
    ("log_filter", "Filter log", "narrow the activity panel"),
    ("pause", "Pause workers", "suspend detached workers"),
    ("resume", "Resume workers", "resume suspended workers"),
    ("stop_job", "Stop job", "terminate the current job"),
    ("stop_all", "Stop all", "stop the job and clear the queue"),
    ("calm", "Toggle calm mode", "disable motion and the spinner"),
    ("ascii", "Toggle ASCII glyphs", "fallback for limited fonts"),
    ("help", "Help", "keyboard reference"),
    ("quit_app", "Quit", "exit the dashboard"),
]


class PaletteScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self._matches: list[tuple[str, str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="palettebox"):
            yield Input(placeholder="Type a command…", id="pquery")
            yield OptionList(id="poptions")
            yield Static("↑↓ move · Enter run · Esc close", id="phint")

    def on_mount(self) -> None:
        fade_in(self, "palettebox", "modal-palette")
        self.query_one("#palettebox").border_title = "COMMANDS"
        self._fill("")
        self.query_one("#pquery", Input).focus()

    def _fill(self, query: str) -> None:
        options = self.query_one("#poptions", OptionList)
        options.clear_options()
        needle = query.lower().strip()
        self._matches = [
            item
            for item in PALETTE_ACTIONS
            if not needle
            or needle in item[0].lower()
            or needle in item[1].lower()
            or needle in item[2].lower()
        ]
        for action, label, description in self._matches:
            options.add_option(Option("%s  ·  %s" % (label, description), id=action))
        if self._matches:
            options.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    def on_key(self, event) -> None:
        if event.key in ("down", "up"):
            count = len(self._matches)
            if count:
                options = self.query_one("#poptions", OptionList)
                step = 1 if event.key == "down" else -1
                options.highlighted = (options.highlighted + step) % count
            event.stop()
        elif event.key == "enter":
            self._choose()
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._choose()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def _choose(self) -> None:
        if not self._matches:
            return
        options = self.query_one("#poptions", OptionList)
        index = options.highlighted
        if 0 <= index < len(self._matches):
            self.dismiss(self._matches[index][0])

    def action_close(self) -> None:
        self.dismiss(None)


class DetailsScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("y", "copy_path", "Copy path"),
        Binding("o", "open_folder", "Open folder"),
    ]

    def __init__(self, stats: dict, queue: list[str], session: dict, state: str) -> None:
        super().__init__()
        self._stats = stats
        self._queue = queue
        self._session = session
        self._state = state

    def compose(self) -> ComposeResult:
        table = Table.grid(padding=(0, 2))
        table.add_column(style=P["muted"], no_wrap=True)
        table.add_column(style=P["text"])
        table.add_row("data folder", str(self._stats.get("path", "")))
        table.add_row("", "")
        table.add_row("enumerated", "{:,}".format(int(self._stats.get("manifest", 0))))
        table.add_row(
            "downloaded", "{:,}".format(int(self._stats.get("downloaded", 0)))
        )
        table.add_row(
            "protected",
            "{:,}".format(
                max(
                    0,
                    int(self._stats.get("manifest", 0))
                    - int(self._stats.get("downloaded", 0)),
                )
            ),
        )
        table.add_row("folders", "{:,}".format(int(self._stats.get("folders", 0))))
        table.add_row("source", "%.1f MB" % (self._stats.get("bytes", 0) / 1048576))
        table.add_row("index", "%.1f MB" % self._stats.get("index_mb", 0.0))
        table.add_row("disk free", "%.1f GB" % self._stats.get("disk_gb", 0.0))
        table.add_row("uptime", str(self._stats.get("uptime", "—")))
        table.add_row("", "")
        table.add_row("workers", self._state)
        table.add_row("jobs run", str(self._session.get("jobs", 0)))
        table.add_row("last job", self._session.get("last", "—"))
        table.add_row("queue", ", ".join(self._queue) if self._queue else "empty")
        table.add_row("refreshed", str(self._stats.get("refresh", "—")))
        with Vertical(id="detailsbox"):
            yield Static(table, id="details")
            yield Static("y copy path · o open folder · Esc close", id="detailhint")

    def on_mount(self) -> None:
        fade_in(self, "detailsbox", "modal-details")
        self.query_one("#detailsbox").border_title = "DETAILS"

    def action_copy_path(self) -> None:
        try:
            self.app.copy_to_clipboard(str(self._stats.get("path", "")))
            self.app.notify("Data-folder path copied.")
        except Exception as exc:
            self.app.notify(str(exc), severity="error")

    def action_open_folder(self) -> None:
        path = str(self._stats.get("path", ""))
        if not os.path.isdir(path):
            self.app.notify("Data folder not found: %s" % path, severity="warning")
            return
        try:
            os.startfile(path)
        except Exception as exc:
            self.app.notify(str(exc), severity="error")

    def action_close(self) -> None:
        self.dismiss(None)


class HistoryScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, history: list[dict]) -> None:
        super().__init__()
        self._history = history

    def compose(self) -> ComposeResult:
        with Vertical(id="historybox"):
            yield DataTable(id="historytable")
            yield Static("Esc close", id="historyhint")

    def on_mount(self) -> None:
        fade_in(self, "historybox", "modal-history")
        self.query_one("#historybox").border_title = "JOB HISTORY"
        table = self.query_one("#historytable", DataTable)
        table.add_columns("Job", "Result", "Duration", "Finished")
        table.cursor_type = "row"
        if not self._history:
            table.add_row("no jobs yet", "", "", "")
            return
        for item in self._history:
            code = item.get("rc")
            if code == 0:
                result = Text("rc=0 ✓", style=P["success"])
            else:
                result = Text("rc=%s ✗" % code, style=P["danger"])
            table.add_row(
                str(item.get("label", "")),
                result,
                _duration(float(item.get("duration", 0.0))),
                str(item.get("time", "")),
            )

    def action_close(self) -> None:
        self.dismiss(None)


class ConfigureScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="configurebox"):
            yield Input(placeholder=str(OUT), id="cpath")
            yield Static("Enter set · Esc cancel", id="chint")

    def on_mount(self) -> None:
        fade_in(self, "configurebox", "modal-configure")
        self.query_one("#configurebox").border_title = "DATA FOLDER"
        self.query_one("#cpath", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        if path:
            self.dismiss(path)

    def action_close(self) -> None:
        self.dismiss("")


MAINTENANCE_ITEMS = [
    ("session", "Clear session", "queue, history, log view and counters — no files"),
    ("logs", "Clear logs", "code files\\logs\\*.log"),
    ("cache", "Clear work cache", "OUT\\_work — pages, keywords, descriptions, enrichment"),
    ("index", "Clear index", "library.sqlite and its WAL/SHM files"),
    ("manifests", "Clear manifests", "_manifest.csv, _manifest.jsonl, _manifest_stats.json"),
    ("source", "Clear downloaded source", "every script folder plus _downloaded.jsonl and catalog.md"),
    ("everything", "Clear EVERYTHING", "source, manifests, index and work cache"),
]


class MaintenanceScreen(ModalScreen[dict]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, summary: dict) -> None:
        super().__init__()
        self._summary = dict(summary)
        self._work_files = 0
        self._work_bytes = 0
        self._alive = True

    def compose(self) -> ComposeResult:
        with Vertical(id="maintenancebox"):
            yield Static("", id="msummary")
            yield OptionList(id="moptions")
            yield Static(
                "↑↓ select · Enter choose · Esc close · destructive actions ask twice",
                id="mhint",
            )

    def on_mount(self) -> None:
        fade_in(self, "maintenancebox", "modal-maintenance")
        self.query_one("#maintenancebox").border_title = "MAINTENANCE"
        options = self.query_one("#moptions", OptionList)
        for action, label, description in MAINTENANCE_ITEMS:
            options.add_option(Option("%s  ·  %s" % (label, description), id=action))
        options.highlighted = 0
        options.focus()
        self._render_summary()
        self.run_worker(self._measure_work, thread=True, group="measure")

    def on_unmount(self) -> None:
        self._alive = False

    def _render_summary(self) -> None:
        summary = self._summary
        text = Text()

        def row(label: str, value: str) -> None:
            text.append("%-10s" % label, style=P["muted"])
            text.append(value + "\n", style=P["text"])

        row(
            "source",
            "%s folders · %.1f MB"
            % (
                "{:,}".format(int(summary.get("source_folders", 0))),
                summary.get("source_bytes", 0) / 1048576,
            ),
        )
        if self._work_files:
            row(
                "work",
                "%s files · %.1f MB"
                % ("{:,}".format(self._work_files), self._work_bytes / 1048576),
            )
        else:
            row("work", "measuring…")
        row("index", "%.1f MB" % (summary.get("index_bytes", 0) / 1048576))
        row("manifests", "%.1f MB" % (summary.get("manifest_bytes", 0) / 1048576))
        row("logs", "%.1f KB" % (summary.get("logs_bytes", 0) / 1024))
        self.query_one("#msummary", Static).update(text)

    def _measure_work(self) -> None:
        work = os.path.join(OUT, "_work")
        files = 0
        total = 0
        for root, _dirs, names in os.walk(work):
            if not self._alive:
                return
            for name in names:
                files += 1
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        try:
            self.app.call_from_thread(self._set_work, files, total)
        except Exception:
            pass

    def _set_work(self, files: int, total: int) -> None:
        self._work_files = files
        self._work_bytes = total
        self._render_summary()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(
            {
                "action": event.option.id,
                "work_files": self._work_files,
                "work_bytes": self._work_bytes,
            }
        )

    def action_close(self) -> None:
        self.dismiss({})


class DangerScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self, title: str, lines: list[str], word: str | None, note: str
    ) -> None:
        super().__init__()
        self._title = title
        self._lines = lines
        self._word = word
        self._note = note

    def compose(self) -> ComposeResult:
        with Vertical(id="dangerbox"):
            yield Static(self._body(), id="dangertext")
            yield Input(
                placeholder=("type %s to confirm" % self._word)
                if self._word
                else "confirm",
                id="dconfirm",
            )
            with Horizontal(id="dbuttons"):
                yield Button(
                    "Delete", id="delete", variant="error", disabled=bool(self._word)
                )
                yield Button("Cancel", id="cancel")
            yield Static("Esc cancels · this cannot be undone", id="dangerhint")

    def _body(self) -> Text:
        text = Text()
        text.append(self._title + "\n\n", style="bold " + P["danger"])
        for line in self._lines:
            text.append("▸ ", style=P["danger"])
            text.append(line + "\n", style=P["text"])
        text.append("\n" + self._note, style=P["warning"])
        return text

    def on_mount(self) -> None:
        fade_in(self, "dangerbox", "modal-danger")
        self.query_one("#dangerbox").border_title = "CONFIRM"
        if self._word:
            self.query_one("#dconfirm", Input).focus()
        else:
            self.query_one("#delete", Button).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._word:
            self.query_one("#delete", Button).disabled = (
                event.value.strip().upper() != self._word.upper()
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ConfirmQuit(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="quitbox"):
            yield Static("A job is running.\nStop it and quit?", id="quittext")
            with Horizontal(classes="buttons"):
                yield Button("Stop & quit", id="yes", variant="error")
                yield Button("Keep running", id="no", variant="primary")

    def on_mount(self) -> None:
        fade_in(self, "quitbox", "modal-quit")
        self.query_one("#quitbox").border_title = "QUIT"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)
