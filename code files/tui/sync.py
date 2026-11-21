"""Incremental sync driver used by the TUI's ``s`` action.

This mirrors ``harvest/tv_delta.py`` (merge shards -> download new -> rebuild
manifest/index/analyze) with one correction: the catalog is written with an
``os.walk`` so per-script folders are counted. ``Pipeline._verify`` still lists
the flat root and reports zero on a restructured corpus.

Output is plain text on stdout, including ``PROG`` lines, so the TUI can render
live progress.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files

import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import bootstrap  # noqa: F401,E402

from tv_config import OUT  # noqa: E402
from tv_lib import read_jsonl  # noqa: E402
from tv_pipeline import Pipeline, safe_name  # noqa: E402


def say(message: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), message), flush=True)


class Reporter:
    """Streams pipeline events as human + machine readable lines."""

    def emit_event(self, event: dict) -> None:
        kind = event.get("ev")
        if kind == "task":
            print(
                "[%s] PROG task|%s|%s|%s|%s"
                % (
                    time.strftime("%H:%M:%S"),
                    event.get("name"),
                    event.get("done"),
                    event.get("total"),
                    event.get("eta_min") or "",
                ),
                flush=True,
            )
        elif kind == "log":
            say(str(event.get("text", "")))
        elif kind == "phase":
            say("-- %s %s" % (event.get("name"), event.get("state")))


def write_catalog(pipeline: Pipeline) -> None:
    """Write catalog.md using a recursive walk (folder-safe)."""
    pine_paths: list[str] = []
    for root, dirs, names in os.walk(OUT):
        dirs[:] = [d for d in dirs if d != "_work"]
        for name in names:
            if name.lower().endswith(".pine"):
                pine_paths.append(os.path.join(root, name))

    present = {os.path.basename(path) for path in pine_paths}
    total_bytes = 0
    for path in pine_paths:
        try:
            total_bytes += os.path.getsize(path)
        except OSError:
            pass

    catalog = os.path.join(OUT, "catalog.md")
    rows = sorted(
        pipeline.by_pub.values(),
        key=lambda r: (-(r.get("likes") or 0), r.get("name") or ""),
    )
    protected = sum(1 for r in pipeline.by_pub.values() if str(r.get("access")) != "1")

    with open(catalog, "w", encoding="utf-8") as handle:
        handle.write("# TradingView Pine library\n\n")
        handle.write("- scripts enumerated: %d\n" % len(pipeline.by_pub))
        handle.write("- open-source (downloaded): %d\n" % len(pine_paths))
        handle.write("- protected (no source): %d\n" % protected)
        handle.write("- total size: %.1f MB\n" % (total_bytes / 1048576))
        handle.write("- generated: %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        handle.write("| # | Name | Author | Ver | Source | URL |\n|---|---|---|---|---|---|\n")
        for index, row in enumerate(rows, 1):
            pub = row.get("pub_id")
            filename = safe_name(row.get("name"), row.get("tv_id"), pub)
            has_source = filename in present
            handle.write(
                "| %d | %s | %s | %s | %s | %s |\n"
                % (
                    index,
                    (row.get("name") or "").replace("|", "/"),
                    (row.get("author") or "").replace("|", "/"),
                    row.get("version") or "",
                    ("[%s](%s)" % (filename, filename)) if has_source else "_protected_",
                    row.get("url") or "",
                )
            )
    say("catalog written: %s (%d files, %.1f MB)" % (catalog, len(pine_paths), total_bytes / 1048576))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    pipeline = Pipeline(reporter=Reporter(), workers=6, delay=0.15, scope="all")

    say("sync: merging cached shards")
    pipeline._merge()

    manifest = os.path.join(OUT, "_manifest.jsonl")
    known = {row.get("pub_id") for row in read_jsonl(manifest) if row.get("pub_id")}
    new = set(pipeline.by_pub) - known
    say("new scripts: %d" % len(new))

    pipeline._download()
    write_catalog(pipeline)

    cli = os.path.join(CODE, "tools", "tv.py")
    for step in ("manifest", "index", "analyze"):
        result = subprocess.run([sys.executable, "-u", cli, step])
        say("%s rc=%s" % (step, result.returncode))

    say("sync done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
