"""Fast coverage and parse check: this checkout against a base ref, in parallel, with a cache.

    python3 scripts/coverage_check.py                     # vs origin/main: counts, gained/lost full, new errors
    python3 scripts/coverage_check.py --base agent/x      # vs another ref
    python3 scripts/coverage_check.py --cards "Flicker" "Broken Visage"   # just these cards, instantly
    python3 scripts/coverage_check.py --json              # machine-readable summary

Every card in the offline database is classified as database_coverage does (full / simplified / partial /
parse_error), and a hash of its parsed CardDef is kept so changed parses can be counted. Results are cached
in <git common dir>/coverage-cache/ (shared by every worktree) under a hash of the parser code (every file under mtgsim/ except the data directory) plus
the card database, so the base ref is parsed only once and repeat runs with unchanged code are instant. The
work is split across all CPU cores. Exits 1 when a card that parsed on the base now raises.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("MTGSIM_CARDDB", ROOT / "mtgsim" / "data" / "cards.sqlite3"))


def _cache_dir() -> Path:
    """In the repository's common git dir, so every worktree (and agent) shares the base results."""
    try:
        common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], check=True,
                                capture_output=True, text=True).stdout.strip()
        return (ROOT / common).resolve() / "coverage-cache"
    except (OSError, subprocess.CalledProcessError):
        return ROOT / ".cache" / "coverage"


CACHE = _cache_dir()
STATUSES = ("full", "simplified", "partial", "parse_error")

# Runs inside a worker process with PYTHONPATH=<code root>; prints "name\tstatus\tparse-hash" per card.
WORKER = r"""
import dataclasses, hashlib, re, sys
re._MAXCACHE = 1_000_000   # thousands of parser patterns; the default cache recompiles them per card
from mtgsim.carddb import CardDB
from mtgsim.coverage import card_coverage
def canon(obj, depth=0):
    # a stable text form of a parsed card: dataclass fields, recursively (CardDef's repr is only its name)
    if depth > 12:
        return "..."
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return type(obj).__name__ + "(" + ",".join(
            f.name + "=" + canon(getattr(obj, f.name), depth + 1) for f in dataclasses.fields(obj)) + ")"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(canon(x, depth + 1) for x in obj) + "]"
    if isinstance(obj, (set, frozenset)):
        return "{" + ",".join(sorted(canon(x, depth + 1) for x in obj)) + "}"
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k!r}:{canon(v, depth + 1)}" for k, v in sorted(obj.items(), key=lambda kv: repr(kv[0]))) + "}"
    if callable(obj):
        return getattr(obj, "__qualname__", type(obj).__name__)
    return repr(obj)
part, parts = int(sys.argv[1]), int(sys.argv[2])
db = CardDB(offline=True)
names = [r[0] for r in db._all.execute("SELECT name FROM cards ORDER BY key")][part::parts]
out = []
for name in names:
    try:
        card = db.get(name)
        status = card_coverage(card).status
        digest = hashlib.sha1(canon(card).encode()).hexdigest()[:12]
    except Exception as exc:
        status, digest = "parse_error", "ERR " + type(exc).__name__
    out.append(f"{name}\t{status}\t{digest}")
sys.stdout.write("\n".join(out) + "\n")
"""


