import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Single CLI entry point. Every subcommand is a module in a subfolder."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

MAP = {
    "verify": "organize/tv_verify.py", "manifest": "harvest/tv_manifest.py",
    "index": "organize/tv_index.py", "analyze": "organize/tv_analyze.py",
    "expand": "harvest/tv_expand.py", "enrich": "harvest/tv_enrich.py",
    "delta": "harvest/tv_delta.py", "export": "organize/tv_export.py",
    "snapshot": "organize/tv_snapshot.py",
    "desc": "harvest/tv_desc_scrape.py", "refresh": "organize/tv_md_refresh.py",
}
HELP = """TradingView Pine harvester

  python tv.py status
  python tv.py configure <folder>      choose where the indicators live
  python tv.py verify                  integrity check
  python tv.py manifest                rebuild _manifest.* from cache
  python tv.py analyze                 hashes, tags, imports, inputs, meta.json
  python tv.py index                   build SQLite FTS index
  python tv.py index <query>           search descriptions
  python tv.py expand type|seeds|author|slice|all
  python tv.py enrich meta|versions|images|comments|lang|all
  python tv.py delta                   merge caches, download new, rebuild
  python tv.py export <name|--prefix P|--all>
  python tv.py snapshot                commit catalog state to git
  python tv.py pause|resume            suspend/resume detached workers
"""


def status():
    from tv_config import OUT
    n = 0
    for root, dirs, names in os.walk(OUT):
        dirs[:] = [d for d in dirs if d != "_work"]
        n += sum(1 for f in names if f.lower().endswith(".pine"))
    print("data folder :", OUT)
    if not os.path.isdir(OUT):
        print("data folder does not exist yet — run configure or a full scrape")
        return
    print("script folders:", len([d for d in os.listdir(OUT)
          if os.path.isdir(os.path.join(OUT, d)) and d != "_work"]))
    print("pine files  :", n)
    for f in ("catalog.md", "_manifest.csv", "library.sqlite"):
        p = os.path.join(OUT, f)
        print("%-16s %s" % (f, ("%.1f MB" % (os.path.getsize(p) / 1048576)) if os.path.exists(p) else "-"))


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP)
        return
    cmd = args[0]
    if cmd == "status":
        status()
        return
    if cmd == "configure":
        from tv_config import set_data_dir
        if len(args) < 2:
            print("usage: python tv.py configure <folder>")
            sys.exit(2)
        set_data_dir(args[1])
        print("data folder set to", os.path.abspath(args[1]))
        return
    if cmd in ("pause", "resume"):
        ps = os.path.join(HERE, "tools", "tv_pause.ps1")
        extra = ["-Resume"] if cmd == "resume" else []
        sys.exit(subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", ps] + extra).returncode)
    if cmd not in MAP:
        print("unknown command:", cmd)
        print(HELP)
        sys.exit(2)
    script = os.path.join(HERE, MAP[cmd].replace("/", os.sep))
    extra = ["query", args[1]] if cmd == "index" and len(args) > 1 else args[1:]
    sys.exit(subprocess.run([PY, "-u", script] + extra).returncode)


if __name__ == "__main__":
    main()
