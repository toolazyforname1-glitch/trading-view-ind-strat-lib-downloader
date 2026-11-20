import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Local analyzers: import graph, input params, hashes, tags, meta.json per folder."""
import hashlib, json, os, re, sys, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_config import HERE, OUT
from tv_lib import read_jsonl, write_jsonl

ANAL = os.path.join(OUT, "_work", "analysis")
IMPORT = re.compile(r"^\s*import\s+([^\s]+)", re.M)
INPUT = re.compile(r"\b(?:input|input\w*)\s*\(\s*(?:[^,()]+,\s*)?[\"']([^\"']+)[\"']")
TAGWORDS = {
    "trend": ("supertrend", "trend", "ema", "ma ", "moving average", "ichimoku"),
    "volume": ("volume", "vwap", "obv", "delta", "footprint"),
    "volatility": ("bollinger", "atr", "volatility", "stddev", "band"),
    "momentum": ("rsi", "macd", "stoch", "momentum", "cci", "williams"),
    "price-action": ("candlestick", "pinbar", "engulf", "price action", "pattern"),
    "liquidity": ("liquidity", "order block", "fvg", "fair value", "sweep"),
    "session": ("session", "new york", "london", "asia", "time filter"),
    "risk": ("risk", "position size", "stop loss", "take profit"),
    "machine-learning": ("machine learning", "neural", "regression", "lstm"),
}


def pine_files():
    for root, dirs, names in os.walk(OUT):
        dirs[:] = [d for d in dirs if d not in ("_work",)]
        for n in names:
            if n.lower().endswith(".pine"):
                yield os.path.join(root, n)


def analyze():
    os.makedirs(ANAL, exist_ok=True)
    graph = defaultdict(list)
    hashes = {}
    tags = {}
    inputs = {}
    n = 0
    t0 = time.time()
    for p in pine_files():
        n += 1
        stem = os.path.splitext(os.path.basename(p))[0]
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        hashes[stem] = hashlib.sha256(txt.encode("utf-8", "replace")).hexdigest()
        imps = [x.split("/")[-1].split(".")[0] for x in IMPORT.findall(txt)]
        if imps:
            graph[stem] = imps
        ins = INPUT.findall(txt[:30000])
        if ins:
            inputs[stem] = ins[:40]
        low = (stem + " " + txt[:800]).lower()
        t = [k for k, words in TAGWORDS.items() if any(w in low for w in words)]
        tags[stem] = t or ["uncategorized"]
        if n % 10000 == 0:
            print("[analysis] %d files %.0fs" % (n, time.time() - t0), flush=True)
    write_jsonl(os.path.join(ANAL, "imports.jsonl"),
                [{"script": k, "imports": v} for k, v in graph.items()])
    write_jsonl(os.path.join(ANAL, "hashes.jsonl"),
                [{"script": k, "sha256": v} for k, v in hashes.items()])
    write_jsonl(os.path.join(ANAL, "tags.jsonl"),
                [{"script": k, "tags": v} for k, v in tags.items()])
    write_jsonl(os.path.join(ANAL, "inputs.jsonl"),
                [{"script": k, "params": v} for k, v in inputs.items()])
    print("[analysis] %d files: %d with imports, %d with inputs, %d hashes in %.0fs"
          % (n, len(graph), len(inputs), len(hashes), time.time() - t0), flush=True)
    return hashes, tags, inputs


def meta_json(hashes, tags, inputs):
    dl = {r.get("pub_id"): r for r in read_jsonl(os.path.join(OUT, "_downloaded.jsonl"))}
    man = {r.get("pub_id"): r for r in read_jsonl(os.path.join(OUT, "_manifest.jsonl"))}
    desc = {r.get("pub_id"): r.get("description") for r in read_jsonl(
        os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl"))}
    n = 0
    for pub, rec in dl.items():
        fname = rec.get("file") or ""
        stem = fname[:-5] if fname.lower().endswith(".pine") else fname
        folder = os.path.join(OUT, stem)
        if not os.path.isdir(folder):
            continue
        m = dict(man.get(pub) or {})
        m.update({k: v for k, v in rec.items() if v})
        obj = {
            "pub_id": pub, "name": m.get("name") or stem, "author": m.get("author", ""),
            "type": m.get("script_type"), "version": m.get("version"),
            "url": m.get("url") or "", "sha256": hashes.get(stem, ""),
            "tags": tags.get(stem, []), "inputs": inputs.get(stem, []),
            "description": desc.get(pub, "") or m.get("description", ""),
        }
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        n += 1
    print("[analysis] meta.json written: %d" % n, flush=True)


def main():
    hashes, tags, inputs = analyze()
    meta_json(hashes, tags, inputs)


if __name__ == "__main__":
    main()
