import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Export scripts into ZIP archives: one script, a tag set, or the whole library."""
import os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT
from tv_lib import read_jsonl

DEST = os.path.join(OUT, "_exports")


def folders():
    return [d for d in os.listdir(OUT)
            if os.path.isdir(os.path.join(OUT, d)) and d not in ("_work",)]


def zip_one(name):
    os.makedirs(DEST, exist_ok=True)
    fp = os.path.join(DEST, name.strip().replace("/", "_")[:80] + ".zip")
    src = os.path.join(OUT, name)
    if not os.path.isdir(src):
        print("not found:", name)
        return
    with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(src):
            z.write(os.path.join(src, f), os.path.join(name, f))
    print("wrote", fp)


def zip_prefix(prefix):
    os.makedirs(DEST, exist_ok=True)
    fp = os.path.join(DEST, "export_%s.zip" % prefix.replace("/", "_")[:40])
    names = [d for d in folders() if d.lower().startswith(prefix.lower())]
    with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED) as z:
        for d in names:
            for f in os.listdir(os.path.join(OUT, d)):
                z.write(os.path.join(OUT, d, f), os.path.join(d, f))
    print("wrote %s (%d scripts)" % (fp, len(names)))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--all"
    if arg == "--all":
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), "--prefix", ""], check=True)
    elif arg == "--prefix":
        zip_prefix(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        zip_one(arg)


if __name__ == "__main__":
    main()
