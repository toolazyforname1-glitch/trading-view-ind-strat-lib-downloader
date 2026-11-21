#!/usr/bin/env python3
"""Destructive cleanup for harvester data. Requires --yes; --dry-run is read-only."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import bootstrap  # noqa: F401,E402

from tv_config import LOGS, OUT  # noqa: E402

MANIFESTS = ("_manifest.csv", "_manifest.jsonl", "_manifest_stats.json")
INDEX_FILES = ("library.sqlite", "library.sqlite-wal", "library.sqlite-shm")
MARKERS = (
    "_manifest.jsonl",
    "_manifest.csv",
    "_downloaded.jsonl",
    "library.sqlite",
    "catalog.md",
)


def say(message: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), message), flush=True)


def prog(label: str, done: int, total: int) -> None:
    print(
        "[%s] PROG task|%s|%d|%d|" % (time.strftime("%H:%M:%S"), label, done, total),
        flush=True,
    )


def fail(message: str) -> None:
    say("refusing: " + message)
    raise SystemExit(2)


def safe_root(require_marker: bool = False, require_work: bool = False) -> str:
    root = os.path.realpath(os.path.abspath(OUT))
    if not os.path.isdir(root):
        fail("data folder not found: %s" % root)
    drive, _ = os.path.splitdrive(root)
    root_key = os.path.normcase(root)
    if root_key == os.path.normcase(drive + os.sep):
        fail("data folder is a drive root")
    home = os.path.normcase(os.path.realpath(os.path.expanduser("~")))
    if root_key == home or home.startswith(root_key + os.sep):
        fail("data folder is or contains the user home")
    for guarded, label in ((CODE, "code folder"), (ROOT, "project root")):
        guard = os.path.normcase(os.path.realpath(os.path.abspath(guarded)))
        if root_key == guard or guard.startswith(root_key + os.sep):
            fail("data folder contains the %s" % label)
    entries = list(os.scandir(root))
    has_marker = any(os.path.exists(os.path.join(root, name)) for name in MARKERS)
    has_folder = any(entry.is_dir() and entry.name != "_work" for entry in entries)
    has_work = any(entry.is_dir() and entry.name == "_work" for entry in entries)
    if require_marker and not has_marker:
        fail("no harvester ledger markers in the data folder")
    if require_work and not (has_work or has_marker):
        fail("no work cache or ledger in the data folder")
    if not (has_marker or has_folder or has_work):
        fail("folder does not look like harvester data")
    return root


def remove(path: str) -> bool:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
            return not os.path.exists(path)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception as exc:
        say("remove failed %s: %s" % (path, exc))
        return False


def report(action: str, path: str, dry: bool) -> None:
    say("%s %s" % ("would remove" if dry else "removed", path))
    if not dry:
        remove(path)


def clear_logs(dry: bool) -> None:
    files: list[str] = []
    if os.path.isdir(LOGS):
        files = [
            os.path.join(LOGS, name)
            for name in os.listdir(LOGS)
            if name.lower().endswith(".log")
        ]
    size = 0
    for path in files:
        try:
            size += os.path.getsize(path)
        except OSError:
            pass
    say("logs: %d file(s), %.1f KB" % (len(files), size / 1024))
    for path in files:
        report("logs", path, dry)


def clear_index(root: str, dry: bool) -> None:
    for name in INDEX_FILES:
        path = os.path.join(root, name)
        if os.path.exists(path):
            report("index", path, dry)


def clear_manifests(root: str, dry: bool) -> None:
    for name in MANIFESTS:
        path = os.path.join(root, name)
        if os.path.exists(path):
            report("manifests", path, dry)


def clear_source(root: str, dry: bool) -> None:
    folders = [
        entry.path
        for entry in os.scandir(root)
        if entry.is_dir() and entry.name != "_work"
    ]
    total = len(folders)
    say("source: %d folder(s)" % total)
    for index, path in enumerate(folders, 1):
        if not dry:
            remove(path)
        if index % 50 == 0 or index == total:
            prog("clear source", index, total)
        if index % 500 == 0 or index == total:
            say("source: %d/%d" % (index, total))
    for name in ("_downloaded.jsonl", "catalog.md"):
        path = os.path.join(root, name)
        if os.path.exists(path):
            report("source", path, dry)


def clear_cache(root: str, dry: bool) -> None:
    work = os.path.join(root, "_work")
    if not os.path.isdir(work):
        say("work cache: absent")
        return
    entries = list(os.scandir(work))
    total = len(entries)
    say("work cache: %d item(s)" % total)
    for index, entry in enumerate(entries, 1):
        report("cache", entry.path, dry)
        prog("clear cache", index, total)
    if not dry:
        remove(work)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        fail("usage: clear.py <logs|cache|index|manifests|source|everything> --yes [--dry-run]")
    mode = args[0]
    dry = "--dry-run" in args
    if "--yes" not in args and not dry:
        fail("pass --yes to confirm deletion")
    if mode == "logs":
        clear_logs(dry)
        say("done (logs%s)" % (", dry run" if dry else ""))
        return 0
    if mode == "index":
        clear_index(safe_root(), dry)
    elif mode == "manifests":
        clear_manifests(safe_root(), dry)
    elif mode == "cache":
        clear_cache(safe_root(require_work=True), dry)
    elif mode == "source":
        clear_source(safe_root(require_marker=True), dry)
    elif mode == "everything":
        root = safe_root(require_marker=True)
        clear_source(root, dry)
        clear_manifests(root, dry)
        clear_index(root, dry)
        clear_cache(root, dry)
    else:
        fail("unknown mode %s" % mode)
    say("done (%s%s)" % (mode, ", dry run" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
