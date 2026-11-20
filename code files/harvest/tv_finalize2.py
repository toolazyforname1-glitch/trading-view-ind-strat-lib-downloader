import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""End-to-end finalizer: wait for the description scrapers, then finish the job.

1. wait for tv_desc_scrape.py (phase 2) and tv_desc_phase3.py
2. re-run phase 2 to pick up short ids resolved by phase 3
3. rewrite every .md with the full description
4. rebuild the manifest + run the integrity check
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tv_lib import read_jsonl, OUT
from tv_config import LOGS

PY = sys.executable
LOG = os.path.join(LOGS, "finalize2.log")
REPORT = os.path.join(HERE, "_finalize2.txt")
IDS = os.path.join(OUT, "_work", "descriptions", "ids.jsonl")
DESCS = os.path.join(OUT, "_work", "descriptions", "descriptions.jsonl")


import ctypes
from ctypes import wintypes

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def pythonw_pids():
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return []
    pids = []
    try:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if k32.Process32First(snap, ctypes.byref(pe)):
            while True:
                if pe.szExeFile.lower() == b"pythonw.exe" and pe.th32ProcessID != os.getpid():
                    pids.append(pe.th32ProcessID)
                if not k32.Process32Next(snap, ctypes.byref(pe)):
                    break
    finally:
        k32.CloseHandle(snap)
    return pids


def running():
    return len(pythonw_pids())


def count_lines(p):
    if not os.path.exists(p):
        return 0
    n = 0
    with open(p, "rb") as f:
        for _ in f:
            n += 1
    return n


def main():
    logf = open(LOG, "a", buffering=1, encoding="utf-8")
    rep = []

    def say(m):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)
        logf.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), m))
        logf.flush()

    deadline = time.time() + 21600
    while time.time() < deadline:
        if running() == 0:
            break
        time.sleep(20)
    say("scrapers finished")

    cli = os.path.join(HERE, "tools", "tv.py")
    for step, args in (("phase2 rerun", ["desc", "2"]),
                       ("md refresh", ["refresh"]),
                       ("manifest", ["manifest"]),
                       ("verify", ["verify"])):
        say("running %s ..." % step)
        try:
            r = subprocess.run([PY, "-u", cli] + args,
                               capture_output=True, text=True, timeout=14400, cwd=HERE)
            say("  %s rc=%s" % (step, r.returncode))
            rep.append("=== %s rc=%s ===" % (step, r.returncode))
            rep.append((r.stdout or "").strip()[-4000:])
            if r.stderr and r.stderr.strip():
                rep.append("STDERR: " + r.stderr.strip()[-1500:])
        except Exception as e:
            say("  %s FAILED: %s" % (step, e))
            rep.append("=== %s FAILED: %s ===" % (step, e))

    rep.append("ids.jsonl lines: %d" % count_lines(IDS))
    rep.append("descriptions.jsonl lines: %d" % count_lines(DESCS))
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    say("finalize2 done")


if __name__ == "__main__":
    main()
