"""Compare common assertions from the bounded Python/Forge rules probes.

    python3 -m mtgsim.rules_compare --builtin python.json --forge-log forge.log --save comparison.json
"""
import argparse
import json
from pathlib import Path

from .provenance import atomic_json, file_hash

EXPECTED = {
    "legend-rule": {"observed_remaining": 1},
    "target-type-validation": {"validation_accepts_land": False},
    "equip-response-window": {"observed_stack_size": 1, "observed_attached_before_resolution": False,
                              "observed_attached_after_resolution": True},
}


def index(rows, required_only=False):
    out = {}
    for row in rows:
        key = row["id"]
        if required_only and key not in EXPECTED:
            continue
        if key in out:
            raise ValueError(f"duplicate probe: {key}")
        out[key] = row
    if set(out) != set(EXPECTED):
        raise ValueError("missing or unexpected probe IDs")
    return out


def compare(builtin, forge_log):
    a = index(builtin["observations"], required_only=True)
    b = index([json.loads(line.partition("RULES_PROBE ")[2]) for line in forge_log.splitlines()
               if line.startswith("RULES_PROBE ")])
    rows = []
    for key, expected in EXPECTED.items():
        for record in (a[key], b[key]):
            if any(field not in record or type(record[field]) is not type(value)
                   for field, value in expected.items()):
                raise ValueError(f"missing or malformed assertions for {key}")
        left, right = ({f: record[f] for f in expected} for record in (a[key], b[key]))
        rows.append({"id": key, "expected": expected, "builtin": left, "forge": right,
                     "agree": left == right, "builtin_conforms": left == expected,
                     "forge_conforms": right == expected})
    return {"schema": 1, "scope": "Three bounded common assertion sets; no full-card correctness claim",
            "compared": len(rows), "agree": sum(row["agree"] for row in rows),
            "both_conform": sum(row["builtin_conforms"] and row["forge_conforms"] for row in rows),
            "excluded": ["forge-import-exile: Python importer, not Forge runtime"], "observations": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--builtin", type=Path, required=True)
    ap.add_argument("--forge-log", type=Path, required=True)
    ap.add_argument("--save", type=Path, required=True)
    args = ap.parse_args(argv)
    result = compare(json.loads(args.builtin.read_text()), args.forge_log.read_text())
    result["inputs"] = {"builtin_sha256": file_hash(args.builtin), "forge_log_sha256": file_hash(args.forge_log)}
    atomic_json(args.save, result)
    print(f"{result['agree']}/{result['compared']} agree; {result['both_conform']} conform to bounded expectations")
    return int(result["both_conform"] != result["compared"])


if __name__ == "__main__":
    raise SystemExit(main())