def code_hash(root: Path) -> str:
    """Hash of the parser/engine source under root/mtgsim (data/ excluded except its JSON tables) and the DB."""
    h = hashlib.sha1(WORKER.encode())      # a change to how cards are measured invalidates the cache too
    pkg = root / "mtgsim"
    for path in sorted(pkg.rglob("*")):
        rel = path.relative_to(pkg)
        if not path.is_file() or "__pycache__" in rel.parts:
            continue
        if rel.parts[0] == "data" and path.suffix != ".json":
            continue
        h.update(str(rel).encode())
        h.update(path.read_bytes())
    st = DB.stat()
    h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def measure(root: Path, jobs: int) -> dict[str, tuple[str, str]]:
    """{name: (status, parse hash)} for every card under the code at root, cached by code hash."""
    key = code_hash(root)
    cached = CACHE / f"{key}.tsv"
    if cached.exists():
        return _load(cached)
    env = dict(os.environ, PYTHONPATH=str(root), MTGSIM_CARDDB=str(DB), PYTHONWARNINGS="ignore")
    procs = [subprocess.Popen([sys.executable, "-c", WORKER, str(i), str(jobs)], cwd=root, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(jobs)]
    lines = []
    for p in procs:
        out, err = p.communicate()
        if p.returncode:
            sys.exit(f"worker failed under {root}:\n{err[-2000:]}")
        lines.append(out)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".tmp")
    tmp.write_text("".join(lines))
    tmp.replace(cached)
    return _load(cached)


def _load(path: Path) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in path.read_text().splitlines():
        if line:
            name, status, digest = line.split("\t", 2)
            rows[name] = (status, digest)
    return rows


def export(ref: str, dest: Path) -> Path:
    """The mtgsim package at ref, unpacked under dest."""
    data = subprocess.run(["git", "-C", str(ROOT), "archive", ref, "mtgsim"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=BytesIO(data)) as tar:
        tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)
    return dest


def counts(rows) -> dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for status, _ in rows.values():
        out[status] += 1
    return out


def check_cards(names, jobs) -> int:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("MTGSIM_CARDDB", str(DB))
    from mtgsim.carddb import CardDB
    from mtgsim.coverage import card_coverage
    db = CardDB(offline=True)
    for name in names:
        try:
            row = card_coverage(db.get(name))
        except Exception as exc:
            print(f"{name}: parse_error {type(exc).__name__}: {exc}")
            continue
        print(f"{name}: {row.status}")
        for line in row.ignored:
            print(f"    unsupported: {line}")
        for line in row.simplified:
            print(f"    simplified:  {line}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="git ref to compare against (default origin/main)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="worker processes (default: CPU count)")
    ap.add_argument("--cards", nargs="+", metavar="NAME", help="only report these cards (no full run)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--show", type=int, default=25, help="cards listed per change group (default 25)")
    args = ap.parse_args(argv)
    if args.cards:
        return check_cards(args.cards, args.jobs)
    if not DB.exists():
        sys.exit(f"no card database at {DB}; run python3 -m mtgsim.build_carddb")

    head = measure(ROOT, args.jobs)
    with tempfile.TemporaryDirectory() as tmp:
        base = measure(export(args.base, Path(tmp)), args.jobs)

    names = sorted(set(head) | set(base))
    gained = [n for n in names if head.get(n, ("",))[0] == "full" and base.get(n, ("",))[0] != "full"]
    lost = [n for n in names if base.get(n, ("",))[0] == "full" and head.get(n, ("",))[0] != "full"]
    broke = [n for n in names if head.get(n, ("",))[0] == "parse_error" and base.get(n, ("",))[0] != "parse_error"]
    changed = sum(1 for n in names if head.get(n, ("", ""))[1] != base.get(n, ("", ""))[1])
    hc, bc, total = counts(head), counts(base), len(head)
    summary = {"base": args.base, "total": total, "base_counts": bc, "counts": hc,
               "delta": {s: hc[s] - bc[s] for s in STATUSES}, "parse_changed": changed,
               "gained_full": gained, "lost_full": lost, "new_parse_errors": broke}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{total} cards, this checkout vs {args.base}")
        for s in STATUSES:
            print(f"  {s:<12} {bc[s]:>6} -> {hc[s]:>6}  ({hc[s] - bc[s]:+d})   {100 * hc[s] / total:5.2f}%")
        print(f"  parse changed for {changed} cards")
        for label, group in (("gained full", gained), ("lost full", lost), ("NEW PARSE ERRORS", broke)):
            if group:
                more = f" (+{len(group) - args.show} more)" if len(group) > args.show else ""
                print(f"{label} ({len(group)}): {', '.join(group[:args.show])}{more}")
    return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
