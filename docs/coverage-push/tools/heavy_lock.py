"""Machine-wide slot queue for CPU-heavy mtg-simulator checks (used by `heavy` and by each venv's sitecustomize)."""
import fcntl, os, sys, time
from pathlib import Path

SLOTS = int(os.environ.get("MTG_HEAVY_SLOTS", "4"))
LOCKS = Path.home() / "mtg-worktrees" / ".locks"
HEAVY_SCRIPTS = ("fast_check.py", "pilot_gate.py", "parse_diff.py")
HEAVY_MODULES = ("mtgsim.database_coverage",)
_held = None


def acquire(label):
    global _held
    LOCKS.mkdir(exist_ok=True)
    waited = False
    while True:
        for i in range(SLOTS):
            f = open(LOCKS / f"slot{i}", "a")     # not "w": that would wipe the holder's label
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.truncate(0); f.write(f"{os.getcwd()} {label}\n"); f.flush()
                _held = f                      # kept open for the life of the process
                os.environ["MTG_HEAVY_HELD"] = "1"   # children (workers, subprocesses) inherit it and don't queue again
                return f
            except BlockingIOError:
                f.close()
        if not waited:
            print(f"heavy: {SLOTS} heavy checks already running, waiting for a free slot...", file=sys.stderr, flush=True)
            waited = True
        time.sleep(5)


def auto():
    """Called from sitecustomize: queue this interpreter if it is a top-level heavy check."""
    if os.environ.get("MTG_HEAVY_HELD"):
        return
    argv = list(getattr(sys, "orig_argv", sys.argv))
    if "_worker" in argv or any("multiprocessing" in a for a in argv):
        return
    script = any(a.endswith(HEAVY_SCRIPTS) for a in argv)
    module = any(argv[i] == "-m" and argv[i + 1] in HEAVY_MODULES for i in range(len(argv) - 1))
    if script or module:
        try:
            os.nice(10)
        except OSError:
            pass
        acquire(" ".join(argv[1:])[:200])
