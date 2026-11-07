#!/bin/bash
# Census of main through the heavy queue; writes results to ~/mtg-worktrees/census/<UTC> and refreshes the work lists.
set -e
cd ~/mtg-simulator && git checkout -q main && git pull -q --ff-only
out=~/mtg-worktrees/census/$(date -u +%Y%m%dT%H%MZ)
~/mtg-worktrees/bin/heavy .venv/bin/python -m mtgsim.database_coverage --save "$out" --top 40 >/dev/null
.venv/bin/python -m mtgsim.blocking_units "$out/cards.csv" --save "$out/units" >/dev/null
cp "$out/units/units.csv" ~/mtg-worktrees/briefs/lists/units-latest.csv
.venv/bin/python - "$out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + "/summary.json")); c = d["counts"]
full = c.get("full", 0); print(f"census {sys.argv[1].rsplit('/',1)[1]} main {__import__('subprocess').check_output(['git','rev-parse','--short','HEAD'],text=True).strip()}: "
      f"full {full:,} of {d['total']:,} ({full/d['total']:.2%}), simplified {c.get('simplified',0):,}, partial {c.get('partial',0):,}; "
      f"since baseline 17,612: {full-17612:+,}")
PY
