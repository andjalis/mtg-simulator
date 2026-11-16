#!/bin/sh
# before/after for #723: usage run.sh <label>
cd "$(dirname "$0")/../.."
P=.venv/bin/python
for m in "results/ai_723/ubr_723.txt decks/green_stompy.txt" "results/ai_723/ubr_723.txt decks/mono_red_aggro.txt" "decks/ub_snow_control.txt decks/mono_red_aggro.txt" "decks/orzhov_midrange.txt decks/green_stompy.txt"; do
  set -- $m
  echo "== $1 vs $2"; $P -m mtgsim "$1" "$2" -n 400 --seed 5 2>/dev/null | grep -iE "win|%" | head -3
done
