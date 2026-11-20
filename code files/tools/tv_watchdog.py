import os as _os, sys as _sys
_sys.dont_write_bytecode = True  # never create __pycache__ / .pyc files
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import bootstrap
"""Watchdog: wait for the gap-fill worker to exit, then write a summary file.

Usage: python tv_watchdog.py [max_seconds]
Polls internally, exits by itself. Output: _watchdog_gapfill.txt
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIDFILE = os.path.join(HERE, "_gapfill.pid")
LOG = os.path.join(HERE, "gapfill.log")
OUT = os.path.join(HERE, "_watchdog_gapfill.txt")


def alive(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE|QUERY_INFORMATION
        if not h:
            return False
        rc = ctypes.windll.kernel32.WaitForSingleObject(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)
        return rc == 0x102
    except Exception:
        return True


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 14400.0
    pidfile = sys.argv[2] if len(sys.argv) > 2 else PIDFILE
    pid = 0
    for _ in range(30):
        try:
            pid = int(open(pidfile).read().strip())
            break
        except Exception:
            time.sleep(2)
    deadline = time.time() + limit
    state = "timeout"
    while time.time() < deadline:
        if pid and not alive(pid):
            state = "exited"
            break
        time.sleep(10)
    tail = ""
    try:
        with open(LOG, "r", encoding="utf-8", errors="replace") as fh:
            tail = "\n".join(fh.read().splitlines()[-60:])
    except Exception as e:
        tail = "log read failed: %s" % e
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("pid=%s state=%s at %s\n" % (pid, state, time.strftime("%Y-%m-%d %H:%M:%S")))
        f.write(tail + "\n")
    print("watchdog done: %s" % state)


if __name__ == "__main__":
    main()
