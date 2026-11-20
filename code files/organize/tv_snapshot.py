import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Git-tracked snapshots of the catalog and indexes (audit trail)."""
import os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import OUT, HERE


def run(*args):
    r = subprocess.run(args, cwd=OUT, capture_output=True, text=True)
    if r.returncode:
        print("FAIL", " ".join(args), r.stderr.strip()[:300], flush=True)
    return r.returncode == 0


def main():
    if not run("git", "rev-parse", "--git-dir"):
        print("[snapshot] init", flush=True)
        if not run("git", "init"):
            return
    files = ["catalog.md", "_manifest.csv", "_manifest.jsonl", "_manifest_stats.json",
             "README.md", "library.sqlite"]
    run("git", "add", "--", *[f for f in files if os.path.exists(os.path.join(OUT, f))])
    msg = "snapshot: %s" % time.strftime("%Y-%m-%d %H:%M")
    run("git", "commit", "-m", msg)
    r = subprocess.run(["git", "log", "--oneline", "-3"], cwd=OUT,
                       capture_output=True, text=True)
    print("[snapshot] %s\n%s" % (msg, r.stdout.strip()), flush=True)


if __name__ == "__main__":
    main()
