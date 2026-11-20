import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Build/query a SQLite FTS5 index over all scripts, descriptions and sources."""
import os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT

DB = os.path.join(OUT, "library.sqlite")


def build():
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE scripts(pub_id TEXT PRIMARY KEY, name TEXT, author TEXT, "
                "kind TEXT, description TEXT, path TEXT, sha256 TEXT, tags TEXT)")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(name, author, description, content='scripts', "
                "content_rowid='rowid')")
    t0 = time.time()
    n = 0
    man = {}
    mf = os.path.join(OUT, "_manifest.jsonl")
    if os.path.exists(mf):
        import json
        for line in open(mf, encoding="utf-8"):
            try:
                r = json.loads(line)
                man[r.get("pub_id")] = r
            except Exception:
                pass
    dl = {}
    df = os.path.join(OUT, "_downloaded.jsonl")
    if os.path.exists(df):
        import json
        for line in open(df, encoding="utf-8"):
            try:
                r = json.loads(line)
                dl[r.get("pub_id")] = r
            except Exception:
                pass
    hf = os.path.join(OUT, "_work", "analysis", "hashes.jsonl")
    hashes = {}
    if os.path.exists(hf):
        import json
        for line in open(hf, encoding="utf-8"):
            try:
                r = json.loads(line)
                hashes[r.get("script")] = r.get("sha256")
            except Exception:
                pass
    dfp = os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl")
    descs = {}
    if os.path.exists(dfp):
        import json
        for line in open(dfp, encoding="utf-8"):
            try:
                r = json.loads(line)
                descs[r.get("pub_id")] = r.get("description")
            except Exception:
                pass
    for pub, rec in dl.items():
        m = man.get(pub) or {}
        fname = rec.get("file") or ""
        stem = fname[:-5] if fname.lower().endswith(".pine") else fname
        folder = os.path.join(OUT, stem)
        if not os.path.isdir(folder):
            continue
        d = descs.get(pub) or m.get("description") or ""
        con.execute("INSERT OR REPLACE INTO scripts VALUES(?,?,?,?,?,?,?,?)",
                    (pub, m.get("name") or stem, m.get("author") or "",
                     str(m.get("script_type") or ""), d,
                     os.path.join(folder, fname), hashes.get(stem, ""), ""))
        n += 1
        if n % 10000 == 0:
            con.commit()
    con.commit()
    con.execute("INSERT INTO fts(rowid,name,author,description) "
                "SELECT rowid,name,author,description FROM scripts")
    con.commit()
    print("[index] %d rows in %.0fs -> %s" % (n, time.time() - t0, DB), flush=True)
    con.close()


def query(term, limit=20):
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT s.name,s.author,s.path FROM fts f JOIN scripts s ON s.rowid=f.rowid "
                       "WHERE fts MATCH ? LIMIT ?", (term, limit)).fetchall()
    con.close()
    for name, author, path in rows:
        print("%s | %s | %s" % (name[:50], author[:20], path))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        query(sys.argv[2] if len(sys.argv) > 2 else "indicator")
    else:
        build()


if __name__ == "__main__":
    main()
