"""Seeded, stratified sample of PARTIAL cards for the per-card translation pilot.

    python3 scripts/translate_sample.py --coverage <coverage_check cache .tsv> --bulk oracle-cards.jsonl.gz \
        --exclude-text DIR --seed 20261116 --n 200 --out results/pilot_translate_20261116/sample.tsv

Strata are (primary card type, rarity); each gets a share of N proportional to its size (largest remainder).
Inside a stratum the cards are drawn with random.Random(seed). Cards whose exact name appears in any file
under --exclude-text (open-PR diffs and bodies) are dropped before the draw.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
from pathlib import Path

TYPES = ("Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Land", "Artifact", "Enchantment")


def primary_type(type_line: str) -> str:
    front = type_line.split(" // ")[0]
    return next((t for t in TYPES if t in front), "Other")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", required=True, type=Path)
    ap.add_argument("--bulk", required=True, type=Path)
    ap.add_argument("--exclude-text", type=Path)
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    partial = sorted(line.split("\t")[0] for line in a.coverage.read_text().splitlines()
                     if line.split("\t")[1:2] == ["partial"])
    info = {}
    with gzip.open(a.bulk, "rt") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            c = json.loads(line)
            info.setdefault(c["name"], (primary_type(c.get("type_line", "")), c.get("rarity", "?")))
    blob = ""
    if a.exclude_text:
        blob = "\n".join(p.read_text(errors="replace") for p in sorted(a.exclude_text.iterdir()) if p.is_file())
    excluded = [n for n in partial if n in blob]
    pool = [n for n in partial if n not in blob and n in info]
    strata: dict = {}
    for n in pool:
        strata.setdefault(info[n], []).append(n)
    keys = sorted(strata)
    quotas = {k: a.n * len(strata[k]) / len(pool) for k in keys}
    alloc = {k: int(q) for k, q in quotas.items()}
    for k in sorted(keys, key=lambda k: (-(quotas[k] - alloc[k]), k))[:a.n - sum(alloc.values())]:
        alloc[k] += 1
    rng = random.Random(a.seed)
    rows = []
    for k in keys:
        for n in sorted(rng.sample(strata[k], alloc[k])):
            rows.append((n, k[0], k[1]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("# seed=%d n=%d partial=%d excluded_open_pr=%d not_in_bulk=%d\nname\ttype\trarity\n" % (
        a.seed, a.n, len(partial), len(excluded), len(partial) - len(excluded) - len(pool))
        + "".join(f"{n}\t{t}\t{r}\n" for n, t, r in rows))
    print(f"{len(rows)} cards from {len(pool)} (excluded {len(excluded)} named in open PRs)")
    for k in keys:
        print(f"  {k[0]:13} {k[1]:9} {len(strata[k]):5} -> {alloc[k]}")


if __name__ == "__main__":
    main()
